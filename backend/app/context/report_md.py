"""Human-readable Markdown (.md) report of a learned context with Mermaid diagrams.

The ``.epwcontext`` package is a ZIP for re-import/sharing; this is the openable
counterpart — a formatted Markdown document of the application's cubes, dimensions,
member hierarchies, rules and variables that renders beautifully on GitHub and in
Markdown viewers with Mermaid diagram support.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import ContextVersion
from ..services import context_store

MD_MIME = "text/markdown"


def _sorted_records(records: list, kind: str) -> list:
    return [r for r in records if r.kind == kind]


def _escape_md(text: str) -> str:
    """Escape special Markdown characters."""
    if not text:
        return ""
    # Escape characters that have special meaning in Markdown
    for ch in ['\\', '`', '*', '_', '{', '}', '[', ']', '(', ')', '#', '+', '-', '.', '!', '|']:
        text = text.replace(ch, '\\' + ch)
    return text


def _sanitize_mermaid_id(text: str) -> str:
    """Convert text to a valid Mermaid node ID."""
    if not text:
        return "node"
    # Replace spaces and special chars with underscores
    sanitized = "".join(c if c.isalnum() or c == '_' else '_' for c in text)
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = "n" + sanitized
    return sanitized[:50]  # Limit length


def _build_cube_architecture_mermaid(cubes_data: list, dims_data: list) -> str:
    """Generate Mermaid graph showing cube-dimension relationships."""
    lines = ["```mermaid", "graph LR"]

    # Define dimension nodes
    dim_names = {d.name for d in dims_data}
    for dim in sorted(dim_names)[:20]:  # Limit to 20 dimensions for readability
        dim_id = _sanitize_mermaid_id(dim)
        lines.append(f"    {dim_id}[📐 {dim}]")

    lines.append("")  # Empty line for separation

    # Define cube nodes and connections (limit to first 10 cubes)
    for cube in cubes_data[:10]:
        data = cube.data or {}
        dims = data.get("dimensions") or []
        cube_id = _sanitize_mermaid_id(cube.name)
        cube_type = data.get("type", "")

        # Add cube node with type
        label = f"🧊 {cube.name}"
        if cube_type:
            label += f" ({cube_type})"
        lines.append(f"    {cube_id}[\"{label}\"]")

        # Connect to dimensions (limit to first 8 per cube)
        for dim in dims[:8]:
            if dim in dim_names:
                dim_id = _sanitize_mermaid_id(dim)
                lines.append(f"    {cube_id} --> {dim_id}")

    lines.append("```")
    return "\n".join(lines)


def _build_hierarchy_mermaid(members: list, dimension_name: str, max_depth: int = 4, max_nodes: int = 50) -> str:
    """Generate Mermaid tree diagram for dimension member hierarchy."""
    by_name = {m.name: m for m in members}
    children: dict[str | None, list] = {}
    for m in members:
        parent = m.parent if (m.parent and m.parent in by_name and m.parent != m.name) else None
        children.setdefault(parent, []).append(m)

    roots = children.get(None, [])
    if not roots:
        return ""

    lines = ["```mermaid", "graph TD"]

    node_count = [0]  # Use list to allow modification in nested function

    def walk(node, depth: int = 0) -> None:
        if depth > max_depth or node_count[0] >= max_nodes:
            return

        node_count[0] += 1
        node_id = _sanitize_mermaid_id(f"{dimension_name}_{node.name}")
        data = node.data or {}
        alias = node.alias or data.get("alias")

        label = node.name
        if alias and alias != node.name:
            label += f" ({alias})"

        # Add node with depth-based styling
        if depth == 0:
            lines.append(f"    {node_id}[\"{label}\"]")
            lines.append(f"    style {node_id} fill:#4589ff,stroke:#333,stroke-width:2px,color:#fff")
        else:
            lines.append(f"    {node_id}[\"{label}\"]")

        # Process children
        child_nodes = children.get(node.name, [])
        for child in child_nodes[:10]:  # Limit children per node
            if node_count[0] >= max_nodes:
                break
            child_id = _sanitize_mermaid_id(f"{dimension_name}_{child.name}")
            lines.append(f"    {node_id} --> {child_id}")
            walk(child, depth + 1)

    # Process first 3 roots
    for root in roots[:3]:
        if node_count[0] >= max_nodes:
            break
        walk(root)

    lines.append("```")
    return "\n".join(lines)


def _build_hierarchy_text_tree(members: list, max_depth: int = 5, max_display: int = 100) -> str:
    """Generate text-based tree for member hierarchy (fallback or supplement)."""
    by_name = {m.name: m for m in members}
    children: dict[str | None, list] = {}
    for m in members:
        parent = m.parent if (m.parent and m.parent in by_name and m.parent != m.name) else None
        children.setdefault(parent, []).append(m)

    roots = children.get(None, [])
    lines = []
    display_count = [0]

    def walk(node, depth: int, is_last: bool = False, prefix: str = "") -> None:
        if depth > max_depth or display_count[0] >= max_display:
            return

        display_count[0] += 1
        data = node.data or {}
        label = node.name
        alias = node.alias or data.get("alias")
        if alias and alias != node.name:
            label += f"  ({alias})"

        connector = "└─ " if is_last else "├─ "
        lines.append(f"{prefix}{connector}{label}")

        child_prefix = prefix + ("   " if is_last else "│  ")
        child_nodes = children.get(node.name, [])

        for idx, child in enumerate(child_nodes):
            walk(child, depth + 1, idx == len(child_nodes) - 1, child_prefix)

    for idx, root in enumerate(roots):
        walk(root, 0, idx == len(roots) - 1)

    return "\n".join(lines)


def _build_summary_mermaid(counts: dict) -> str:
    """Generate Mermaid bar chart for summary statistics."""
    if not counts:
        return ""

    lines = ["```mermaid", "%%{init: {'theme':'base'}}%%", "pie title EPM Context Summary"]

    for key, value in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        label = key.replace("_", " ").title()
        if value > 0:  # Only include non-zero counts
            lines.append(f'    "{label}" : {value}')

    lines.append("```")
    return "\n".join(lines)


def build_context_md(session: Session, context_version_id: str) -> tuple[str, str]:
    """Build a Markdown report with Mermaid diagrams for an EPM context version.

    Args:
        session: SQLAlchemy database session
        context_version_id: ID of the context version to export

    Returns:
        Tuple of (filename, markdown_string)
    """
    cv = session.get(ContextVersion, context_version_id)
    if cv is None:
        raise KeyError("context version not found")

    records = context_store.get_records(session, context_version_id)
    counts = (cv.manifest or {}).get("counts", {})
    manifest = cv.manifest or {}

    lines = []

    # Front matter
    lines.append("---")
    lines.append(f"title: EPM Context Report - {cv.application}")
    lines.append(f"application: {cv.application}")
    lines.append(f"context_version: {cv.label}")
    lines.append(f"environment: {manifest.get('environmentClassification', 'Unknown')}")
    lines.append(f"generated: {manifest.get('generatedAt', str(cv.created_at))}")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# 📊 EPM Context Report")
    lines.append("")
    lines.append(f"## {cv.application}")
    lines.append("")

    # Metadata section
    lines.append("### Metadata")
    lines.append("")
    lines.append(f"- **Application**: {cv.application}")
    lines.append(f"- **Environment**: {manifest.get('environmentClassification', '—')}")
    lines.append(f"- **Generated**: {manifest.get('generatedAt', str(cv.created_at))}")
    lines.append(f"- **Context Version**: {cv.label}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of contents
    lines.append("## 📑 Table of Contents")
    lines.append("")
    lines.append("- [Summary](#summary)")
    lines.append("- [Cubes](#cubes)")
    lines.append("  - [Architecture Diagram](#architecture-diagram)")
    lines.append("  - [Cube Details](#cube-details)")
    lines.append("- [Dimensions](#dimensions)")
    lines.append("- [Member Hierarchies](#member-hierarchies)")
    lines.append("- [Business Rules](#business-rules)")
    lines.append("- [Variables](#variables)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary section
    lines.append("## Summary")
    lines.append("")
    lines.append("Overview of the EPM context contents.")
    lines.append("")

    # Summary chart
    if counts:
        lines.append(f"### 📊 Statistics")
        lines.append("")
        lines.append(_build_summary_mermaid(counts))
        lines.append("")

    # Summary table
    lines.append("| Category | Count |")
    lines.append("|----------|------:|")
    for k, v in sorted(counts.items()):
        label = k.replace("_", " ").title()
        lines.append(f"| {label} | {v} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Cubes section
    cubes = _sorted_records(records, "cube")
    if cubes:
        lines.append(f"## 🧊 Cubes ({len(cubes)})")
        lines.append("")

        # Architecture diagram
        lines.append("### Architecture Diagram")
        lines.append("")
        lines.append("Visual representation of how dimensions connect to cubes:")
        lines.append("")

        dims = _sorted_records(records, "dimension")
        if cubes and dims:
            lines.append(_build_cube_architecture_mermaid(cubes, dims))
            lines.append("")

        # Cube details table
        lines.append("### Cube Details")
        lines.append("")
        lines.append("| Cube | Type | # Dimensions | Dimensions (first 5) |")
        lines.append("|------|------|-------------:|----------------------|")

        for c in cubes:
            data = c.data or {}
            dims_list = data.get("dimensions") or []
            cube_type = data.get("type", "")

            dim_display = ", ".join(dims_list[:5])
            if len(dims_list) > 5:
                dim_display += f" ... +{len(dims_list) - 5} more"

            lines.append(f"| {c.name} | {cube_type} | {len(dims_list)} | {dim_display} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Dimensions section
    dims = _sorted_records(records, "dimension")
    if dims:
        lines.append(f"## 📐 Dimensions ({len(dims)})")
        lines.append("")
        lines.append("| Dimension | Type | Density | Used in Cubes |")
        lines.append("|-----------|------|---------|---------------|")

        for d in dims:
            data = d.data or {}
            dim_type = data.get("type", "")
            density = "Dense" if data.get("dense") else "Sparse"
            cubes_list = data.get("cubes") or []

            cube_display = ", ".join(cubes_list[:3])
            if len(cubes_list) > 3:
                cube_display += f" +{len(cubes_list) - 3}"

            lines.append(f"| {d.name} | {dim_type} | {density} | {cube_display} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Member hierarchies section
    members = _sorted_records(records, "member")
    if members:
        lines.append(f"## 🌳 Member Hierarchies ({len(members)} total)")
        lines.append("")
        lines.append("Visual tree representation of dimension members showing parent-child relationships.")
        lines.append("")

        by_dim: dict[str, list] = {}
        for m in members:
            by_dim.setdefault(m.dimension or "—", []).append(m)

        shown_dims = list(sorted(by_dim.keys()))

        # Show Mermaid diagrams for first 5 dimensions
        lines.append("### 🎨 Visual Hierarchies (First 5 Dimensions)")
        lines.append("")

        for dim in shown_dims[:5]:
            member_list = by_dim[dim]
            lines.append(f"#### {dim} ({len(member_list)} members)")
            lines.append("")

            mermaid_diagram = _build_hierarchy_mermaid(member_list, dim)
            if mermaid_diagram:
                lines.append(mermaid_diagram)
                lines.append("")

        # Show remaining dimensions in collapsible sections with text trees
        if len(shown_dims) > 5:
            lines.append("### 📋 Additional Hierarchies (Text Format)")
            lines.append("")

            for dim in shown_dims[5:]:
                member_list = by_dim[dim]
                tree_text = _build_hierarchy_text_tree(member_list)

                lines.append("<details>")
                lines.append(f"<summary><strong>{dim}</strong> ({len(member_list)} members)</summary>")
                lines.append("")
                lines.append("```")
                lines.append(tree_text)
                lines.append("```")
                lines.append("")
                lines.append("</details>")
                lines.append("")

        lines.append("---")
        lines.append("")
    else:
        lines.append("## 🌳 Member Hierarchies")
        lines.append("")
        lines.append("> ⚠️ **Note**: No members were captured. Members require an EPM Automate metadata ")
        lines.append("> export or LCM snapshot; run a context refresh once that is configured.")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Business rules section
    rules = _sorted_records(records, "rule")
    if rules:
        lines.append(f"## ⚙️ Business Rules ({len(rules)})")
        lines.append("")
        lines.append("Calculation scripts and business rules defined in the application.")
        lines.append("")

        for idx, r in enumerate(rules, 1):
            lines.append(f"{idx}. **{r.name}**")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Variables section
    variables = _sorted_records(records, "variable")
    if variables:
        lines.append(f"## 🔢 Substitution & User Variables ({len(variables)})")
        lines.append("")
        lines.append("Variables used for dynamic calculations and member substitutions.")
        lines.append("")
        lines.append("| Variable | Dimension | Value |")
        lines.append("|----------|-----------|-------|")

        for v in variables:
            data = v.data or {}
            dimension = data.get("dimension") or "—"
            value = str(data.get("value") or "—")
            lines.append(f"| {v.name} | {dimension} | {value} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Footer
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by EPM Wizard • {cv.label}*")
    lines.append("")

    markdown_content = "\n".join(lines)
    filename = f"{cv.label}.md"

    return filename, markdown_content
