"""Rule execution history persistence (spec section 32)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import RuleExecution
from ..schemas.api import RuleExecutionOut
from . import iso


def to_out(r: RuleExecution) -> RuleExecutionOut:
    return RuleExecutionOut(
        id=r.id,
        project_id=r.project_id,
        rule_name=r.rule_name,
        application=r.application,
        cube=r.cube,
        status=r.status,
        prompt_values=r.prompt_values or {},
        job_result=r.job_result,
        duration_ms=r.duration_ms,
        output=r.output,
        demo_mode=r.demo_mode,
        created_at=iso(r.created_at),
    )


def create_execution(session: Session, project_id: str, **fields) -> RuleExecution:
    r = RuleExecution(project_id=project_id, **fields)
    session.add(r)
    session.flush()
    return r


def list_executions(session: Session, project_id: str, rule_name: str | None = None) -> list[RuleExecution]:
    q = session.query(RuleExecution).filter_by(project_id=project_id)
    if rule_name:
        q = q.filter_by(rule_name=rule_name)
    return q.order_by(RuleExecution.created_at.desc()).all()
