"""Parse an Oracle-artifact representation back into a FormSpecification.

Supports two inputs:
  * a normalised reference-form ``definition`` dict (spec section 23 cloning)
  * EPM Wizard normalised form XML (round-trips render_xml exactly, spec 27)
"""

from __future__ import annotations

from defusedxml import ElementTree as DET

from ..schemas.form_spec import (
    AxisMember,
    DisplayOptions,
    FormSpecification,
    MemberSelection,
    ReferenceTemplate,
)

_INT_ATTRS = {"offsetStart", "offsetEnd"}
_LIST_ATTRS = {"members"}


def parse_definition(definition: dict, name: str, description: str | None = None) -> FormSpecification:
    payload = {"name": name, **definition}
    if description:
        payload["description"] = description
    return FormSpecification.model_validate(payload)


def clone_from_reference(reference_definition: dict, new_name: str, reference_name: str) -> FormSpecification:
    spec = parse_definition(reference_definition, new_name)
    spec.reference_template = ReferenceTemplate(type="existingForm", name=reference_name)
    return spec


def parse_xml(xml_text: str) -> FormSpecification:
    root = DET.fromstring(xml_text)
    if root.tag != "form":
        raise ValueError("not an EPM Wizard form document")

    description = None
    reference = None
    display = DisplayOptions()
    hidden: list[str] = []
    axes: dict[str, list[AxisMember]] = {"pov": [], "page": [], "row": [], "column": []}
    rules = []

    for child in root:
        if child.tag == "description":
            description = child.text
        elif child.tag == "reference":
            reference = ReferenceTemplate(type=child.get("type", "existingForm"), name=child.get("name", ""))
        elif child.tag == "display":
            display = DisplayOptions(
                use_aliases=child.get("useAliases") == "true",
                alias_table=child.get("aliasTable", "Default"),
                suppress_missing_rows=child.get("suppressMissingRows") == "true",
                suppress_missing_columns=child.get("suppressMissingColumns") == "true",
                read_only=child.get("readOnly") == "true",
            )
        elif child.tag == "hiddenMembers":
            hidden = [m.text for m in child if m.text]
        elif child.tag == "axis":
            kind = child.get("kind")
            for dim_el in child:
                sel_el = dim_el.find("selection")
                selection = _parse_selection(sel_el)
                axes[kind].append(AxisMember(
                    dimension=dim_el.get("name"),
                    selection=selection,
                    suppress_missing=dim_el.get("suppressMissing") == "true",
                ))
        elif child.tag == "businessRules":
            from ..schemas.form_spec import BusinessRuleAssociation, PromptMapping
            for rule_el in child:
                mappings = [
                    PromptMapping(prompt_name=pm.get("prompt"), source=pm.get("source", "userEntered"),
                                  dimension=pm.get("dimension"), value=pm.get("value"))
                    for pm in rule_el.findall("promptMapping")
                ]
                rules.append(BusinessRuleAssociation(
                    rule_name=rule_el.get("name"), rule_type=rule_el.get("type", "businessRule"),
                    association_type=rule_el.get("association", "manualLaunch"), prompt_mappings=mappings,
                ))

    display.hidden_members = hidden
    return FormSpecification(
        schema_version=root.get("schemaVersion", "1.0.0"),
        name=root.get("name"),
        description=description,
        application=root.get("application"),
        cube=root.get("cube"),
        folder=root.get("folder", "EPM Wizard/Generated"),
        reference_template=reference,
        pov=axes["pov"], pages=axes["page"], rows=axes["row"], columns=axes["column"],
        display=display,
        business_rule_associations=rules,
    )


def _parse_selection(sel_el) -> MemberSelection:  # noqa: ANN001
    data: dict = {}
    for key, value in sel_el.attrib.items():
        if key in _INT_ATTRS:
            data[key] = int(value)
        elif key in _LIST_ATTRS:
            data[key] = value.split(",")
        else:
            data[key] = value
    return MemberSelection.model_validate(data)
