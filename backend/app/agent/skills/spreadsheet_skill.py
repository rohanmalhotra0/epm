"""/spreadsheet skill — conversational layer over uploaded workbook analysis.

A message carrying attachments routes here (orchestrator). The stored
deterministic ``WorkbookAnalysis`` is presented honestly (kind, columns/roles,
member counts, issues verbatim), then a confirmation offers kind-specific
actions: merge a chart of accounts into the context, render a metadata CSV,
reconcile against the tenant, build a form/report from a layout sheet (handing
off to the forms/reports workflows), plan a data load (generation only) or
explain extracted formulas/VBA. Nothing is ever executed against a tenant.
"""

from __future__ import annotations

import hashlib
import re

from ...ai.base import AIMessage
from ...artifacts.metadata import TenantMetadata
from ...db.models import Attachment
from ...schemas.chat import ChatAction
from ...schemas.deployment import FormWorkflowState
from ...schemas.form_spec import AxisMember, FormSpecification, MemberSelection
from ...schemas.report_spec import ReportGrid, ReportSpecification
from ...schemas.tools import SkillSpec
from ...services import artifacts as artifacts_svc
from ...services import attachments as attachments_svc
from ...services import context_store
from ...spreadsheet import WorkbookAnalysis
from ...spreadsheet.context_merge import merge_hierarchy_into_context
from ...spreadsheet.metadata_csv import render_metadata_csv, save_metadata_artifact
from ...spreadsheet.models import HierarchyParse, SheetAnalysis, SheetKind
from .. import blocks
from .. import outline_defaults as od
from .base import Emitter, Skill, SkillContext, SkillResult

# Anchored match plus a lenient one: "ok cancel that" used to leave the user stuck
# in a workflow whose only documented exit was the word "cancel".
_CANCEL = re.compile(r"^\s*(cancel|stop|never ?mind|abort|forget it|nvm)\b[\s.!]*$", re.I)
_MERGE = re.compile(r"\bmerge\b.*\bcontext\b", re.I)
_METADATA_CSV = re.compile(r"\bmetadata\b.*\bcsv\b|\bcsv\b.*\bmetadata\b", re.I)
_VALIDATE = re.compile(r"\bvalidate\b|\breconcile\b", re.I)
# "layout" is no longer mandatory — "create a form from this sheet", "make a form
# like this excel", or a bare "create a form" while a workbook is loaded all count.
_FORM_FROM_LAYOUT = re.compile(
    r"\b(create|build|make|generate|mimic|replicate|recreate)\b[\w \-]*\bform\b|"
    r"\bform\b[\w \-]*\b(from|like|based on|out of|mimick\w*)\b", re.I)
_REPORT_FROM_LAYOUT = re.compile(
    r"\b(create|build|make|generate|mimic|replicate|recreate)\b[\w \-]*\breport\b|"
    r"\breport\b[\w \-]*\b(from|like|based on|out of|mimick\w*)\b", re.I)
_LOAD_PLAN = re.compile(r"\bload[- ]?file plan\b|\bload plan\b|\bdata load\b", re.I)
_EXPLAIN = re.compile(r"\bexplain\b.*\b(formulas?|macros?|vba)\b", re.I)
_USE_SHEET = re.compile(r"\b(?:use|switch to|open|show|pick|select)\s+(?:the\s+)?"
                        r"(?:sheet|tab|worksheet)\s+[\"'`]?([^\"'`\n]+?)[\"'`]?\s*$", re.I)
_LIST_SHEETS = re.compile(r"\blist (the )?sheets?\b|\bwhich sheets?\b|\bwhat sheets?\b|"
                          r"\b(another|different|other) (sheet|tab)\b", re.I)

_ACTION_PATTERNS = (_CANCEL, _MERGE, _METADATA_CSV, _VALIDATE, _FORM_FROM_LAYOUT,
                    _REPORT_FROM_LAYOUT, _LOAD_PLAN, _EXPLAIN, _USE_SHEET, _LIST_SHEETS)


def matches_spreadsheet_action(text: str) -> bool:
    """True when the text is one of this skill's own commands.

    The orchestrator asks this before releasing an active spreadsheet workflow,
    rather than keeping a second copy of the vocabulary that drifts out of sync —
    "explain formulas" reads as an `explain` intent but belongs to this skill.
    """
    return any(p.search(text) for p in _ACTION_PATTERNS)


_MAX_PREVIEW_SHEETS = 3
_MAX_TABLE_ROWS = 25
_MAX_FORMULAS_SHOWN = 30
_MAX_VBA_MODULES_SHOWN = 5
_MAX_VBA_CHARS_SHOWN = 4000
_MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_KIND_LABELS = {
    SheetKind.chart_of_accounts.value: "chart of accounts",
    SheetKind.layout.value: "form layout",
    SheetKind.data_table.value: "data table",
    SheetKind.unknown.value: "unclassified",
}


class SpreadsheetSkill(Skill):
    spec = SkillSpec(
        name="/spreadsheet",
        description="Analyze uploaded spreadsheets: import a chart of accounts, build forms/reports "
                    "from layouts, reconcile against the tenant and explain formulas (never executes).",
        intent_examples=["Drop a chart of accounts spreadsheet to import it",
                         "Create a form from my spreadsheet layout",
                         "Explain the macros in this workbook"],
        required_context=False, approval_required=True,
        allowed_tools=["search_members", "validate_form_spec", "preview_form"],
    )

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        text = ctx.user_text
        wf = ctx.workflow

        if wf and _CANCEL.match(text):
            await emit.block(blocks.markdown("Cancelled. The spreadsheet workflow has ended."))
            return SkillResult(skill="spreadsheet", workflow_state="cancelled", workflow_active=False)

        if ctx.attachment_ids:
            return await self._analyze(ctx, emit, ctx.attachment_ids)

        if wf is None or not (wf.data or {}).get("attachmentId"):
            await emit.block(blocks.markdown(
                "Attach a spreadsheet (`.xlsx`, `.xlsm` or `.csv`) with the paperclip in the composer "
                "and I'll analyze it: charts of accounts can be merged into the context or rendered as "
                "a metadata CSV, layout sheets can become forms or reports, and extracted formulas/VBA "
                "can be explained. Files are parsed only — macros are never executed."))
            return SkillResult(skill="spreadsheet")

        loaded = self._load_workflow_attachment(ctx, wf)
        if loaded is None:
            await emit.block(blocks.markdown(
                "I couldn't re-load the analyzed attachment for this workflow (it may have been "
                "deleted). Upload the file again to continue."))
            return SkillResult(skill="spreadsheet", workflow_state="error", workflow_active=False)
        attachment, analysis, sheet = loaded

        if _LIST_SHEETS.search(text):
            await emit.block(blocks.markdown(_sheet_menu_markdown(analysis, sheet)))
            return _persist(wf.data)
        if (m := _USE_SHEET.search(text)) is not None:
            picked = _find_sheet(analysis, m.group(1))
            if picked is None:
                await emit.block(blocks.markdown(
                    f"There's no sheet called *{m.group(1).strip()}* in **{attachment.filename}**.\n\n"
                    + _sheet_menu_markdown(analysis, sheet)))
                return _persist(wf.data)
            data = dict(wf.data or {}) | {"sheetName": picked.name}
            await emit.block(blocks.spreadsheet_preview(_preview_data(attachment.filename, picked)))
            await emit.block(blocks.confirmation(_confirm_prompt(picked), _actions_for(picked, analysis)))
            return _persist(data)

        if _MERGE.search(text):
            return await self._merge(ctx, emit, wf, sheet)
        if _METADATA_CSV.search(text):
            return await self._metadata_csv(ctx, emit, wf, sheet)
        if _VALIDATE.search(text):
            return await self._validate(ctx, emit, wf, sheet)
        if _FORM_FROM_LAYOUT.search(text):
            return await self._form_from_layout(ctx, emit, wf, attachment, sheet)
        if _REPORT_FROM_LAYOUT.search(text):
            return await self._report_from_layout(ctx, emit, wf, attachment, sheet)
        if _LOAD_PLAN.search(text):
            return await self._load_plan(ctx, emit, wf, attachment, sheet)
        if _EXPLAIN.search(text):
            return await self._explain_formulas(ctx, emit, wf, analysis)

        # Two strikes, then let go. Re-arming the workflow on every unmatched
        # message meant an unrelated question got "the workbook is still loaded"
        # forever, with the exact word "cancel" as the only exit.
        misses = int((wf.data or {}).get("misses", 0)) + 1
        if misses >= 2:
            await emit.block(blocks.markdown(
                f"That doesn't look like it's about **{attachment.filename}**, so I've set the "
                f"workbook aside — ask me again and I'll answer it normally. To pick it back up, "
                f"re-attach the file."))
            return SkillResult(skill="spreadsheet", workflow_state="released", workflow_active=False)
        await emit.block(blocks.markdown(
            f"**{attachment.filename}** (sheet *{sheet.name}*, {_KIND_LABELS.get(str(sheet.kind), str(sheet.kind))}) "
            "is still loaded. " + _action_hint(sheet, analysis)))
        return SkillResult(skill="spreadsheet", workflow_state="actions", workflow_active=True,
                           workflow_data=dict(wf.data or {}) | {"misses": misses})

    # --- analyze (a message with attachments) --------------------------------

    async def _analyze(self, ctx: SkillContext, emit: Emitter, attachment_ids: list[str]) -> SkillResult:
        emit.set_steps(blocks.steps("Reading stored analysis", "Classifying sheets", "Preparing actions"))
        await emit.step_running(0)
        loaded: list[tuple[Attachment, WorkbookAnalysis]] = []
        missing: list[str] = []
        for attachment_id in attachment_ids:
            attachment = attachments_svc.get_attachment(ctx.session, attachment_id)
            if attachment is None:
                missing.append(attachment_id)
                continue
            loaded.append((attachment, attachments_svc.load_analysis(attachment)))
        await emit.step_done(0)
        if missing:
            await emit.block(blocks.markdown(
                "Some attachments could not be found and were skipped: "
                + ", ".join(f"`{m}`" for m in missing)))
        if not loaded:
            await emit.block(blocks.markdown("No readable attachments arrived with that message."))
            return SkillResult(skill="spreadsheet")

        await emit.step_running(1)
        attachment, analysis = loaded[0]
        primary = _primary_sheet(analysis)
        # Preview only the sheet we're going to act on. Previewing three sheets of
        # a twenty-tab workbook produced screens of text and still buried the one
        # that mattered; the summary below lists the rest in one line each.
        for att, ana in loaded:
            chosen = primary if ana is analysis else _primary_sheet(ana)
            if chosen is not None:
                await emit.block(blocks.spreadsheet_preview(_preview_data(att.filename, chosen)))
            await emit.block(blocks.markdown(
                _summary_markdown(att.filename, ana, current=chosen.name if chosen else None)))
        await emit.step_done(1)

        await emit.step_running(2)
        data = {"attachmentId": attachment.id, "attachmentIds": [a.id for a, _ in loaded],
                "sheetName": primary.name if primary else None, "phase": "actions"}
        result = _persist(data)
        if primary is None or primary.kind == SheetKind.unknown.value:
            await emit.block(blocks.markdown(
                "I couldn't classify this file as a chart of accounts, a form layout or a data table, "
                "so no import actions are available. The issues above say exactly why. If it should be "
                "a chart of accounts, make sure it has *Member* and *Parent* columns (or Level 1..N "
                "columns); a form layout needs period column headers (Jan, Feb, Q1…) over a label column."))
            if _has_formulas(analysis):
                await emit.block(blocks.confirmation(
                    "The workbook does contain extracted formulas/VBA I can explain.",
                    [blocks.action("explain", "Explain formulas", "explain formulas"),
                     blocks.action("cancel", "Cancel", "cancel", "ghost")]))
            else:
                result = SkillResult(skill="spreadsheet")
        else:
            # The upload turn used to discard ctx.user_text entirely, so "create a
            # form that mimics this sheet" became a wall of analysis and a load-plan
            # button. If they already said what they want, just do it.
            if _FORM_FROM_LAYOUT.search(ctx.user_text) and _axes_source(primary) is not None:
                await emit.step_done(2)
                return await self._form_from_layout(ctx, emit, None, attachment, primary, data)
            if _REPORT_FROM_LAYOUT.search(ctx.user_text) and _axes_source(primary) is not None:
                await emit.step_done(2)
                return await self._report_from_layout(ctx, emit, None, attachment, primary, data)
            if str(primary.kind) == SheetKind.data_table.value:
                await emit.block(blocks.markdown(
                    "_Data loads are **generation only**: I can draft an EPM Automate-style "
                    "load-file plan, but I never execute loads or touch the tenant._"))
            await emit.block(blocks.confirmation(
                _confirm_prompt(primary), _actions_for(primary, analysis),
                severity="info"))
        await emit.step_done(2)
        return result

    # --- CoA actions ---------------------------------------------------------

    async def _merge(self, ctx: SkillContext, emit: Emitter, wf, sheet: SheetAnalysis) -> SkillResult:
        hierarchy = _require_hierarchy(sheet)
        if hierarchy is None:
            await emit.block(blocks.markdown(
                f"Sheet *{sheet.name}* has no parsed hierarchy to merge — it was classified as "
                f"{_KIND_LABELS.get(str(sheet.kind), str(sheet.kind))}."))
            return _persist(wf.data)
        dimension = hierarchy.dimension_guess
        emit.set_steps(blocks.steps("Loading hierarchy", "Merging into context", "Activating version"))
        await emit.step_running(0)
        active_before = context_store.get_active_context(ctx.session, ctx.project.id)
        before_members = (active_before.counts or {}).get("members", 0) if active_before else 0
        await emit.step_done(0)

        await emit.step_running(1)
        cv = merge_hierarchy_into_context(ctx.session, ctx.project.id, hierarchy, dimension)
        ctx.session.flush()
        await emit.step_done(1)
        await emit.step_running(2)
        await emit.step_done(2)

        after_members = (cv.counts or {}).get("members", 0)
        await emit.block(blocks.markdown(
            f"Merged **{len(hierarchy.members)}** `{dimension}` members from the spreadsheet into "
            f"the project context.\n\n"
            f"- New context version: **{cv.label}** (mode `imported`) — **now active**\n"
            f"- Previous version: {active_before.label if active_before else 'none (this is the first context)'}\n"
            f"- Members: {before_members} → {after_members}\n\n"
            "Existing versions were not modified — merging always creates a new version, so this "
            "is fully auditable and reversible by re-activating an earlier version."))
        await emit.block(blocks.diff(
            "Member counts",
            f"members: {before_members}", f"members: {after_members}", language="text"))
        if hierarchy.issues:
            await emit.block(blocks.markdown(
                "**Parse issues carried over from the sheet** (these members were merged as parsed):\n\n"
                + "\n".join(f"- {i}" for i in hierarchy.issues)))
        return _persist(wf.data)

    async def _metadata_csv(self, ctx: SkillContext, emit: Emitter, wf, sheet: SheetAnalysis) -> SkillResult:
        hierarchy = _require_hierarchy(sheet)
        if hierarchy is None:
            await emit.block(blocks.markdown(
                f"Sheet *{sheet.name}* has no parsed hierarchy — a metadata CSV needs a chart of accounts."))
            return _persist(wf.data)
        dimension = hierarchy.dimension_guess
        content = render_metadata_csv(hierarchy, dimension)
        artifact = save_metadata_artifact(ctx.session, ctx.project.id, hierarchy, dimension)
        ctx.session.flush()
        await emit.prose(
            f"Rendered a deterministic Oracle Planning metadata-import CSV for **{dimension}** "
            f"({len(hierarchy.members)} members, checksum `{artifact.checksum[:12]}`).\n\n")
        await emit.block(blocks.downloadable_file({
            "filename": artifact.name, "artifactId": artifact.id, "mediaType": "text/csv",
            "sizeBytes": len(content.encode("utf-8")), "checksum": artifact.checksum,
        }))
        await emit.block(blocks.markdown(
            "**How to load it** (you run these — EPM Wizard never executes anything):\n\n"
            "1. Create/verify a metadata import job for the "
            f"`{dimension}` dimension in Planning (Application → Overview → Dimensions → Import).\n"
            "2. Upload and import with EPM Automate:\n\n"
            "```shell\n"
            f"epmautomate uploadFile \"{artifact.name}\" inbox\n"
            f"epmautomate importMetadata \"<IMPORT_JOB>\" {artifact.name} errorFile=\"errors.zip\"\n"
            "epmautomate refreshCube <DATABASE_REFRESH_JOB>\n"
            "```\n\n"
            "Ask `/epm-automate` for a full script with login, logging and error handling."))
        return _persist(wf.data)

    # --- validate against tenant --------------------------------------------

    async def _validate(self, ctx: SkillContext, emit: Emitter, wf, sheet: SheetAnalysis) -> SkillResult:
        hierarchy = _require_hierarchy(sheet)
        if hierarchy is None:
            await emit.block(blocks.markdown(
                f"Sheet *{sheet.name}* has no parsed hierarchy — validation needs a chart of accounts."))
            return _persist(wf.data)
        emit.set_steps(blocks.steps("Loading tenant metadata", "Reconciling members", "Writing reconciliation CSV"))
        await emit.step_running(0)
        md = await ctx.tool_ctx.metadata()
        await emit.step_done(0)

        await emit.step_running(1)
        dimension, dim_note = _match_dimension(md, hierarchy)
        rows: list[dict] = []
        counts = {"exact": 0, "caseInsensitive": 0, "alias": 0, "missing": 0, "parentMismatch": 0}
        for member in hierarchy.members:
            resolved = _resolve_identifier(md, member.name, dimension=dimension)
            if resolved is None:
                counts["missing"] += 1
                rows.append({"member": member.name, "status": "missing", "matched": "",
                             "sheetParent": member.parent or "", "tenantParent": "", "parentMatch": ""})
                continue
            rec, _dim, method = resolved
            counts[method] += 1
            parent_match = ""
            if member.parent and rec.parent:
                parent_match = "yes" if rec.parent.lower() == member.parent.lower() else "no"
            elif member.parent or rec.parent:
                parent_match = "no"
            if parent_match == "no":
                counts["parentMismatch"] += 1
            rows.append({"member": member.name, "status": method, "matched": rec.name,
                         "sheetParent": member.parent or "", "tenantParent": rec.parent or "",
                         "parentMatch": parent_match})
        await emit.step_done(1)

        await emit.step_running(2)
        csv_content = _reconciliation_csv(rows)
        artifact = artifacts_svc.save_artifact(
            ctx.session, ctx.project.id, "reconciliationCsv", f"{dimension}_reconciliation.csv",
            content=csv_content, checksum=hashlib.sha256(csv_content.encode("utf-8")).hexdigest(),
            metadata={"dimension": dimension, "counts": counts, "memberCount": len(rows)},
            source_conversation_id=ctx.conversation.id)
        ctx.session.flush()
        await emit.step_done(2)

        matched = counts["exact"] + counts["caseInsensitive"] + counts["alias"]
        lines = [
            f"### Reconciliation against **{ctx.application}** — dimension `{dimension}`", "",
        ]
        if dim_note:
            lines += [dim_note, ""]
        lines += [
            f"**{matched} of {len(rows)}** spreadsheet members exist in the tenant "
            f"(exact: {counts['exact']}, case-insensitive: {counts['caseInsensitive']}, "
            f"alias: {counts['alias']}); **{counts['missing']} missing**, "
            f"**{counts['parentMismatch']} parent mismatch(es)** among the matched members.", "",
            "| Member | Status | Matched | Sheet parent | Tenant parent | Parent match |",
            "|---|---|---|---|---|---|",
        ]
        for row in rows[:_MAX_TABLE_ROWS]:
            lines.append(f"| {row['member']} | {row['status']} | {row['matched'] or '—'} "
                         f"| {row['sheetParent'] or '—'} | {row['tenantParent'] or '—'} "
                         f"| {row['parentMatch'] or '—'} |")
        if len(rows) > _MAX_TABLE_ROWS:
            lines.append(f"\n_Table truncated to the first {_MAX_TABLE_ROWS} of {len(rows)} members — "
                         "the CSV below contains every row._")
        await emit.block(blocks.markdown("\n".join(lines)))
        await emit.block(blocks.downloadable_file({
            "filename": artifact.name, "artifactId": artifact.id, "mediaType": "text/csv",
            "sizeBytes": len(csv_content.encode("utf-8")), "checksum": artifact.checksum,
        }))
        return _persist(wf.data)

    # --- layout -> form / report handoff ------------------------------------

    async def _form_from_layout(self, ctx: SkillContext, emit: Emitter, wf,
                                attachment: Attachment, sheet: SheetAnalysis,
                                data: dict | None = None) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        built = _build_axes_from_layout(md, sheet)
        if built is None:
            await emit.block(blocks.markdown(_layout_failure_markdown(sheet)))
            return _persist(data if wf is None else wf.data)
        rows_axis, columns_axis, pov_axes, cube, notes, unresolved = built
        spec = FormSpecification(
            name=_artifact_name(attachment.filename, sheet.name, "Form"),
            description=f"Built from layout sheet '{sheet.name}' of {attachment.filename}",
            application=ctx.application, cube=cube,
            pov=pov_axes, rows=[rows_axis], columns=[columns_axis],
        )
        await self._emit_layout_resolution(emit, notes, unresolved)
        forms_skill = _registry_skill("forms")
        await forms_skill._emit_preview(ctx, emit, md, spec)
        if ctx.workflow is not None:
            ctx.workflow.active = False  # hand the conversation to the forms workflow
        return SkillResult(
            skill="forms", workflow_state=FormWorkflowState.preview_ready.value,
            workflow_data={"spec": spec.model_dump(by_alias=True), "phase": "preview"},
            workflow_active=True)

    async def _report_from_layout(self, ctx: SkillContext, emit: Emitter, wf,
                                  attachment: Attachment, sheet: SheetAnalysis,
                                  data: dict | None = None) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        built = _build_axes_from_layout(md, sheet)
        if built is None:
            await emit.block(blocks.markdown(_layout_failure_markdown(sheet)))
            return _persist(data if wf is None else wf.data)
        rows_axis, columns_axis, pov_axes, cube, notes, unresolved = built
        spec = ReportSpecification(
            name=_artifact_name(attachment.filename, sheet.name, "Report"),
            description=f"Built from layout sheet '{sheet.name}' of {attachment.filename}",
            application=ctx.application, cube=cube,
            grids=[ReportGrid(name=sheet.name[:80] or "Grid", pov=pov_axes,
                              rows=[rows_axis], columns=[columns_axis])],
        )
        await self._emit_layout_resolution(emit, notes, unresolved)
        reports_skill = _registry_skill("reports")
        await reports_skill._emit_preview(ctx, emit, md, spec)
        if ctx.workflow is not None:
            ctx.workflow.active = False  # hand the conversation to the reports workflow
        return SkillResult(
            skill="reports", workflow_state="preview",
            workflow_data={"spec": spec.model_dump(by_alias=True), "phase": "preview"},
            workflow_active=True)

    async def _emit_layout_resolution(self, emit: Emitter, notes: list[str], unresolved: list[str]) -> None:
        await emit.prose("Here's how I mapped the layout sheet:\n\n"
                         + "\n".join(f"- {n}" for n in notes) + "\n\n")
        if unresolved:
            await emit.block(blocks.markdown(
                "**Labels I could not resolve against the tenant** (left off the artifact, not guessed):\n\n"
                + "\n".join(f"- {u}" for u in unresolved)))

    # --- data table ----------------------------------------------------------

    async def _load_plan(self, ctx: SkillContext, emit: Emitter, wf,
                         attachment: Attachment, sheet: SheetAnalysis) -> SkillResult:
        table = sheet.data_table
        if table is None:
            await emit.block(blocks.markdown(
                f"Sheet *{sheet.name}* was not classified as a data table, so there is no load plan to build."))
            return _persist(wf.data)
        load_name = re.sub(r"\.(xlsx|xlsm)$", ".csv", attachment.filename, flags=re.I)
        await emit.block(blocks.markdown("\n".join([
            "### Data load-file plan (generated only — EPM Wizard never executes loads)",
            "",
            f"**Source:** sheet *{sheet.name}* of **{attachment.filename}** — "
            f"{table.row_count} data row(s), label column `{table.label_column or 'first column'}`, "
            f"period columns: {', '.join(f'`{p}`' for p in table.period_columns) or 'none'}.",
            "",
            "1. Export the sheet as CSV with one header row (label column + period columns).",
            "2. Create/verify a Data Management (or Data Integration) import job that maps the label "
            "column to your dimension and the period columns to Period members.",
            "3. Upload and load with EPM Automate:",
            "",
            "```shell",
            "epmautomate login \"<USERNAME>\" \"<PASSWORD.epw>\" \"<EPM_URL>\"",
            f"epmautomate uploadFile \"{load_name}\" inbox",
            f"epmautomate importData \"<IMPORT_JOB>\" {load_name} errorFile=\"errors.zip\"",
            "epmautomate downloadFile \"errors.zip\"",
            "epmautomate logout",
            "```",
            "",
            "4. Review `errors.zip` and the Jobs console for rejected rows before trusting the load.",
            "",
            "_Data loads are supported as **generation only**: I draft the plan and files, you run them._",
        ])))
        return _persist(wf.data)

    # --- formulas / VBA ------------------------------------------------------

    async def _explain_formulas(self, ctx: SkillContext, emit: Emitter, wf,
                                analysis: WorkbookAnalysis) -> SkillResult:
        shown_any = False
        prompt_parts: list[str] = []
        for sheet in analysis.sheets:
            if not sheet.formulas:
                continue
            shown = sheet.formulas[:_MAX_FORMULAS_SHOWN]
            note = f" (showing {len(shown)} of {len(sheet.formulas)})" if len(shown) < len(sheet.formulas) else ""
            await emit.block(blocks.markdown(f"**Formulas — sheet *{sheet.name}***{note}:"))
            listing = "\n".join(f"{f.cell}: {f.formula}" for f in shown)
            await emit.block(blocks.code(listing, "text"))
            prompt_parts.append(f"Sheet {sheet.name} formulas:\n{listing}")
            shown_any = True
        for module in analysis.vba_modules[:_MAX_VBA_MODULES_SHOWN]:
            code = module.code[:_MAX_VBA_CHARS_SHOWN]
            note = " (truncated)" if len(module.code) > len(code) else ""
            await emit.block(blocks.markdown(
                f"**VBA module *{module.name}*** ({module.line_count} lines, secrets redacted){note}:"))
            await emit.block(blocks.code(code, "vb"))
            prompt_parts.append(f"VBA module {module.name}:\n{code}")
            shown_any = True
        if len(analysis.vba_modules) > _MAX_VBA_MODULES_SHOWN:
            await emit.block(blocks.markdown(
                f"_{len(analysis.vba_modules) - _MAX_VBA_MODULES_SHOWN} further VBA module(s) not shown._"))
        if not shown_any:
            await emit.block(blocks.markdown(
                f"**{analysis.filename}** contains no extracted formulas or VBA modules to explain."))
            return _persist(wf.data)

        system = ("You are EPM Wizard. Explain only what the spreadsheet formulas and VBA macros shown "
                  "actually do — cell references, ranges, arithmetic and procedure structure. Do not "
                  "invent business meaning beyond what the text states, and never claim anything was "
                  "executed; this code was extracted as inert text only.")
        await emit.prose("\n")
        await emit.stream_provider_text(
            ctx, [AIMessage(role="user", content="Explain these extracted spreadsheet artifacts:\n\n"
                                                 + "\n\n".join(prompt_parts)[:8000])],
            system=system)
        result = _persist(wf.data)
        result.provider_used = getattr(ctx.provider, "name", None)
        return result

    # --- helpers -------------------------------------------------------------

    def _load_workflow_attachment(
        self, ctx: SkillContext, wf
    ) -> tuple[Attachment, WorkbookAnalysis, SheetAnalysis] | None:
        data = wf.data or {}
        attachment = attachments_svc.get_attachment(ctx.session, data.get("attachmentId", ""))
        if attachment is None:
            return None
        try:
            analysis = attachments_svc.load_analysis(attachment)
        except Exception:
            return None
        sheet = next((s for s in analysis.sheets if s.name == data.get("sheetName")), None)
        sheet = sheet or _primary_sheet(analysis)
        if sheet is None:
            return None
        return attachment, analysis, sheet


# --- module helpers ----------------------------------------------------------


def _registry_skill(name: str):
    from . import get_skill  # runtime import: the registry imports this module
    return get_skill(name)


def _persist(data: dict | None) -> SkillResult:
    # Drop the miss counter: reaching here means a real action matched.
    payload = {k: v for k, v in (data or {}).items() if k != "misses"}
    return SkillResult(skill="spreadsheet", workflow_state="actions",
                       workflow_data=payload, workflow_active=True)


def _primary_sheet(analysis: WorkbookAnalysis) -> SheetAnalysis | None:
    """Best sheet to act on, not merely the leftmost one that classified.

    Tab order put a three-year-old summary tab ahead of the sheet the user was
    actually looking at. Prefer sheets a form can be built from, then bigger
    grids, then later tabs — workbooks grow rightward as years are added.
    """
    def score(item: tuple[int, SheetAnalysis]) -> tuple:
        idx, sheet = item
        if sheet.kind == SheetKind.unknown.value:
            return (-1, 0, 0)
        buildable = 1 if _axes_source(sheet) is not None else 0
        size = 0
        if sheet.layout is not None:
            size = len(sheet.layout.row_labels) * max(1, len(sheet.layout.column_labels))
        elif sheet.data_table is not None:
            size = sheet.data_table.row_count * max(1, len(sheet.data_table.period_columns))
        elif sheet.hierarchy is not None:
            size = len(sheet.hierarchy.members)
        return (buildable, size, idx)

    if not analysis.sheets:
        return None
    best = max(enumerate(analysis.sheets), key=score)
    return best[1] if best[1].kind != SheetKind.unknown.value else analysis.sheets[0]


def _find_sheet(analysis: WorkbookAnalysis, name: str) -> SheetAnalysis | None:
    """Locate a sheet by exact, case-insensitive, then substring name match."""
    query = name.strip().strip("*_`").lower()
    if not query:
        return None
    for sheet in analysis.sheets:
        if sheet.name.lower() == query:
            return sheet
    matches = [s for s in analysis.sheets if query in s.name.lower()]
    return matches[0] if len(matches) == 1 else None


def _sheet_menu_markdown(analysis: WorkbookAnalysis, current: SheetAnalysis | None) -> str:
    lines = ["**Sheets in this workbook** — say *use sheet <name>* to switch:", ""]
    for sheet in analysis.sheets:
        kind = _KIND_LABELS.get(str(sheet.kind), str(sheet.kind))
        marker = " ← current" if current is not None and sheet.name == current.name else ""
        buildable = " · can build a form" if _axes_source(sheet) is not None else ""
        lines.append(f"- **{sheet.name}** — {kind}{buildable}{marker}")
    return "\n".join(lines)


def _has_formulas(analysis: WorkbookAnalysis) -> bool:
    return bool(analysis.vba_modules) or any(s.formulas for s in analysis.sheets)


def _require_hierarchy(sheet: SheetAnalysis) -> HierarchyParse | None:
    return sheet.hierarchy if sheet.hierarchy and sheet.hierarchy.members else None


def _sheet_issues(sheet: SheetAnalysis) -> list[str]:
    issues = list(sheet.issues)
    for part in (sheet.hierarchy, sheet.layout, sheet.data_table):
        if part is not None:
            issues.extend(part.issues)
    return issues


def _preview_data(filename: str, sheet: SheetAnalysis) -> dict:
    data = {
        "filename": filename,
        "sheetName": sheet.name,
        "kind": str(sheet.kind),
        "columns": [c.model_dump(by_alias=True) for c in sheet.columns],
        "sampleRows": [list(r) for r in sheet.sample_rows],
        "issues": _sheet_issues(sheet),
    }
    if sheet.hierarchy is not None:
        data["memberCount"] = len(sheet.hierarchy.members)
        data["dimensionGuess"] = sheet.hierarchy.dimension_guess
    return data


def _abbrev(values: list[str], limit: int) -> str:
    """`a`, `b`, `c` … +N more — long header lists are noise, not information."""
    if not values:
        return "none"
    shown = ", ".join(f"`{v}`" for v in values[:limit])
    return shown if len(values) <= limit else f"{shown} … +{len(values) - limit} more"


def _summary_markdown(filename: str, analysis: WorkbookAnalysis, current: str | None = None) -> str:
    """One line per sheet.

    This used to print every column and every issue for every sheet, which on a
    20-tab workbook buried the one fact that mattered (which sheet was picked)
    under several screens of text.
    """
    lines = [f"### Sheets in **{filename}**", ""]
    skipped: list[str] = []
    for sheet in analysis.sheets:
        if sheet.kind == SheetKind.unknown.value and sheet.name != current:
            skipped.append(sheet.name)
            continue
        kind = _KIND_LABELS.get(str(sheet.kind), str(sheet.kind))
        marker = " ← using this one" if sheet.name == current else ""
        detail = ""
        if sheet.hierarchy is not None:
            detail = (f" — {len(sheet.hierarchy.members)} members, {sheet.hierarchy.root_count} root(s), "
                      f"dimension guess `{sheet.hierarchy.dimension_guess}`")
        elif sheet.layout is not None:
            detail = (f" — {len(sheet.layout.row_labels)} row label(s) × "
                      f"{len(sheet.layout.column_labels)} column(s): "
                      f"{_abbrev(sheet.layout.column_labels, 4)}")
        elif sheet.data_table is not None:
            t = sheet.data_table
            detail = (f" — {t.row_count} row(s) × {len(t.period_columns)} period column(s): "
                      f"{_abbrev(t.period_columns, 4)}")
        lines.append(f"- **{sheet.name}** ({kind}){detail}{marker}")
        issues = [i for i in _sheet_issues(sheet) if not i.startswith("possible subtotal row")]
        subtotals = sum(1 for i in _sheet_issues(sheet) if i.startswith("possible subtotal row"))
        if subtotals:
            issues.append(f"{subtotals} possible subtotal row(s) — exclude them before loading")
        for issue in issues[:3]:
            lines.append(f"  - _{issue}_")
        if len(issues) > 3:
            lines.append(f"  - _…{len(issues) - 3} further note(s)_")
    if skipped:
        lines += ["", f"_{len(skipped)} sheet(s) couldn't be classified and are not listed: "
                      f"{', '.join(skipped[:6])}{' …' if len(skipped) > 6 else ''}._"]
    if analysis.vba_modules:
        lines += ["", f"**VBA:** {len(analysis.vba_modules)} module(s) extracted as inert, redacted "
                      "text (never executed)."]
    return "\n".join(lines).rstrip()


def _confirm_prompt(sheet: SheetAnalysis) -> str:
    kind = str(sheet.kind)
    if kind == SheetKind.chart_of_accounts.value:
        return "This looks like a chart of accounts. What would you like to do with it?"
    source = _axes_source(sheet)
    if source is not None:
        rows, cols, _ = source
        return (f"*{sheet.name}* is a {len(rows)}-row × {len(cols)}-column grid. "
                f"What would you like to build from it?")
    return "This looks like a data table. What would you like to do?"


def _actions_for(sheet: SheetAnalysis, analysis: WorkbookAnalysis) -> list[ChatAction]:
    kind = str(sheet.kind)
    cancel = blocks.action("cancel", "Cancel", "cancel", "ghost")
    if kind == SheetKind.chart_of_accounts.value:
        actions = [
            blocks.action("merge", "Merge into context", "merge into context", "primary"),
            blocks.action("csv", "Generate metadata CSV", "generate metadata csv"),
            blocks.action("validate", "Validate against tenant", "validate against tenant"),
        ]
        if _has_formulas(analysis):
            actions.append(blocks.action("explain", "Explain formulas", "explain formulas"))
        return actions + [cancel]
    actions: list[ChatAction] = []
    # A data table has row labels and period columns — everything the form builder
    # needs — so it gets the same offer a layout does, not just a load plan.
    if _axes_source(sheet) is not None:
        actions += [
            blocks.action("form", "Create a form from this sheet", "create a form from this sheet", "primary"),
            blocks.action("report", "Create a report from this sheet", "create a report from this sheet"),
        ]
    if kind == SheetKind.data_table.value:
        actions.append(blocks.action("plan", "Generate load-file plan", "generate load-file plan",
                                     "primary" if not actions else "secondary"))
    if len([s for s in analysis.sheets if s.kind != SheetKind.unknown.value]) > 1:
        actions.append(blocks.action("sheets", "Use a different sheet", "list sheets"))
    return actions + [cancel]


def _action_hint(sheet: SheetAnalysis, analysis: WorkbookAnalysis) -> str:
    kind = str(sheet.kind)
    if kind == SheetKind.chart_of_accounts.value:
        extra = ", *explain formulas*" if _has_formulas(analysis) else ""
        return ("Say *merge into context*, *generate metadata csv*, "
                f"*validate against tenant*{extra} or *cancel*.")
    options: list[str] = []
    if _axes_source(sheet) is not None:
        options += ["*create a form from this sheet*", "*create a report from this sheet*"]
    if kind == SheetKind.data_table.value:
        options.append("*generate load-file plan*")
    if len(analysis.sheets) > 1:
        options.append("*list sheets*")
    if not options:
        options.append("*explain formulas* (if any were extracted)")
    return "Say " + ", ".join(options) + " or *cancel*."


# --- identifier-first resolution ---------------------------------------------


def _resolve_identifier(md: TenantMetadata, label: str, dimension: str | None = None):
    """exact -> caseInsensitive -> alias, never fuzzy. Returns (record, dimension, method)."""
    query = label.strip()
    dims = [dimension] if dimension else list(md.members)
    for dim in dims:
        rec = md.members.get(dim, {}).get(query.lower())
        if rec is not None:
            return rec, dim, ("exact" if rec.name == query else "caseInsensitive")
    ql = query.lower()
    for dim in dims:
        for rec in md.members.get(dim, {}).values():
            if rec.alias and rec.alias.lower() == ql:
                return rec, dim, "alias"
    return None


def _match_dimension(md: TenantMetadata, hierarchy: HierarchyParse) -> tuple[str, str | None]:
    """Pick the tenant dimension to reconcile against, honestly noting the choice."""
    guess = hierarchy.dimension_guess
    for dim in md.dimensions:
        if dim.lower() == guess.lower():
            return dim, None
    # dimension name unknown: pick the dimension holding the most exact name matches
    best_dim, best_hits = None, 0
    for dim, members in md.members.items():
        hits = sum(1 for m in hierarchy.members if m.name.lower() in members)
        if hits > best_hits:
            best_dim, best_hits = dim, hits
    if best_dim:
        return best_dim, (f"_The sheet's dimension guess `{guess}` is not a tenant dimension; "
                          f"compared against `{best_dim}` ({best_hits} name matches), which fit best._")
    return guess, (f"_The sheet's dimension guess `{guess}` is not a tenant dimension and no member "
                   "names matched any dimension — every member is reported as missing._")


def _reconciliation_csv(rows: list[dict]) -> str:
    import csv
    import io
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Member", "Status", "Matched Name", "Sheet Parent", "Tenant Parent", "Parent Match"])
    for row in rows:
        writer.writerow([row["member"], row["status"], row["matched"],
                         row["sheetParent"], row["tenantParent"], row["parentMatch"]])
    return buffer.getvalue()


# --- layout -> axes ----------------------------------------------------------


_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def _axes_source(sheet: SheetAnalysis) -> tuple[list[str], list[str], list[str]] | None:
    """(row_labels, column_labels, pov_hints) from a layout *or* a data table.

    A data table carries the same three things a form needs; refusing to build
    from one was an artificial restriction, not a modelling limit.
    """
    layout = sheet.layout
    if layout is not None and layout.row_labels and layout.column_labels:
        return layout.row_labels, layout.column_labels, layout.pov_hints
    table = sheet.data_table
    if table is not None and table.row_labels and table.period_columns:
        return table.row_labels, table.period_columns, []
    return None


def _collapse_period_labels(labels: list[str]) -> tuple[list[str], str | None]:
    """Daily date columns -> the distinct months they cover.

    Planning period dimensions are monthly, so a column per calendar day has no
    intersection to map onto. Collapsing is lossy, so the note is surfaced to the
    user rather than applied silently.
    """
    months: list[str] = []
    seen: set[str] = set()
    years: set[int] = set()
    for label in labels:
        m = _ISO_DATE_RE.match(label.strip())
        if m is None:
            return labels, None  # not a date grid; leave the headers alone
        years.add(int(m.group(1)))
        name = _MONTH_ORDER[int(m.group(2)) - 1]
        if name not in seen:
            seen.add(name)
            months.append(name)
    note = (f"Columns: {len(labels)} daily column(s) collapsed to {len(months)} period "
            f"member(s) — the period dimension is monthly, so day-level columns have no "
            f"intersection to map onto")
    if len(years) > 1:
        note += (f". The sheet spans {min(years)}–{max(years)}, so Years belongs on the "
                 f"POV or pages to keep the months unambiguous")
    return months, note


def _build_axes_from_layout(md: TenantMetadata, sheet: SheetAnalysis):
    source = _axes_source(sheet)
    if source is None:
        return None
    row_labels, column_labels, pov_hints = source
    period_dim = od.find_dimension(md, "period") or "Period"

    notes: list[str] = []
    unresolved: list[str] = []

    column_labels, collapse_note = _collapse_period_labels(column_labels)
    if collapse_note:
        notes.append(collapse_note)

    # rows: resolve labels, use the dimension where most of them live
    resolutions: list[tuple[str, object, str, str]] = []  # (label, record, dim, method)
    for label in row_labels:
        resolved = _resolve_identifier(md, label)
        if resolved is None:
            unresolved.append(f"row label **{label}** — no exact name or alias match in the tenant")
        else:
            rec, dim, method = resolved
            resolutions.append((label, rec, dim, method))
    if not resolutions:
        return None
    dim_counts: dict[str, int] = {}
    for _label, _rec, dim, _method in resolutions:
        dim_counts[dim] = dim_counts.get(dim, 0) + 1
    rows_dim = max(dim_counts, key=lambda d: dim_counts[d])
    row_members: list[str] = []
    for label, rec, dim, method in resolutions:
        if dim != rows_dim:
            unresolved.append(f"row label **{label}** — matched `{rec.name}` in dimension `{dim}`, "
                              f"not the row dimension `{rows_dim}`; left off the rows")
            continue
        row_members.append(rec.name)
        if method != "exact":
            notes.append(f"Row label *{label}* resolved to `{rec.name}` via {method} match")
    if not row_members:
        return None
    rows_axis = AxisMember(dimension=rows_dim,
                           selection=MemberSelection(type="memberList", members=row_members))
    notes.insert(0, f"Rows: {len(row_members)} `{rows_dim}` member(s) from the sheet's row labels")

    # columns: detected period headers -> range when contiguous months, else memberList
    period_members: list[str] = []
    for label in column_labels:
        resolved = _resolve_identifier(md, label, dimension=period_dim)
        if resolved is None:
            unresolved.append(f"column header **{label}** — not a `{period_dim}` member in the tenant")
        else:
            period_members.append(resolved[0].name)
    if not period_members:
        return None
    month_positions = [_MONTH_ORDER.index(m) for m in period_members if m in _MONTH_ORDER]
    contiguous_months = (
        len(month_positions) == len(period_members) and len(month_positions) > 1
        and month_positions == list(range(month_positions[0], month_positions[0] + len(month_positions)))
    )
    if contiguous_months:
        columns_axis = AxisMember(dimension=period_dim, selection=MemberSelection(
            type="range", start=period_members[0], end=period_members[-1]))
        notes.append(f"Columns: contiguous months {period_members[0]}–{period_members[-1]} (range)")
    else:
        columns_axis = AxisMember(dimension=period_dim, selection=MemberSelection(
            type="memberList", members=period_members))
        notes.append(f"Columns: {period_dim} members {', '.join(period_members)}")

    # POV from hints ("Scenario: Actual" style), only when resolvable
    pov_axes: list[AxisMember] = []
    used_dims = {rows_dim, period_dim}
    for hint in pov_hints:
        value = hint.split(":", 1)[1].strip() if ":" in hint else hint.strip()
        resolved = _resolve_identifier(md, value) if value else None
        if resolved is None:
            unresolved.append(f"POV hint **{hint}** — could not resolve to a tenant member")
            continue
        rec, dim, _method = resolved
        if dim in used_dims:
            continue
        used_dims.add(dim)
        pov_axes.append(AxisMember(dimension=dim, selection=MemberSelection(type="member", member=rec.name)))
        notes.append(f"POV: `{dim}` = `{rec.name}` (from hint *{hint}*)")

    cube = next((name for name, c in md.cubes.items()
                 if rows_dim in c.dimensions and period_dim in c.dimensions), None)
    if cube is None:
        cube = next(iter(md.cubes), "OEP_FS")
        notes.append(f"Cube: `{cube}` (fallback — no cube contains both `{rows_dim}` and `{period_dim}`)")
    else:
        notes.append(f"Cube: `{cube}` (contains `{rows_dim}` and `{period_dim}`)")

    return rows_axis, columns_axis, pov_axes, cube, notes, unresolved


def _layout_failure_markdown(sheet: SheetAnalysis) -> str:
    """Say which stage failed and what would fix it — a dead end is worse than an error."""
    if _axes_source(sheet) is None:
        return (f"Sheet *{sheet.name}* doesn't have both row labels and period column headers, "
                f"so there's nothing to build a form from. It was classified as "
                f"*{_KIND_LABELS.get(str(sheet.kind), str(sheet.kind))}*. If another tab holds the "
                f"grid you want, say *use sheet <name>*.")
    row_labels, column_labels, _hints = _axes_source(sheet)
    return "\n".join([
        f"I read the grid on *{sheet.name}* ({len(row_labels)} row label(s), "
        f"{len(column_labels)} column header(s)) but couldn't match enough of it to this "
        f"application to build an artifact.",
        "",
        "Members are never guessed — a label only becomes a form row if it matches a tenant "
        "member by exact name or alias. What usually fixes this:",
        "",
        "- the sheet describes a different application than the one loaded;",
        "- the labels are business descriptions (*J.P. Morgan Concentration (..6967)*) rather than "
        "member names — map them to members first, or import them as a chart of accounts;",
        "- the right grid is on another tab — say *use sheet <name>*.",
    ])


def _artifact_name(filename: str, sheet_name: str, suffix: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", filename).strip() or sheet_name
    return f"{stem} {suffix}"[:80]
