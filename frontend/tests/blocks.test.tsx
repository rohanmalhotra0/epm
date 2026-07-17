import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BlockRenderer } from "../src/blocks";

function renderBlock(type: string, data: any, onAction = vi.fn()) {
  render(<BlockRenderer block={{ id: "b1", type, data }} onAction={onAction} />);
  return onAction;
}

describe("inline blocks", () => {
  it("renders a form preview grid with axis chips and cells", () => {
    renderBlock("formPreview", {
      formName: "Actual Payroll Form",
      application: "MCWPCF",
      cube: "OEP_WFP",
      folder: "EPM Wizard/Generated",
      validationStatus: "valid",
      useAliases: true,
      hiddenMembers: [],
      ruleAssociations: [],
      pov: [{ kind: "pov", dimension: "Scenario", selectionSummary: "Actual", resolvedCount: 1, sampleMembers: [], suppressMissing: false, truncated: false }],
      pages: [],
      rows: [{ kind: "row", dimension: "Account", selectionSummary: "level-0 of Total Payroll", resolvedCount: 7, sampleMembers: [], suppressMissing: true, truncated: false }],
      columns: [{ kind: "column", dimension: "Period", selectionSummary: "Jan:Dec", resolvedCount: 12, sampleMembers: [], suppressMissing: false, truncated: false }],
      rowLabels: ["Salaries", "Wages"],
      columnLabels: ["Jan", "Feb"],
      rowsTruncated: false,
      columnsTruncated: false,
      sizeEstimate: { rowCombinations: 7, columnCombinations: 12, pageCombinations: 1, totalCells: 84, warningThreshold: 250000 },
    });
    expect(screen.getByText(/Actual Payroll Form/)).toBeInTheDocument();
    expect(screen.getByText("Salaries")).toBeInTheDocument();
    expect(screen.getByText(/84 cells/)).toBeInTheDocument();
  });

  it("renders a validation report with candidates", () => {
    renderBlock("validationReport", {
      artifactName: "x",
      valid: false,
      blocking: true,
      issues: [{ layer: "selection", severity: "error", code: "MEMBER_NOT_FOUND", message: "Member 'Total Payrol' not found", candidates: ["Total Payroll"] }],
    });
    expect(screen.getByText(/not found/)).toBeInTheDocument();
    expect(screen.getByText("Total Payroll")).toBeInTheDocument();
  });

  it("confirmation button records the value as a user message", () => {
    const onAction = renderBlock("confirmation", {
      prompt: "Ready to deploy?",
      actions: [{ key: "deploy", label: "Deploy to Dev", value: "deploy", style: "primary" }],
      severity: "info",
    });
    fireEvent.click(screen.getByText("Deploy to Dev"));
    expect(onAction).toHaveBeenCalledWith("deploy");
  });

  it("renders the cube architecture map and dimension table", () => {
    renderBlock("cubeArchitecture", {
      application: "MCWPCF",
      cube: "OEP_DCSH",
      dimensionCount: 2,
      dimensions: [
        { name: "Account", type: "account", group: "financial", memberCount: 21, rootMembers: [], usedOnAxis: "rows", status: "selected" },
        { name: "Bank", type: "custom", group: "custom", memberCount: 4, rootMembers: [], status: "missing" },
      ],
    });
    expect(screen.getAllByText("OEP_DCSH").length).toBeGreaterThan(0);
    expect(screen.getByText("Custom dimension")).toBeInTheDocument();
  });

  it("runtime prompt form submits a /run-rule command", () => {
    const onAction = renderBlock("runtimePromptForm", {
      ruleName: "IR",
      application: "MCWPCF",
      cube: "OEP_FS",
      fields: [{ name: "Scenario", type: "member", dimension: "Scenario", promptText: "Scenario", required: true, default: "Forecast" }],
      prefilledFrom: {},
      actions: [],
    });
    fireEvent.click(screen.getByText("Run rule"));
    expect(onAction).toHaveBeenCalledWith(expect.stringContaining("/run-rule IR"));
    expect(onAction).toHaveBeenCalledWith(expect.stringContaining("Scenario=Forecast"));
  });

  it("deployment result shows verified state", () => {
    renderBlock("deploymentResult", {
      plan: { artifactName: "Actual Payroll Form", environmentName: "Demo", environmentClassification: "development", operation: "create", steps: [] },
      state: "COMPLETED",
      success: true,
      verified: true,
      verificationNotes: ["✓ Artifact exists"],
      rollbackAvailable: false,
    });
    expect(screen.getByText(/Deployed & verified/)).toBeInTheDocument();
  });

  it("unknown block types fall back gracefully", () => {
    renderBlock("totallyUnknownBlock", { anything: 1 });
    expect(screen.getByText("totallyUnknownBlock")).toBeInTheDocument();
  });

  it("report blocks render an artifacts card", () => {
    renderBlock("reportSpecification", { spec: { name: "Actual Revenue Report" }, preview: { grids: [] } });
    expect(screen.getByText("Actual Revenue Report")).toBeInTheDocument();
    expect(screen.getByText("Open in panel ↗")).toBeInTheDocument();
  });
});
