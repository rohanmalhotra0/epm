import { CheckmarkFilled } from "@carbon/icons-react";
import { Markdown } from "./Markdown";
import { FormPreviewBlock } from "./FormPreviewBlock";
import { ArtifactBlock } from "../artifacts/blocks";
import { CubeArchitectureBlock } from "./CubeArchitectureBlock";
import { DeploymentPlanBlock, DeploymentProgressBlock, DeploymentResultBlock } from "./DeploymentBlocks";
import { SnapshotSummaryBlock } from "./SnapshotSummaryBlock";
import { SpreadsheetBlock } from "./SpreadsheetBlock";
import {
  CellIntersectionBlock,
  CodeBlock,
  ConfirmationBlock,
  ConnectionStatusBlock,
  ContextSummaryBlock,
  CubeComparisonBlock,
  DiffBlock,
  DimensionCoverageBlock,
  DimensionHierarchyBlock,
  DownloadableFileBlock,
  ErrorDiagnosticsBlock,
  FallbackBlock,
  MemberSearchBlock,
  RuntimePromptFormBlock,
  ToolInvocationBlock,
  ValidationReportBlock,
} from "./SimpleBlocks";

export interface ChatBlockT {
  id: string;
  type: string;
  data: any;
}

export function ProcessSteps({ steps }: { steps: Array<{ key: string; label: string; state: string }> }) {
  if (!steps?.length) return null;
  return (
    <div className="process-steps">
      {steps.map((s) => (
        <div className={`process-step ${s.state}`} key={s.key}>
          <span className="ic">
            {s.state === "active" ? <div className="spinner" /> : s.state === "done" ? <CheckmarkFilled size={12} /> : "○"}
          </span>
          {s.label}
        </div>
      ))}
    </div>
  );
}

export function BlockRenderer({ block, onAction }: { block: ChatBlockT; onAction: (v: string) => void }) {
  const d = block.data;
  switch (block.type) {
    case "markdown":
      return <Markdown text={d.text} />;
    case "code":
      return <CodeBlock data={d} />;
    case "processSteps":
      return <ProcessSteps steps={d.steps} />;
    case "formPreview":
      return <FormPreviewBlock data={d} />;
    case "formSpecification":
    case "reportPreview":
    case "reportSpecification":
      return <ArtifactBlock block={block} />;
    case "validationReport":
      return <ValidationReportBlock data={d} />;
    case "confirmation":
      return <ConfirmationBlock data={d} onAction={onAction} />;
    case "deploymentPlan":
      return <DeploymentPlanBlock data={d} />;
    case "deploymentProgress":
      return <DeploymentProgressBlock data={d} />;
    case "deploymentResult":
      return <DeploymentResultBlock data={d} />;
    case "memberSearchResults":
      return <MemberSearchBlock data={d} />;
    case "contextSummary":
      return <ContextSummaryBlock data={d} />;
    case "runtimePromptForm":
      return <RuntimePromptFormBlock data={d} onAction={onAction} />;
    case "toolInvocation":
      return <ToolInvocationBlock data={d} />;
    case "errorDiagnostics":
      return <ErrorDiagnosticsBlock data={d} onAction={onAction} />;
    case "downloadableFile":
      return <DownloadableFileBlock data={d} />;
    case "connectionStatus":
      return <ConnectionStatusBlock data={d} />;
    case "diff":
      return <DiffBlock data={d} />;
    case "cubeArchitecture":
      return <CubeArchitectureBlock data={d} onAction={onAction} />;
    case "cellIntersection":
      return <CellIntersectionBlock data={d} />;
    case "cubeComparison":
      return <CubeComparisonBlock data={d} />;
    case "dimensionCoverage":
      return <DimensionCoverageBlock data={d} />;
    case "dimensionHierarchy":
      return <DimensionHierarchyBlock data={d} onAction={onAction} />;
    case "snapshotSummary":
      return <SnapshotSummaryBlock data={d} />;
    case "spreadsheetPreview":
      return <SpreadsheetBlock data={d} />;
    default:
      return <FallbackBlock type={block.type} data={d} />;
  }
}
