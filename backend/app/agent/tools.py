"""Tool framework (spec section 36): narrow, typed, allowlisted operations.

Every executable action maps to a named handler here — there is no generic
command surface for the model. Handlers delegate to the connector boundary and
the deterministic artifact engine, both of which validate their own arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from sqlalchemy.orm import Session

from ..artifacts.metadata import TenantMetadata, build_metadata_from_connector
from ..connector.base import EpmConnector
from ..connector.errors import ConnectorError, ErrorCategory
from ..db.models import Project
from ..schemas.common import OperationClass
from ..schemas.tools import ToolCall, ToolResult, ToolSpec
from ..services import context_store


@dataclass
class ToolContext:
    session: Session
    project: Project
    connector: EpmConnector
    application: str
    context_version_id: str | None = None
    conversation_id: str | None = None
    _metadata: TenantMetadata | None = field(default=None, repr=False)

    async def metadata(self) -> TenantMetadata:
        if self._metadata is None:
            if self.context_version_id:
                self._metadata = context_store.build_tenant_metadata(self.session, self.context_version_id)
                if not self._metadata.members:  # empty context -> fall back to live connector
                    self._metadata = await build_metadata_from_connector(self.connector, self.application)
            else:
                self._metadata = await build_metadata_from_connector(self.connector, self.application)
        return self._metadata


# --- Tool catalog (spec section 36) -----------------------------------------

TOOL_SPECS: dict[str, ToolSpec] = {
    "list_applications": ToolSpec(name="list_applications", description="List Planning applications.",
                                  operation_class=OperationClass.read_only),
    "list_cubes": ToolSpec(name="list_cubes", description="List cubes/plan types for an application.",
                           operation_class=OperationClass.read_only),
    "list_dimensions": ToolSpec(name="list_dimensions", description="List dimensions for an application.",
                                operation_class=OperationClass.read_only),
    "search_members": ToolSpec(name="search_members", description="Search members by name/alias.",
                               operation_class=OperationClass.read_only),
    "list_forms": ToolSpec(name="list_forms", description="List data forms.",
                           operation_class=OperationClass.read_only),
    "get_form": ToolSpec(name="get_form", description="Get a form definition.",
                         operation_class=OperationClass.read_only),
    "list_rules": ToolSpec(name="list_rules", description="List business rules.",
                           operation_class=OperationClass.read_only),
    "get_rule": ToolSpec(name="get_rule", description="Get a rule definition.",
                         operation_class=OperationClass.read_only),
    "get_variables": ToolSpec(name="get_variables", description="List substitution/user variables.",
                              operation_class=OperationClass.read_only),
    "validate_form_spec": ToolSpec(name="validate_form_spec", description="Validate a FormSpecification.",
                                   operation_class=OperationClass.read_only),
    "preview_form": ToolSpec(name="preview_form", description="Build a deterministic form preview.",
                             operation_class=OperationClass.read_only),
    "build_form_package": ToolSpec(name="build_form_package", description="Build a deterministic import package.",
                                   operation_class=OperationClass.read_only),
    "run_business_rule": ToolSpec(name="run_business_rule", description="Run a business rule (approval required).",
                                  operation_class=OperationClass.execution, read_only=False,
                                  modifies_oracle=True, requires_approval=True),
    "import_snapshot": ToolSpec(name="import_snapshot", description="Import an artifact package (approval required).",
                                operation_class=OperationClass.modifying, read_only=False,
                                modifies_oracle=True, requires_approval=True),
    "verify_form": ToolSpec(name="verify_form", description="Verify a form exists after deployment.",
                            operation_class=OperationClass.read_only),
}


async def run_tool(ctx: ToolContext, call: ToolCall) -> ToolResult:
    spec = TOOL_SPECS.get(call.name)
    if spec is None:
        return ToolResult(name=call.name, ok=False, error=f"Unknown tool '{call.name}'",
                          error_category="security")
    handler = _HANDLERS.get(call.name)
    start = perf_counter()
    try:
        data = await handler(ctx, call.arguments or {})
        return ToolResult(name=call.name, ok=True, data=data, operation_class=spec.operation_class,
                          duration_ms=int((perf_counter() - start) * 1000))
    except ConnectorError as exc:
        return ToolResult(name=call.name, ok=False, error=exc.message, error_category=exc.category.value,
                          operation_class=spec.operation_class)
    except Exception as exc:  # normalise everything else
        return ToolResult(name=call.name, ok=False, error=str(exc),
                          error_category=ErrorCategory.artifact_generation.value,
                          operation_class=spec.operation_class)


# --- handlers ---------------------------------------------------------------


async def _list_applications(ctx: ToolContext, _args: dict) -> dict:
    return {"applications": [a.model_dump(by_alias=True) for a in await ctx.connector.list_applications()]}


async def _list_cubes(ctx: ToolContext, _args: dict) -> dict:
    return {"cubes": [c.model_dump(by_alias=True) for c in await ctx.connector.list_cubes(ctx.application)]}


async def _list_dimensions(ctx: ToolContext, _args: dict) -> dict:
    return {"dimensions": [d.model_dump(by_alias=True) for d in await ctx.connector.list_dimensions(ctx.application)]}


async def _search_members(ctx: ToolContext, args: dict) -> dict:
    res = await ctx.connector.search_members(ctx.application, args.get("query", ""),
                                             dimension=args.get("dimension"), limit=int(args.get("limit", 25)))
    return {"members": [m.model_dump(by_alias=True) for m in res]}


async def _list_forms(ctx: ToolContext, _args: dict) -> dict:
    return {"forms": [f.model_dump(by_alias=True) for f in await ctx.connector.list_forms(ctx.application)]}


async def _get_form(ctx: ToolContext, args: dict) -> dict:
    form = await ctx.connector.get_form(ctx.application, args["name"])
    return {"form": form.model_dump(by_alias=True) if form else None}


async def _list_rules(ctx: ToolContext, _args: dict) -> dict:
    return {"rules": [r.model_dump(by_alias=True) for r in await ctx.connector.list_rules(ctx.application)]}


async def _get_rule(ctx: ToolContext, args: dict) -> dict:
    rule = await ctx.connector.get_rule(ctx.application, args["name"])
    return {"rule": rule.model_dump(by_alias=True) if rule else None}


async def _get_variables(ctx: ToolContext, _args: dict) -> dict:
    return {"variables": [v.model_dump(by_alias=True) for v in await ctx.connector.get_variables(ctx.application)]}


async def _validate_form_spec(ctx: ToolContext, args: dict) -> dict:
    from ..artifacts.validation import validate_form
    from ..schemas.form_spec import FormSpecification
    spec = FormSpecification.model_validate(args["spec"])
    report = validate_form(spec, await ctx.metadata())
    return {"report": report.model_dump(by_alias=True)}


async def _preview_form(ctx: ToolContext, args: dict) -> dict:
    from ..artifacts.preview import build_preview
    from ..schemas.form_spec import FormSpecification
    spec = FormSpecification.model_validate(args["spec"])
    preview = build_preview(spec, await ctx.metadata())
    return {"preview": preview.model_dump(by_alias=True)}


async def _build_form_package(ctx: ToolContext, args: dict) -> dict:
    from ..artifacts.packager import build_form_package
    from ..schemas.form_spec import FormSpecification
    spec = FormSpecification.model_validate(args["spec"])
    pkg = build_form_package(spec)
    return {"checksum": pkg["checksum"], "manifest": pkg["manifest"], "sizeBytes": len(pkg["zip"])}


async def _run_business_rule(ctx: ToolContext, args: dict) -> dict:
    job = await ctx.connector.run_business_rule(ctx.application, args.get("cube"), args["rule"],
                                                args.get("prompts", {}))
    return {"job": job.model_dump()}


async def _import_snapshot(ctx: ToolContext, args: dict) -> dict:
    job = await ctx.connector.import_snapshot(args["name"])
    return {"job": job.model_dump()}


async def _verify_form(ctx: ToolContext, args: dict) -> dict:
    form = await ctx.connector.verify_form(ctx.application, args["name"])
    return {"exists": form is not None, "form": form.model_dump(by_alias=True) if form else None}


_HANDLERS = {
    "list_applications": _list_applications,
    "list_cubes": _list_cubes,
    "list_dimensions": _list_dimensions,
    "search_members": _search_members,
    "list_forms": _list_forms,
    "get_form": _get_form,
    "list_rules": _list_rules,
    "get_rule": _get_rule,
    "get_variables": _get_variables,
    "validate_form_spec": _validate_form_spec,
    "preview_form": _preview_form,
    "build_form_package": _build_form_package,
    "run_business_rule": _run_business_rule,
    "import_snapshot": _import_snapshot,
    "verify_form": _verify_form,
}
