"""Context engine, retrieval, .epwcontext and Cube Architecture tests."""

from __future__ import annotations

import pytest

from app.architecture import service as arch
from app.artifacts import build_metadata_from_connector
from app.connector import DemoConnector
from app.context import build_context, import_context_package, validate_context_package
from app.context.retrieval import resolve_member, search_members
from app.services import context_store, projects
from app.agent.form_nlu import build_initial_spec



async def _md():
    return await build_metadata_from_connector(DemoConnector(), "MCWPCF")


async def test_build_and_retrieve_context(session):
    proj = projects.get_default_project(session)
    bundle = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    cv = context_store.persist_context(session, proj.id, bundle.application, bundle.mode, bundle.label,
                                       bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records)
    session.flush()
    assert bundle.counts["members"] == 80
    # alias exact match resolves technical name
    m = resolve_member(session, cv.id, "Base Salaries")
    assert m is not None and m.member == "Salaries" and m.retrieval_method == "alias"
    # no silent substitution: a non-existent phrase returns nothing
    assert resolve_member(session, cv.id, "Payroll Expenses XYZ") is None


async def test_context_package_export_import(session):
    proj = projects.get_default_project(session)
    bundle = await build_context(DemoConnector(), "MCWPCF", mode="quick")
    cv = context_store.persist_context(session, proj.id, bundle.application, bundle.mode, bundle.label,
                                       bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records)
    session.flush()
    from app.context import export_context_package
    _, data = export_context_package(session, cv.id)
    assert validate_context_package(data) == []
    imported = import_context_package(data)
    assert imported.application == "MCWPCF"
    assert len(imported.records) == len(bundle.records)


async def test_cube_architecture_deterministic():
    md = await _md()
    spec, *_ = build_initial_spec("Create an Actuals form with level-zero descendants of Total Payroll in rows", md, "MCWPCF")
    model = arch.get_cube_architecture(md, spec.cube, spec)
    account = next(d for d in model.dimensions if d.name == "Account")
    assert account.type == "account" and account.used_on_axis == "rows" and account.status == "selected"
    # a workforce-only dimension is custom and missing from this form
    employee = next(d for d in model.dimensions if d.name == "Employee")
    assert employee.type == "custom" and employee.status == "missing"


async def test_dimension_coverage_reports_missing():
    md = await _md()
    spec, *_ = build_initial_spec("Create an Actuals form with level-zero descendants of Total Payroll in rows", md, "MCWPCF")
    report = arch.validate_dimension_coverage(md, spec.cube, spec)
    assert not report.valid
    assert "Years" in report.missing_dimensions
    assert any(s.dimension == "Years" for s in report.suggestions)


async def test_cell_intersection_one_member_per_dimension():
    md = await _md()
    cell = arch.explain_cell_intersection(md, "OEP_FS")
    dims = {m.dimension for m in cell.members}
    assert dims == set(md.cubes["OEP_FS"].dimensions)


async def test_compare_cubes():
    md = await _md()
    cmp = arch.compare_cubes(md, "OEP_FS", "OEP_WFP")
    assert "Employee" in cmp.only_b
    assert "Currency" in cmp.only_a


async def test_cross_dimensional_size():
    md = await _md()
    spec, *_ = build_initial_spec("Create an Actuals form with level-zero descendants of Total Payroll in rows", md, "MCWPCF")
    size = arch.cross_dimensional_size(md, spec.cube, spec)
    # 7 payroll accounts x 12 months x 1 page
    assert size.total_potential_cells == 7 * 12 * 1
