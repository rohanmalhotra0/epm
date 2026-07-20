"""Helpers that build typed inline chat blocks (spec section 8)."""

from __future__ import annotations

from ..db.base import new_id
from ..schemas.chat import ChatAction, ChatBlock, ChatBlockType, ProcessStep, ProcessStepState
from ..schemas.deployment import DeploymentPlan, DeploymentReport
from ..schemas.form_preview import FormPreview
from ..schemas.form_spec import FormSpecification
from ..schemas.validation import ValidationReport


def _block(kind: ChatBlockType, data: dict) -> ChatBlock:
    return ChatBlock(id=new_id(), type=kind, data=data)


def markdown(text: str) -> ChatBlock:
    return _block(ChatBlockType.markdown, {"text": text})


def code(text: str, language: str = "text") -> ChatBlock:
    return _block(ChatBlockType.code, {"code": text, "language": language})


def process_steps(steps: list[ProcessStep]) -> ChatBlock:
    return _block(ChatBlockType.process_steps, {"steps": [s.model_dump(by_alias=True) for s in steps]})


def action(key: str, label: str, value: str, style: str = "secondary") -> ChatAction:
    return ChatAction(key=key, label=label, value=value, style=style)


def confirmation(prompt: str, actions: list[ChatAction], detail: str | None = None, severity: str = "info") -> ChatBlock:
    return _block(ChatBlockType.confirmation, {
        "prompt": prompt, "detail": detail, "severity": severity,
        "actions": [a.model_dump(by_alias=True) for a in actions],
    })


def form_preview(preview: FormPreview) -> ChatBlock:
    return _block(ChatBlockType.form_preview, preview.model_dump(by_alias=True))


def form_specification(spec: FormSpecification) -> ChatBlock:
    return _block(ChatBlockType.form_specification, {"spec": spec.model_dump(by_alias=True, exclude_none=True)})


def report_preview(preview) -> ChatBlock:
    return _block(ChatBlockType.report_preview, preview.model_dump(by_alias=True))


def report_specification(spec, preview=None) -> ChatBlock:
    data: dict = {"spec": spec.model_dump(by_alias=True, exclude_none=True)}
    if preview is not None:
        data["preview"] = preview.model_dump(by_alias=True)
    return _block(ChatBlockType.report_specification, data)


def validation_report(report: ValidationReport) -> ChatBlock:
    return _block(ChatBlockType.validation_report, report.model_dump(by_alias=True))


def deployment_plan(plan: DeploymentPlan) -> ChatBlock:
    return _block(ChatBlockType.deployment_plan, plan.model_dump(by_alias=True))


def deployment_progress(plan: DeploymentPlan) -> ChatBlock:
    return _block(ChatBlockType.deployment_progress, plan.model_dump(by_alias=True))


def deployment_result(report: DeploymentReport) -> ChatBlock:
    return _block(ChatBlockType.deployment_result, report.model_dump(by_alias=True))


def diff(title: str, before: str, after: str, language: str = "json") -> ChatBlock:
    return _block(ChatBlockType.diff, {"title": title, "before": before, "after": after, "language": language})


def member_search_results(query: str, matches: list[dict]) -> ChatBlock:
    return _block(ChatBlockType.member_search_results, {"query": query, "matches": matches})


def context_summary(data: dict) -> ChatBlock:
    return _block(ChatBlockType.context_summary, data)


def runtime_prompt_form(data: dict) -> ChatBlock:
    return _block(ChatBlockType.runtime_prompt_form, data)


def connection_status(data: dict) -> ChatBlock:
    return _block(ChatBlockType.connection_status, data)


def tool_invocation(data: dict) -> ChatBlock:
    return _block(ChatBlockType.tool_invocation, data)


def error_diagnostics(data: dict) -> ChatBlock:
    return _block(ChatBlockType.error_diagnostics, data)


def downloadable_file(data: dict) -> ChatBlock:
    return _block(ChatBlockType.downloadable_file, data)


def spreadsheet_preview(data: dict) -> ChatBlock:
    return _block(ChatBlockType.spreadsheet_preview, data)


def snapshot_summary(data: dict) -> ChatBlock:
    return _block(ChatBlockType.snapshot_summary, data)


def rule_preview(data: dict) -> ChatBlock:
    return _block(ChatBlockType.rule_preview, data)


def grounding_sources(data: dict) -> ChatBlock:
    """RAG provenance: {"query", "purpose", "chunks": [GroundingChunk dumps]}."""
    return _block(ChatBlockType.grounding_sources, data)


def steps(*labels: str) -> list[ProcessStep]:
    return [ProcessStep(key=f"s{i}", label=label) for i, label in enumerate(labels)]


def mark_step(process: list[ProcessStep], index: int, state: ProcessStepState) -> None:
    if 0 <= index < len(process):
        process[index].state = state
