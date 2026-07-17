"""Full conversational workflow tests (spec sections 7, 8, 20, 29, 39)."""

from __future__ import annotations

import pytest

from app.agent import stream_turn
from app.ai import MockProvider
from app.connector import DemoConnector
from app.services import conversations, deployments, projects



async def _turn(session, project, conv, text, classification="development", environment_name="MCW Demo (Local)"):
    conversations.add_message(session, conv.id, "user", text)
    events = []
    async for ev in stream_turn(session=session, project=project, conversation=conv,
                                connector=DemoConnector(classification=classification), provider=MockProvider(),
                                application="MCWPCF", classification=classification,
                                environment_name=environment_name, demo=True,
                                context_version_id=None, user_text=text):
        events.append(ev)
    return events


def _block_types(events):
    return [ev.data.get("type") for ev in events if str(ev.type) == "block"]


async def test_full_form_deploy_loop(session):
    proj = projects.get_default_project(session)
    conv = conversations.create_conversation(session, proj.id)

    e = await _turn(session, proj, conv, "Create an Actuals form with level-zero descendants of Total Payroll in rows")
    assert "formPreview" in _block_types(e)
    assert "validationReport" in _block_types(e)
    assert "confirmation" in _block_types(e)

    e = await _turn(session, proj, conv, "move Entity to POV")
    assert "diff" in _block_types(e)

    e = await _turn(session, proj, conv, "show form coverage")
    assert "cubeArchitecture" in _block_types(e)
    assert "dimensionCoverage" in _block_types(e)

    e = await _turn(session, proj, conv, "deploy")
    assert "deploymentPlan" in _block_types(e)

    e = await _turn(session, proj, conv, "confirm deploy")
    assert "deploymentResult" in _block_types(e)

    deps = deployments.list_deployments(session, proj.id)
    assert deps and deps[0].success and deps[0].verified and deps[0].demo_mode


async def test_production_safeguard_requires_confirmation_phrase(session):
    out = projects.create_project(session, "Prod Safeguard Test")
    proj = projects.get_project(session, out.id)
    conv = conversations.create_conversation(session, proj.id)
    await _turn(session, proj, conv, "Create an Actuals form", classification="production", environment_name="MCW PROD")
    await _turn(session, proj, conv, "deploy", classification="production", environment_name="MCW PROD")
    # a plain confirm must NOT deploy to production
    e = await _turn(session, proj, conv, "confirm deploy", classification="production", environment_name="MCW PROD")
    assert "deploymentResult" not in _block_types(e)
    assert deployments.list_deployments(session, proj.id) == []


async def test_run_rule_flow(session):
    proj = projects.get_default_project(session)
    conv = conversations.create_conversation(session, proj.id)
    e = await _turn(session, proj, conv, "run the IR rule")
    assert "runtimePromptForm" in _block_types(e)
    e = await _turn(session, proj, conv, "/run-rule IR :: Scenario=Forecast; Entity=US Operations")
    assert "toolInvocation" in _block_types(e)
    from app.services import rule_executions
    execs = rule_executions.list_executions(session, proj.id)
    assert execs and execs[0].rule_name == "IR" and execs[0].status == "completed"


async def test_search_and_architecture(session):
    proj = projects.get_default_project(session)
    conv = conversations.create_conversation(session, proj.id)
    e = await _turn(session, proj, conv, "what cubes and dimensions exist?")
    assert "markdown" in _block_types(e)
    e = await _turn(session, proj, conv, "visualize OEP_DCSH")
    assert "cubeArchitecture" in _block_types(e)
    assert "cellIntersection" in _block_types(e)
