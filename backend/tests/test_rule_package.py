"""Deterministic Calc Manager rule package: HBRRepo XML rendering, reproducible
zip, snapshot-parser round-trip, and the _save_draft package artifact."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from defusedxml import ElementTree as DET

from app.agent import stream_turn
from app.ai import MockProvider
from app.artifacts.rule_package import GENERATOR, build_rule_package, render_rule_xml
from app.connector import DemoConnector
from app.context.snapshot import _parse_rule_file
from app.schemas.rule_spec import (
    RuleSpecification,
    RuleType,
    RuntimePrompt,
    RuntimePromptType,
)
from app.services import artifacts as artifacts_svc
from app.services import conversations, projects

_SCRIPT = (
    "/* copies Working to Final */\n"
    'String cube = "OEP_FS"\n'
    "if (1 < 2 && true) { return cube }\n"
)


def _spec(**overrides) -> RuleSpecification:
    base = dict(
        name="Copy Working to Final",
        type=RuleType.business_rule,
        application="MCW_PCF",
        cube="OEP_FS",
        purpose="Promote working data to final",
        runtime_prompts=[
            RuntimePrompt(name="OCF_Entity", prompt_text="Select Entity",
                          type=RuntimePromptType.member, dimension="Entity"),
            RuntimePrompt(name="OCF_Version", type=RuntimePromptType.member,
                          dimension="Version", default_value="OEP_Working"),
        ],
    )
    base.update(overrides)
    return RuleSpecification(**base)


def _rule_file_from_zip(data: bytes) -> tuple[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        rule_paths = [n for n in zf.namelist() if n != "manifest.json"]
        assert len(rule_paths) == 1
        return rule_paths[0], zf.read(rule_paths[0]).decode("utf-8")


# --- XML rendering -------------------------------------------------------------


def test_render_rule_xml_hbrrepo_shape():
    xml = render_rule_xml(_spec(), _SCRIPT, "groovy")
    assert xml.startswith("<?xml version = '1.0' encoding = 'UTF-8'?>\n")
    root = DET.fromstring(xml)
    assert root.tag == "HBRRepo"
    assert [c.tag for c in root] == ["variables", "rulesets", "rules", "templates"]

    variables = root.find("variables")
    assert [v.get("name") for v in variables] == ["OCF_Entity", "OCF_Version"]
    entity = variables[0]
    assert entity.get("type") == "member" and entity.get("usage") == "const"
    props = {p.get("name"): p.text for p in entity.findall("property")}
    assert props["dimensionType"] == "Entity"
    assert props["prompt_text"] == "Select Entity"
    assert props["application"] == "MCW_PCF"
    # default_value lands in <value>; absent default stays an empty element.
    assert variables[1].find("value").text == "OEP_Working"
    assert entity.find("value").text is None

    rule = root.find("rules")[0]
    assert rule.get("name") == "Copy Working to Final"
    assert rule.get("product") == "Planning"
    rule_props = {p.get("name"): p.text for p in rule.findall("property")}
    assert rule_props["plantype"] == "OEP_FS"
    refs = rule.find("variable_references")
    assert [r.get("name") for r in refs] == ["OCF_Entity", "OCF_Version"]
    seqs = [next(p.text for p in r.findall("property") if p.get("name") == "seq") for r in refs]
    assert seqs == ["1", "2"]

    script = rule.find("script")
    assert script.get("type") == "groovy"
    # Escaped-text body survives (`<`, `&&`) exactly.
    assert script.text == _SCRIPT
    assert "&lt;" in xml and "&amp;&amp;" in xml


def test_render_rule_xml_calcscript_cdata():
    body = 'DATACOPY "Working" TO "Final";\n/* weird ]]> sequence */'
    xml = render_rule_xml(_spec(type=RuleType.calc_script), body, "calcscript")
    assert "<![CDATA[" in xml
    root = DET.fromstring(xml)
    script = root.find("rules")[0].find("script")
    assert script.get("type") == "calcscript"
    assert script.text == body  # CDATA (incl. the split "]]>") round-trips


def test_render_rule_xml_rejects_unknown_script_type():
    with pytest.raises(ValueError):
        render_rule_xml(_spec(), _SCRIPT, "python")


# --- package construction --------------------------------------------------------


def test_build_rule_package_layout_and_manifest():
    filename, data = build_rule_package(_spec(), _SCRIPT, "groovy")
    assert filename == "Copy_Working_to_Final_calcrules.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        rule_path = "CALC-Calculation Manager/resource/Planning/MCW_PCF/OEP_FS/Rules/Copy Working to Final"
        assert names == sorted(names)
        assert set(names) == {rule_path, "manifest.json"}
        for info in zf.infolist():  # reproducible: fixed timestamps
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
        rule_bytes = zf.read(rule_path)
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["generator"] == GENERATOR
    assert manifest["ruleName"] == "Copy Working to Final"
    assert manifest["application"] == "MCW_PCF"
    assert manifest["cube"] == "OEP_FS"
    assert manifest["checksums"] == {rule_path: hashlib.sha256(rule_bytes).hexdigest()}


def test_build_rule_package_is_byte_identical():
    a = build_rule_package(_spec(), _SCRIPT, "groovy")
    b = build_rule_package(_spec(), _SCRIPT, "groovy")
    assert a == b
    assert hashlib.sha256(a[1]).hexdigest() == hashlib.sha256(b[1]).hexdigest()
    # And any input change changes the bytes.
    c = build_rule_package(_spec(), _SCRIPT + "\n// v2", "groovy")
    assert c[1] != a[1]


def test_rule_name_never_adds_zip_path_levels():
    spec = _spec(name="Bad/../Name")
    _, data = build_rule_package(spec, _SCRIPT)
    path, _ = _rule_file_from_zip(data)
    assert path.split("/")[:6] == ["CALC-Calculation Manager", "resource", "Planning",
                                   "MCW_PCF", "OEP_FS", "Rules"]
    assert len(path.split("/")) == 7  # exactly one leaf segment for the rule


# --- round-trip through the snapshot parser --------------------------------------


@pytest.mark.parametrize("script_type,body", [
    ("groovy", _SCRIPT),
    ("calcscript", 'DATACOPY "Working" TO "Final";'),
])
def test_round_trip_via_snapshot_parser(script_type, body):
    spec = _spec()
    _, data = build_rule_package(spec, body, script_type)
    path, text = _rule_file_from_zip(data)
    issues: list[str] = []
    rules = _parse_rule_file(text, path, "fallback", "fallback_cube", spec.application, issues)
    assert issues == []
    assert len(rules) == 1
    parsed = rules[0]
    assert parsed["name"] == spec.name
    assert parsed["cube"] == spec.cube
    assert parsed["scriptType"] == script_type
    assert parsed["body"] == body
    assert parsed["runtimePrompts"] == ["OCF_Entity", "OCF_Version"]
    assert parsed["application"] == spec.application


# --- _save_draft emits the package artifact ---------------------------------------


async def _turn(session, project, conv, text):
    conversations.add_message(session, conv.id, "user", text)
    events = []
    async for ev in stream_turn(session=session, project=project, conversation=conv,
                                connector=DemoConnector(), provider=MockProvider(),
                                application="MCWPCF", classification="development",
                                environment_name="MCW Demo (Local)", demo=True,
                                context_version_id=None, user_text=text):
        events.append(ev)
    return events


async def test_save_draft_also_builds_rule_package(session):
    out = projects.create_project(session, "Rule Package Save Test")
    proj = projects.get_project(session, out.id)
    conv = conversations.create_conversation(session, proj.id)
    await _turn(session, proj, conv, "create a rule that copies working to final")
    events = await _turn(session, proj, conv, "save rule draft")

    downloads = [ev.data for ev in events
                 if str(ev.type) == "block" and ev.data.get("type") == "downloadableFile"]
    assert len(downloads) == 2  # JSON draft + Calc Manager package
    media = {d["data"]["mediaType"] for d in downloads}
    assert media == {"application/json", "application/zip"}

    packages = artifacts_svc.list_artifacts(session, proj.id, kind="rulePackage")
    assert len(packages) == 1
    pkg = packages[0]
    assert pkg.name.endswith("_calcrules.zip")
    assert pkg.metadata_["application"] and pkg.metadata_["cube"]
    data = open(pkg.path, "rb").read()
    assert hashlib.sha256(data).hexdigest() == pkg.checksum
    path, text = _rule_file_from_zip(data)
    rules = _parse_rule_file(text, path, "fallback", "fallback_cube",
                             pkg.metadata_["application"], [])
    assert len(rules) == 1 and rules[0]["cube"] == pkg.metadata_["cube"]

    # The user-facing note makes the manual-import contract explicit.
    markdown = " ".join(ev.data["data"]["text"] for ev in events
                        if str(ev.type) == "block" and ev.data.get("type") == "markdown")
    assert "Migration" in markdown and "never deployed automatically" in markdown


async def test_rule_nlu_infers_calc_script_type():
    from app.agent.rule_nlu import build_initial_rule_spec
    from app.artifacts.metadata import build_metadata_from_connector
    md = await build_metadata_from_connector(DemoConnector(), "MCWPCF")
    calc, _i, _q = build_initial_rule_spec("write a calc script that FIX/DATACOPY copies Working to Final", md, "MCWPCF")
    assert calc.type == RuleType.calc_script
    groovy, _i, _q = build_initial_rule_spec("create a business rule that emails a report", md, "MCWPCF")
    assert groovy.type == RuleType.business_rule


async def test_save_draft_packages_calc_script_as_calcscript(session):
    # End-to-end: a calc-script creation request must yield a calcscript-typed
    # package, not a mislabeled Groovy one (the drafted body would never compile).
    out = projects.create_project(session, "Calc Script Package Test")
    proj = projects.get_project(session, out.id)
    conv = conversations.create_conversation(session, proj.id)
    await _turn(session, proj, conv, "create a calc script rule that does DATACOPY from Working to Final")
    await _turn(session, proj, conv, "save rule draft")

    pkg = artifacts_svc.list_artifacts(session, proj.id, kind="rulePackage")[0]
    _path, text = _rule_file_from_zip(open(pkg.path, "rb").read())
    root = DET.fromstring(text)
    script = root.find(".//script")
    assert script.get("type") == "calcscript"
