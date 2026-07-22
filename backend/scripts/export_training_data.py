"""Export local EPM Wizard data as a fine-tuning corpus (JSONL).

Builds instruction/response pairs from three local sources:

1. **Conversations** — every active user → assistant turn pair.
2. **Artifacts** — the user request that produced a validated FormSpecification /
   RuleSpecification, paired with the spec JSON itself. These are the highest
   value examples: the output side is deterministic, Pydantic-validated EPM
   structure, not free prose.
3. **Context rule bodies** — Calculation Manager rules and templates carried by
   the active context version (LCM snapshot upload), turned into "write this
   rule" instruction pairs. This is real production calc-script/Groovy from the
   customer's own application — the strongest "EPM expert" signal available.

Every string passes through the central redactor before it is written, so
credentials never leave the machine. Output formats:

- ``chat`` (default): ``{"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}``
  — chat-style SFT, the shape most fine-tuning services (e.g. Together AI)
  ingest directly.
- ``instruct``: ``{"input": ..., "output": ...}`` — plain prompt/completion
  pairs for trainers that want instruction format.

Usage (from backend/):
    python -m scripts.export_training_data --out data/training/epm-tuning.jsonl
    python -m scripts.export_training_data --format instruct --project <project-id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.base import get_sessionmaker
from app.db.models import Artifact, ContextRecord, ContextVersion, Conversation, Message
from app.security.redaction import redact_text

# Artifact kinds whose payload is a spec worth learning to produce.
SPEC_KINDS = {"formSpec", "ruleSpec"}

SYSTEM_PROMPT = (
    "You are an Oracle EPM implementation assistant. Given a request, respond "
    "with either a clear explanation or a structured specification."
)


def _pairs_from_conversations(session: Session, project_id: str | None) -> list[tuple[str, str]]:
    query = session.query(Conversation)
    if project_id:
        query = query.filter(Conversation.project_id == project_id)
    pairs: list[tuple[str, str]] = []
    for conv in query.all():
        messages = [
            m for m in sorted(conv.messages, key=lambda m: m.created_at)
            if m.active and (m.content or "").strip()
        ]
        for prev, cur in zip(messages, messages[1:]):
            if prev.role == "user" and cur.role == "assistant":
                pairs.append((prev.content.strip(), cur.content.strip()))
    return pairs


def _pairs_from_artifacts(session: Session, project_id: str | None) -> list[tuple[str, str]]:
    query = session.query(Artifact).filter(Artifact.kind.in_(SPEC_KINDS), Artifact.payload.isnot(None))
    if project_id:
        query = query.filter(Artifact.project_id == project_id)
    pairs: list[tuple[str, str]] = []
    for artifact in query.all():
        prompt = None
        if artifact.source_message_id:
            source = session.get(Message, artifact.source_message_id)
            if source is not None and (source.content or "").strip():
                prompt = source.content.strip()
        if prompt is None:
            prompt = f"Generate the {artifact.kind} specification for '{artifact.name}'."
        spec_json = json.dumps(artifact.payload, indent=2, sort_keys=True)
        pairs.append((prompt, spec_json))
    return pairs


_MIN_RULE_BODY_CHARS = 40


def _pairs_from_context_rules(session: Session, project_id: str | None) -> list[tuple[str, str]]:
    """Rule/template bodies from ACTIVE context versions → instruction pairs.

    Only active versions are read so retired context generations don't flood
    the corpus; the cross-source dedupe still drops any survivors.
    """
    query = session.query(ContextRecord).join(
        ContextVersion, ContextRecord.context_version_id == ContextVersion.id
    ).filter(ContextVersion.active.is_(True), ContextRecord.kind.in_(("rule", "template")))
    if project_id:
        query = query.filter(ContextRecord.project_id == project_id)
    pairs: list[tuple[str, str]] = []
    for record in query.all():
        data = record.data or {}
        body = (data.get("body") or "").strip()
        if len(body) < _MIN_RULE_BODY_CHARS or data.get("bodyTruncated"):
            continue
        kind = "Calculation Manager template" if record.kind == "template" else "business rule"
        script = {"groovy": "Groovy", "calcscript": "calc script"}.get(data.get("scriptType"), "calc script")
        prompt = f"Write the Oracle Planning {script} {kind} '{record.name}'"
        if record.cube:
            prompt += f" for cube {record.cube}"
        prompts = data.get("runtimePrompts") or []
        if prompts:
            prompt += f", using runtime prompts {', '.join(prompts)}"
        pairs.append((prompt + ".", body))
    return pairs


def _to_record(prompt: str, completion: str, fmt: str) -> dict:
    prompt, completion = redact_text(prompt), redact_text(completion)
    if fmt == "chat":
        return {"messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": completion},
        ]}
    return {"input": prompt, "output": completion}


def export(out_path: Path, fmt: str = "chat", project_id: str | None = None,
           session: Session | None = None) -> dict:
    """Write the JSONL corpus; returns summary counts."""
    owns_session = session is None
    if owns_session:
        session = get_sessionmaker()()
    try:
        conv_pairs = _pairs_from_conversations(session, project_id)
        artifact_pairs = _pairs_from_artifacts(session, project_id)
        rule_pairs = _pairs_from_context_rules(session, project_id)
    finally:
        if owns_session:
            session.close()

    seen: set[str] = set()
    records: list[dict] = []
    for prompt, completion in conv_pairs + artifact_pairs + rule_pairs:
        digest = hashlib.sha256(f"{prompt}\x00{completion}".encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        records.append(_to_record(prompt, completion, fmt))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "examples": len(records),
        "fromConversations": len(conv_pairs),
        "fromArtifacts": len(artifact_pairs),
        "fromContextRules": len(rule_pairs),
        "duplicatesDropped": len(conv_pairs) + len(artifact_pairs) + len(rule_pairs) - len(records),
        "path": str(out_path),
        "format": fmt,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/training/epm-tuning.jsonl", help="output JSONL path")
    parser.add_argument("--format", choices=["chat", "instruct"], default="chat")
    parser.add_argument("--project", default=None, help="limit to one project id")
    args = parser.parse_args()

    summary = export(Path(args.out), fmt=args.format, project_id=args.project)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
