"""Training-data exporter: pairing, artifact specs, redaction, dedupe."""

from __future__ import annotations

import json

from app.db.models import Artifact, Conversation, Message, Project
from scripts.export_training_data import export


def _seed(session) -> str:
    project = Project(name="Train Me")
    session.add(project)
    session.flush()
    conv = Conversation(project_id=project.id, title="t")
    session.add(conv)
    session.flush()
    m1 = Message(conversation_id=conv.id, role="user", content="Create an Actuals form")
    m2 = Message(conversation_id=conv.id, role="assistant", content="Here is the form preview.")
    m3 = Message(conversation_id=conv.id, role="user", content="my password is Hunter2secret!")
    m4 = Message(conversation_id=conv.id, role="assistant", content="I redacted that.")
    session.add_all([m1, m2, m3, m4])
    session.flush()
    session.add(Artifact(
        project_id=project.id, kind="formSpec", name="Actuals",
        payload={"name": "Actuals", "rows": ["Total Payroll"]},
        source_message_id=m1.id,
    ))
    session.flush()
    return project.id


def test_export_watsonx_format(tmp_path, session):
    project_id = _seed(session)
    out = tmp_path / "corpus.jsonl"
    summary = export(out, fmt="watsonx", project_id=project_id, session=session)
    records = [json.loads(line) for line in out.read_text().splitlines()]

    assert summary["examples"] == len(records) == 3  # 2 turn pairs + 1 artifact spec
    assert {"input", "output"} <= set(records[0])
    spec_records = [r for r in records if r["input"] == "Create an Actuals form" and "Total Payroll" in r["output"]]
    assert spec_records, "artifact spec pair missing"


def test_export_chat_format_and_redaction(tmp_path, session):
    project_id = _seed(session)
    out = tmp_path / "chat.jsonl"
    export(out, fmt="chat", project_id=project_id, session=session)
    text = out.read_text()
    records = [json.loads(line) for line in text.splitlines()]

    assert all(r["messages"][0]["role"] == "system" for r in records)
    assert all(r["messages"][1]["role"] == "user" for r in records)
    assert "Hunter2secret!" not in text  # pasted credential never reaches the corpus


def test_export_dedupes(tmp_path, session):
    project_id = _seed(session)
    out1, out2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    first = export(out1, project_id=project_id, session=session)
    second = export(out2, project_id=project_id, session=session)
    assert first["examples"] == second["examples"]
    assert second["duplicatesDropped"] == 0
