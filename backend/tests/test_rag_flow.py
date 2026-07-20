"""RAG grounding flows through the orchestrator (R3): grounded form creation,
grounded rule drafting + save-as-artifact, and workflow-release semantics."""

from __future__ import annotations

import json

from app.agent import stream_turn
from app.ai import MockProvider
from app.connector import DemoConnector
from app.context import build_context
from app.db.models import WorkflowState
from app.services import artifacts as artifacts_svc
from app.services import context_store, conversations, projects


async def _turn(session, project, conv, text, context_version_id=None):
    conversations.add_message(session, conv.id, "user", text)
    events = []
    async for ev in stream_turn(session=session, project=project, conversation=conv,
                                connector=DemoConnector(), provider=MockProvider(),
                                application="MCWPCF", classification="development",
                                environment_name="MCW Demo (Local)", demo=True,
                                context_version_id=context_version_id, user_text=text):
        events.append(ev)
    return events


def _block_types(events):
    return [ev.data.get("type") for ev in events if str(ev.type) == "block"]


def _blocks_of(events, block_type):
    return [ev.data for ev in events if str(ev.type) == "block" and ev.data.get("type") == block_type]


# A calc-script body long enough to exercise the RAG chunker, wearing the exact
# vocabulary the creation request will use ("copies working to final").
_RULE_BODY = (
    "SET UPDATECALC OFF;\n"
    'FIX ("Working", &CurrYr, "OEP_Plan")\n'
    '  DATACOPY "Working" TO "Final";\n'
    "ENDFIX\n"
    "/* copies the Working version to Final across the planning scenario;\n"
    "   working data is promoted to final after review. */\n"
) * 4


def _rule_record(name: str, cube: str, body: str) -> dict:
    return {
        "kind": "rule", "name": name, "cube": cube, "application": "MCWPCF",
        "search_text": name.lower(),
        "data": {"name": name, "application": "MCWPCF", "cube": cube,
                 "body": body, "source": "snapshot"},
    }


async def _context_with_rule_bodies(session, project_id: str) -> str:
    """A DemoConnector-built context plus snapshot-style rule-body records."""
    bundle = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    records = list(bundle.records)
    records.append(_rule_record("Copy Working to Final", "OEP_FS", _RULE_BODY))
    records.append(_rule_record(
        "Allocate Overhead", "OEP_FS",
        'FIX ("Actual") /* allocate overhead across entities */ ENDFIX;'))
    cv = context_store.persist_context(
        session, project_id, bundle.application, bundle.mode, bundle.label,
        bundle.manifest.model_dump(by_alias=True), bundle.counts, records)
    session.flush()
    return cv.id


async def test_form_creation_emits_grounding_before_preview(session):
    out = projects.create_project(session, "RAG Form Grounding Test")
    proj = projects.get_project(session, out.id)
    cv_id = await _context_with_rule_bodies(session, proj.id)
    conv = conversations.create_conversation(session, proj.id)
    e = await _turn(session, proj, conv,
                    "Create an Actuals form with level-zero descendants of Total Payroll in rows",
                    context_version_id=cv_id)
    types = _block_types(e)
    assert "groundingSources" in types
    assert "formPreview" in types
    assert types.index("groundingSources") < types.index("formPreview")
    payload = _blocks_of(e, "groundingSources")[0]["data"]
    assert payload["purpose"] == "form"
    assert payload["chunks"]
    assert payload["query"].startswith("Create an Actuals form")


async def test_form_creation_without_context_has_no_grounding(session):
    out = projects.create_project(session, "RAG No Context Test")
    proj = projects.get_project(session, out.id)
    conv = conversations.create_conversation(session, proj.id)
    e = await _turn(session, proj, conv, "Create an Actuals form")
    types = _block_types(e)
    assert "groundingSources" not in types
    assert "formPreview" in types
    assert "confirmation" in types


async def test_rule_creation_grounded_draft_then_save(session):
    out = projects.create_project(session, "RAG Rule Draft Test")
    proj = projects.get_project(session, out.id)
    cv_id = await _context_with_rule_bodies(session, proj.id)
    conv = conversations.create_conversation(session, proj.id)

    e = await _turn(session, proj, conv, "create a rule that copies working to final",
                    context_version_id=cv_id)
    types = _block_types(e)
    assert "groundingSources" in types
    assert "rulePreview" in types
    assert "confirmation" in types
    assert types.index("groundingSources") < types.index("rulePreview")

    grounding = _blocks_of(e, "groundingSources")[0]["data"]
    assert grounding["purpose"] == "rule"
    assert any(c.get("kind") == "rule" for c in grounding["chunks"])

    preview = _blocks_of(e, "rulePreview")[0]["data"]
    assert preview["draftScript"]
    assert preview["grounded"] is True
    assert preview["cube"]
    assert preview["name"]

    confirmation = _blocks_of(e, "confirmation")[0]["data"]
    values = [a["value"] for a in confirmation["actions"]]
    assert "save rule draft" in values
    assert "cancel" in values

    # follow-up turn: persist the draft as an artifact
    e = await _turn(session, proj, conv, "save rule draft", context_version_id=cv_id)
    types = _block_types(e)
    assert "downloadableFile" in types
    drafts = artifacts_svc.list_artifacts(session, proj.id, kind="ruleDraft")
    assert len(drafts) == 1
    stored = json.loads(drafts[0].content)
    assert stored["spec"]["cube"]
    assert stored["draftScript"] == preview["draftScript"]
    # the workflow ended with the save
    wf = session.query(WorkflowState).filter_by(conversation_id=conv.id, skill="rules").first()
    assert wf is not None and wf.active is False


async def test_rules_draft_workflow_releases_unrelated_turns(session):
    out = projects.create_project(session, "RAG Rule Release Test")
    proj = projects.get_project(session, out.id)
    cv_id = await _context_with_rule_bodies(session, proj.id)
    conv = conversations.create_conversation(session, proj.id)
    await _turn(session, proj, conv, "create a rule that copies working to final",
                context_version_id=cv_id)

    # An unrelated turn must not be swallowed by the pending draft — it releases
    # the workflow and is answered by the skill its intent asked for.
    e = await _turn(session, proj, conv, "what can you do", context_version_id=cv_id)
    assert "rulePreview" not in _block_types(e)
    wf = session.query(WorkflowState).filter_by(conversation_id=conv.id, skill="rules").first()
    assert wf is not None and wf.active is False

    # With the draft released, "save rule draft" no longer saves anything.
    await _turn(session, proj, conv, "save rule draft", context_version_id=cv_id)
    assert artifacts_svc.list_artifacts(session, proj.id, kind="ruleDraft") == []


async def test_rule_creation_cancel_discards_draft(session):
    out = projects.create_project(session, "RAG Rule Cancel Test")
    proj = projects.get_project(session, out.id)
    cv_id = await _context_with_rule_bodies(session, proj.id)
    conv = conversations.create_conversation(session, proj.id)
    await _turn(session, proj, conv, "create a rule that copies working to final",
                context_version_id=cv_id)
    e = await _turn(session, proj, conv, "cancel", context_version_id=cv_id)
    assert "markdown" in _block_types(e)
    assert artifacts_svc.list_artifacts(session, proj.id, kind="ruleDraft") == []
    wf = session.query(WorkflowState).filter_by(conversation_id=conv.id, skill="rules").first()
    assert wf is not None and wf.active is False


async def test_run_rule_flow_not_intercepted_by_creation(session):
    out = projects.create_project(session, "RAG Run Rule Test")
    proj = projects.get_project(session, out.id)
    conv = conversations.create_conversation(session, proj.id)
    e = await _turn(session, proj, conv, "run the IR rule")
    types = _block_types(e)
    assert "runtimePromptForm" in types
    assert "rulePreview" not in types
