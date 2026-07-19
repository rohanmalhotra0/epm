/* eslint-disable */
// ---------------------------------------------------------------------------
// GENERATED FILE — DO NOT EDIT BY HAND.
// Source of truth: backend Pydantic models (app/schemas/*.py).
// Regenerate with:  python -m scripts.export_schema  (from backend/)
// A backend drift test fails if this file is out of sync.
// ---------------------------------------------------------------------------

import { z } from "zod";

export const ApplicationRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  type: z.string().optional(),
  description: z.string().nullable().optional(),
}));

export const ArtifactKindSchema = z.enum(["formSpec", "reportSpec"]);

export const ArtifactOutSchema = z.lazy(() => z.object({
  id: z.string(),
  projectId: z.string(),
  kind: z.string(),
  name: z.string(),
  version: z.number().optional(),
  checksum: z.string().nullable().optional(),
  contextVersion: z.string().nullable().optional(),
  hasContent: z.boolean().optional(),
  hasFile: z.boolean().optional(),
  payload: z.record(z.string(), z.unknown()).nullable().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
}));

export const ArtifactTypeSchema = z.enum(["planningForm", "businessRule", "calcScript", "groovyRule", "ruleset", "contextPackage"]);

export const AxisMemberSchema = z.lazy(() => z.object({
  dimension: z.string(),
  selection: MemberSelectionSchema,
  suppressMissing: z.boolean().optional(),
}));

export const BusinessRuleAssociationSchema = z.lazy(() => z.object({
  ruleName: z.string(),
  ruleType: z.string().optional(),
  associationType: z.string().optional(),
  promptMappings: z.array(PromptMappingSchema).optional(),
}));

export const CellIntersectionSchema = z.lazy(() => z.object({
  application: z.string(),
  cube: z.string(),
  members: z.array(CellMemberSchema).optional(),
  expression: z.string().optional(),
  note: z.string().optional(),
}));

export const CellMemberSchema = z.lazy(() => z.object({
  dimension: z.string(),
  member: z.string(),
  source: z.string().optional(),
}));

export const CellOverrideSchema = z.lazy(() => z.object({
  value: z.number().nullable().optional(),
  format: SmartFormatSchema.nullable().optional(),
  note: z.string().nullable().optional(),
}));

export const ChartTypeSchema = z.enum(["none", "bar", "line", "area", "pie"]);

export const ChatActionSchema = z.lazy(() => z.object({
  key: z.string(),
  label: z.string(),
  value: z.string(),
  style: z.string().optional(),
  disabled: z.boolean().optional(),
}));

export const ChatBlockSchema = z.lazy(() => z.object({
  id: z.string(),
  type: ChatBlockTypeSchema,
  data: z.record(z.string(), z.unknown()).optional(),
}));

export const ChatBlockTypeSchema = z.enum(["markdown", "code", "formPreview", "formSpecification", "reportPreview", "reportSpecification", "rulePreview", "runtimePromptForm", "memberSearchResults", "contextSummary", "validationReport", "deploymentPlan", "deploymentProgress", "deploymentResult", "diff", "confirmation", "spreadsheetPreview", "downloadableFile", "errorDiagnostics", "connectionStatus", "toolInvocation", "processSteps", "cubeArchitecture", "cellIntersection", "cubeComparison", "dimensionCoverage", "dimensionHierarchy"]);

export const ComparatorSchema = z.enum(["lt", "le", "gt", "ge", "eq", "ne"]);

export const CompletenessStatusSchema = z.enum(["complete", "partial", "derived", "unavailable", "notRequested"]);

export const ConditionalRuleSchema = z.lazy(() => z.object({
  comparator: ComparatorSchema.optional(),
  value: z.number().optional(),
  color: z.string().nullable().optional(),
  background: z.string().nullable().optional(),
  bold: z.boolean().optional(),
  label: z.string().nullable().optional(),
}));

export const ConfidenceSchema = z.enum(["exact", "high", "medium", "low"]);

export const ConfirmationPayloadSchema = z.lazy(() => z.object({
  prompt: z.string(),
  detail: z.string().nullable().optional(),
  actions: z.array(ChatActionSchema),
  severity: SeveritySchema.optional(),
}));

export const ConnectionResultSchema = z.lazy(() => z.object({
  connected: z.boolean(),
  environmentId: z.string(),
  message: z.string(),
  application: z.string().nullable().optional(),
  detail: z.string().nullable().optional(),
  diagnostics: z.record(z.string(), z.unknown()).optional(),
}));

export const ConnectionStatusPayloadSchema = z.lazy(() => z.object({
  connected: z.boolean(),
  environmentName: z.string().nullable().optional(),
  classification: EnvironmentClassificationSchema.nullable().optional(),
  application: z.string().nullable().optional(),
  contextStatus: z.string().nullable().optional(),
  demoMode: z.boolean().optional(),
}));

export const ContextManifestSchema = z.lazy(() => z.object({
  format: z.string().optional(),
  schemaVersion: z.string().optional(),
  generatedAt: z.string(),
  application: z.string(),
  environmentClassification: EnvironmentClassificationSchema,
  environmentFingerprint: z.string(),
  mode: ContextModeSchema,
  counts: z.record(z.string(), z.number()).optional(),
  includedFiles: z.array(z.string()).optional(),
  checksums: z.record(z.string(), z.string()).optional(),
  sections: z.array(ContextSectionStatusSchema).optional(),
  knownLimitations: z.array(z.string()).optional(),
  contextVersion: z.string(),
}));

export const ContextModeSchema = z.enum(["quick", "deep", "imported"]);

export const ContextSectionStatusSchema = z.lazy(() => z.object({
  name: z.string(),
  status: CompletenessStatusSchema,
  count: z.number().optional(),
  note: z.string().nullable().optional(),
}));

export const ContextVersionOutSchema = z.lazy(() => z.object({
  id: z.string(),
  projectId: z.string(),
  application: z.string(),
  label: z.string(),
  mode: z.string(),
  counts: z.record(z.string(), z.unknown()).optional(),
  active: z.boolean().optional(),
  manifest: z.record(z.string(), z.unknown()).optional(),
  createdAt: z.string(),
}));

export const ConversationOutSchema = z.lazy(() => z.object({
  id: z.string(),
  projectId: z.string(),
  title: z.string(),
  pinned: z.boolean().optional(),
  archived: z.boolean().optional(),
  provider: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  lastMessageAt: z.string().nullable().optional(),
  messageCount: z.number().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
}));

export const CrossDimAreaSchema = z.lazy(() => z.object({
  area: z.string(),
  detail: z.string(),
  count: z.number(),
}));

export const CrossDimSizeSchema = z.lazy(() => z.object({
  cube: z.string(),
  areas: z.array(CrossDimAreaSchema).optional(),
  totalPotentialCells: z.number().optional(),
  sizeEstimate: SizeEstimateSchema.nullable().optional(),
  warning: z.string().nullable().optional(),
  label: z.string().optional(),
}));

export const CubeArchitectureSchema = z.lazy(() => z.object({
  application: z.string(),
  cube: z.string(),
  cubeType: z.string().nullable().optional(),
  dimensionCount: z.number().optional(),
  dimensions: z.array(DimensionNodeSchema).optional(),
  formName: z.string().nullable().optional(),
  formCoverage: FormCoverageSchema.nullable().optional(),
}));

export const CubeComparisonSchema = z.lazy(() => z.object({
  application: z.string(),
  cubeA: z.string(),
  cubeB: z.string(),
  rows: z.array(CubeComparisonRowSchema).optional(),
  shared: z.number().optional(),
  onlyA: z.array(z.string()).optional(),
  onlyB: z.array(z.string()).optional(),
}));

export const CubeComparisonRowSchema = z.lazy(() => z.object({
  dimension: z.string(),
  inA: z.boolean(),
  inB: z.boolean(),
  detailA: z.string().nullable().optional(),
  detailB: z.string().nullable().optional(),
}));

export const CubeRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  application: z.string(),
  type: z.string().optional(),
  description: z.string().nullable().optional(),
  dimensions: z.array(z.string()).optional(),
}));

export const DeploymentOperationSchema = z.enum(["create", "update", "replace", "delete"]);

export const DeploymentOutSchema = z.lazy(() => z.object({
  id: z.string(),
  projectId: z.string(),
  conversationId: z.string().nullable().optional(),
  environmentName: z.string().nullable().optional(),
  classification: z.string(),
  application: z.string().nullable().optional(),
  artifactName: z.string(),
  artifactType: z.string(),
  operation: z.string(),
  operationClass: z.string(),
  approved: z.boolean(),
  success: z.boolean(),
  verified: z.boolean(),
  demoMode: z.boolean(),
  checksum: z.string().nullable().optional(),
  contextVersion: z.string().nullable().optional(),
  rollbackAvailable: z.boolean().optional(),
  report: z.record(z.string(), z.unknown()).optional(),
  errors: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
  createdAt: z.string(),
}));

export const DeploymentPlanSchema = z.lazy(() => z.object({
  schemaVersion: z.string().optional(),
  artifactType: ArtifactTypeSchema,
  artifactName: z.string(),
  application: z.string(),
  cube: z.string().nullable().optional(),
  folder: z.string().nullable().optional(),
  environmentName: z.string(),
  environmentClassification: EnvironmentClassificationSchema,
  operation: DeploymentOperationSchema,
  operationClass: OperationClassSchema.optional(),
  overwritesExisting: z.boolean().optional(),
  backupRequired: z.boolean().optional(),
  validationPassed: z.boolean().optional(),
  contextFresh: z.boolean().optional(),
  demoMode: z.boolean().optional(),
  requiresConfirmationPhrase: z.boolean().optional(),
  steps: z.array(DeploymentStepSchema).optional(),
  warnings: z.array(z.string()).optional(),
}));

export const DeploymentReportSchema = z.lazy(() => z.object({
  plan: DeploymentPlanSchema,
  state: FormWorkflowStateSchema.optional(),
  success: z.boolean().optional(),
  verified: z.boolean().optional(),
  verificationNotes: z.array(z.string()).optional(),
  jobId: z.string().nullable().optional(),
  jobResult: z.string().nullable().optional(),
  packageChecksum: z.string().nullable().optional(),
  backupArtifact: z.string().nullable().optional(),
  rollbackAvailable: z.boolean().optional(),
  startedAt: z.string().nullable().optional(),
  endedAt: z.string().nullable().optional(),
  durationMs: z.number().nullable().optional(),
  errors: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
}));

export const DeploymentStepSchema = z.lazy(() => z.object({
  key: z.string(),
  label: z.string(),
  status: DeploymentStepStatusSchema.optional(),
  detail: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  endedAt: z.string().nullable().optional(),
}));

export const DeploymentStepStatusSchema = z.enum(["pending", "running", "completed", "failed", "skipped"]);

export const DiagnosticsReportSchema = z.lazy(() => z.object({
  appVersion: z.string(),
  subsystems: z.array(SubsystemStatusSchema).optional(),
  storagePath: z.string(),
  activeProvider: z.string().nullable().optional(),
  activeModel: z.string().nullable().optional(),
  demoMode: z.boolean().optional(),
  schemaVersions: z.record(z.string(), z.unknown()).optional(),
  featureFlags: z.record(z.string(), z.unknown()).optional(),
  redactionHealthy: z.boolean().optional(),
}));

export const DiffPayloadSchema = z.lazy(() => z.object({
  title: z.string(),
  before: z.string(),
  after: z.string(),
  language: z.string().optional(),
}));

export const DimensionCoverageReportSchema = z.lazy(() => z.object({
  cube: z.string(),
  valid: z.boolean().optional(),
  coveredDimensions: z.array(z.string()).optional(),
  missingDimensions: z.array(z.string()).optional(),
  duplicateDimensions: z.array(z.string()).optional(),
  invalidSelections: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
  suggestions: z.array(MissingSuggestionSchema).optional(),
}));

export const DimensionHierarchySchema = z.lazy(() => z.object({
  application: z.string(),
  dimension: z.string(),
  root: z.string(),
  nodes: z.array(HierarchyNodeSchema).optional(),
  truncated: z.boolean().optional(),
  cap: z.number().optional(),
}));

export const DimensionNodeSchema = z.lazy(() => z.object({
  name: z.string(),
  alias: z.string().nullable().optional(),
  type: z.string().optional(),
  group: z.string().optional(),
  memberCount: z.number().nullable().optional(),
  rootMembers: z.array(z.string()).optional(),
  selectedMember: z.string().nullable().optional(),
  selectionSummary: z.string().nullable().optional(),
  usedOnAxis: z.string().nullable().optional(),
  status: z.string().optional(),
}));

export const DimensionRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  application: z.string(),
  type: z.string().optional(),
  cubes: z.array(z.string()).optional(),
  dense: z.boolean().nullable().optional(),
}));

export const DisplayOptionsSchema = z.lazy(() => z.object({
  useAliases: z.boolean().optional(),
  aliasTable: z.string().optional(),
  hiddenMembers: z.array(z.string()).optional(),
  suppressMissingRows: z.boolean().optional(),
  suppressMissingColumns: z.boolean().optional(),
  readOnly: z.boolean().optional(),
}));

export const DownloadableFilePayloadSchema = z.lazy(() => z.object({
  filename: z.string(),
  artifactId: z.string(),
  mediaType: z.string().optional(),
  sizeBytes: z.number().nullable().optional(),
  checksum: z.string().nullable().optional(),
}));

export const EditScopeSchema = z.enum(["artifact", "table", "cell"]);

export const EnvironmentClassificationSchema = z.enum(["development", "test", "production"]);

export const EnvironmentOutSchema = z.lazy(() => z.object({
  id: z.string(),
  projectId: z.string(),
  name: z.string(),
  baseUrl: z.string().nullable().optional(),
  username: z.string().nullable().optional(),
  authMethod: z.string().optional(),
  classification: EnvironmentClassificationSchema,
  preferredApplication: z.string().nullable().optional(),
  demo: z.boolean().optional(),
  connected: z.boolean().optional(),
  lastConnectedAt: z.string().nullable().optional(),
  lastContextRefreshAt: z.string().nullable().optional(),
}));

export const ErrorDiagnosticsPayloadSchema = z.lazy(() => z.object({
  category: z.string(),
  message: z.string(),
  likelyCause: z.string().nullable().optional(),
  suggestedAction: z.string().nullable().optional(),
  technicalDetail: z.string().nullable().optional(),
  actions: z.array(ChatActionSchema).optional(),
}));

export const FormCoverageSchema = z.lazy(() => z.object({
  pov: z.array(z.record(z.string(), z.unknown())).optional(),
  pages: z.array(z.record(z.string(), z.unknown())).optional(),
  rows: z.array(z.record(z.string(), z.unknown())).optional(),
  columns: z.array(z.record(z.string(), z.unknown())).optional(),
  implicitOrDefault: z.array(z.string()).optional(),
  missing: z.array(z.string()).optional(),
  duplicate: z.array(z.string()).optional(),
}));

export const FormPreviewSchema = z.lazy(() => z.object({
  formName: z.string(),
  application: z.string(),
  cube: z.string(),
  folder: z.string(),
  validationStatus: z.string().optional(),
  referenceTemplate: z.string().nullable().optional(),
  useAliases: z.boolean().optional(),
  hiddenMembers: z.array(z.string()).optional(),
  ruleAssociations: z.array(z.string()).optional(),
  pov: z.array(PreviewAxisSchema).optional(),
  pages: z.array(PreviewAxisSchema).optional(),
  rows: z.array(PreviewAxisSchema).optional(),
  columns: z.array(PreviewAxisSchema).optional(),
  rowLabels: z.array(z.string()).optional(),
  columnLabels: z.array(z.string()).optional(),
  rowsTruncated: z.boolean().optional(),
  columnsTruncated: z.boolean().optional(),
  sizeEstimate: SizeEstimateSchema.nullable().optional(),
}));

export const FormRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  application: z.string(),
  cube: z.string().nullable().optional(),
  folder: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  definition: z.record(z.string(), z.unknown()).nullable().optional(),
}));

export const FormSpecificationSchema = z.lazy(() => z.object({
  schemaVersion: z.string().optional(),
  artifactType: ArtifactTypeSchema.optional(),
  name: z.string(),
  description: z.string().nullable().optional(),
  application: z.string(),
  cube: z.string(),
  folder: z.string().optional(),
  referenceTemplate: ReferenceTemplateSchema.nullable().optional(),
  pov: z.array(AxisMemberSchema).optional(),
  pages: z.array(AxisMemberSchema).optional(),
  rows: z.array(AxisMemberSchema).optional(),
  columns: z.array(AxisMemberSchema).optional(),
  display: DisplayOptionsSchema.optional(),
  businessRuleAssociations: z.array(BusinessRuleAssociationSchema).optional(),
  contextVersion: z.string().nullable().optional(),
  generation: GenerationMetadataSchema.nullable().optional(),
}));

export const FormWorkflowStateSchema = z.enum(["REQUEST_RECEIVED", "REQUIREMENTS_COLLECTING", "CONTEXT_SEARCHING", "REFERENCE_FORM_SELECTING", "SPECIFICATION_DRAFTED", "VALIDATING", "PREVIEW_READY", "AWAITING_USER_CHANGES", "AWAITING_APPROVAL", "BUILDING_ARTIFACT", "DEPLOYING", "VERIFYING", "COMPLETED", "CONTEXT_REQUIRED", "MEMBER_NOT_FOUND", "AMBIGUOUS_MEMBER", "INVALID_SPECIFICATION", "PACKAGE_BUILD_FAILED", "DEPLOYMENT_FAILED", "VERIFICATION_FAILED", "CANCELLED"]);

export const GenerationMetadataSchema = z.lazy(() => z.object({
  rendererVersion: z.string().nullable().optional(),
  templateVersion: z.string().nullable().optional(),
  generatedAt: z.string().nullable().optional(),
  conversationId: z.string().nullable().optional(),
  messageId: z.string().nullable().optional(),
}));

export const HierarchyNodeSchema = z.lazy(() => z.object({
  name: z.string(),
  alias: z.string().nullable().optional(),
  parent: z.string().nullable().optional(),
  depth: z.number().optional(),
  hasChildren: z.boolean().optional(),
}));

export const MemberMatchSchema = z.lazy(() => z.object({
  query: z.string(),
  member: z.string(),
  alias: z.string().nullable().optional(),
  dimension: z.string(),
  application: z.string(),
  cube: z.string().nullable().optional(),
  parent: z.string().nullable().optional(),
  sourceArtifact: z.string().nullable().optional(),
  retrievalMethod: z.string().optional(),
  confidence: ConfidenceSchema.optional(),
  contextVersion: z.string().nullable().optional(),
}));

export const MemberRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  dimension: z.string(),
  application: z.string(),
  alias: z.string().nullable().optional(),
  parent: z.string().nullable().optional(),
  children: z.array(z.string()).optional(),
  storage: z.string().nullable().optional(),
  level: z.number().nullable().optional(),
  formula: z.string().nullable().optional(),
  dataType: z.string().nullable().optional(),
}));

export const MemberSelectionSchema = z.lazy(() => z.object({
  type: SelectionTypeSchema,
  member: z.string().nullable().optional(),
  members: z.array(z.string()).nullable().optional(),
  start: z.string().nullable().optional(),
  end: z.string().nullable().optional(),
  offsetStart: z.number().nullable().optional(),
  offsetEnd: z.number().nullable().optional(),
  variable: z.string().nullable().optional(),
  attribute: z.string().nullable().optional(),
  namedSelection: z.string().nullable().optional(),
}));

export const MessageOutSchema = z.lazy(() => z.object({
  id: z.string(),
  conversationId: z.string(),
  role: MessageRoleSchema,
  content: z.string(),
  blocks: z.array(ChatBlockSchema).optional(),
  processSteps: z.array(ProcessStepSchema).optional(),
  parentId: z.string().nullable().optional(),
  createdAt: z.string(),
  model: z.string().nullable().optional(),
  provider: z.string().nullable().optional(),
  usage: z.record(z.string(), z.unknown()).nullable().optional(),
}));

export const MessageRoleSchema = z.enum(["user", "assistant", "system"]);

export const MissingSuggestionSchema = z.lazy(() => z.object({
  dimension: z.string(),
  suggestedHandling: z.string(),
}));

export const NegativeStyleSchema = z.enum(["minus", "parentheses", "red", "redParentheses"]);

export const OperationClassSchema = z.enum(["readOnly", "execution", "modifying", "destructive"]);

export const PreviewAxisSchema = z.lazy(() => z.object({
  kind: z.string(),
  dimension: z.string(),
  selectionSummary: z.string(),
  resolvedCount: z.number().optional(),
  sampleMembers: z.array(ResolvedMemberSchema).optional(),
  suppressMissing: z.boolean().optional(),
  truncated: z.boolean().optional(),
}));

export const ProcessStepSchema = z.lazy(() => z.object({
  key: z.string(),
  label: z.string(),
  state: ProcessStepStateSchema.optional(),
}));

export const ProcessStepStateSchema = z.enum(["pending", "active", "done", "error"]);

export const ProjectOutSchema = z.lazy(() => z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  isDefault: z.boolean().optional(),
  activeEnvironmentId: z.string().nullable().optional(),
  activeContextVersionId: z.string().nullable().optional(),
  settings: z.record(z.string(), z.unknown()).optional(),
  conversationCount: z.number().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
}));

export const PromptEditRequestSchema = z.lazy(() => z.object({
  artifactKind: ArtifactKindSchema,
  scope: EditScopeSchema.optional(),
  instruction: z.string(),
  spec: z.record(z.string(), z.unknown()),
  gridIndex: z.number().optional(),
  rowLabel: z.string().nullable().optional(),
  columnLabel: z.string().nullable().optional(),
}));

export const PromptEditResultSchema = z.lazy(() => z.object({
  changed: z.boolean(),
  changes: z.array(z.string()).optional(),
  questions: z.array(z.string()).optional(),
  spec: z.record(z.string(), z.unknown()).optional(),
  preview: z.record(z.string(), z.unknown()).nullable().optional(),
  validation: z.record(z.string(), z.unknown()).nullable().optional(),
}));

export const PromptMappingSchema = z.lazy(() => z.object({
  promptName: z.string(),
  source: z.string().optional(),
  dimension: z.string().nullable().optional(),
  value: z.string().nullable().optional(),
}));

export const ProviderOutSchema = z.lazy(() => z.object({
  id: z.string(),
  name: z.string(),
  providerType: z.string(),
  baseUrl: z.string().nullable().optional(),
  defaultModel: z.string().nullable().optional(),
  models: z.array(z.string()).optional(),
  roleModels: z.record(z.string(), z.unknown()).optional(),
  enabled: z.boolean().optional(),
  hasKey: z.boolean().optional(),
}));

export const ReferenceTemplateSchema = z.lazy(() => z.object({
  type: z.string().optional(),
  name: z.string(),
}));

export const ReportCellSchema = z.lazy(() => z.object({
  value: z.number().nullable().optional(),
  formatted: z.string().optional(),
  color: z.string().nullable().optional(),
  background: z.string().nullable().optional(),
  bold: z.boolean().optional(),
  negative: z.boolean().optional(),
  note: z.string().nullable().optional(),
}));

export const ReportChartSchema = z.lazy(() => z.object({
  type: ChartTypeSchema.optional(),
  title: z.string().nullable().optional(),
  seriesFrom: z.string().optional(),
  stacked: z.boolean().optional(),
}));

export const ReportGridSchema = z.lazy(() => z.object({
  name: z.string().optional(),
  pov: z.array(AxisMemberSchema).optional(),
  pages: z.array(AxisMemberSchema).optional(),
  rows: z.array(AxisMemberSchema).optional(),
  columns: z.array(AxisMemberSchema).optional(),
  smartFormat: SmartFormatSchema.optional(),
  columnFormats: z.record(z.string(), SmartFormatSchema).optional(),
  cellOverrides: z.record(z.string(), CellOverrideSchema).optional(),
  showRowTotals: z.boolean().optional(),
  showColumnTotals: z.boolean().optional(),
  chart: ReportChartSchema.nullable().optional(),
}));

export const ReportGridPreviewSchema = z.lazy(() => z.object({
  name: z.string(),
  pov: z.array(z.string()).optional(),
  pages: z.array(z.string()).optional(),
  columnLabels: z.array(z.string()).optional(),
  rows: z.array(ReportRowPreviewSchema).optional(),
  columnTotals: z.array(ReportCellSchema).optional(),
  showRowTotals: z.boolean().optional(),
  showColumnTotals: z.boolean().optional(),
  rowsTruncated: z.boolean().optional(),
  columnsTruncated: z.boolean().optional(),
  chartType: z.string().optional(),
  chartTitle: z.string().nullable().optional(),
  sizeEstimate: SizeEstimateSchema.nullable().optional(),
}));

export const ReportPreviewSchema = z.lazy(() => z.object({
  reportName: z.string(),
  application: z.string(),
  cube: z.string(),
  folder: z.string(),
  reportType: z.string().optional(),
  validationStatus: z.string().optional(),
  useAliases: z.boolean().optional(),
  ruleAssociations: z.array(z.string()).optional(),
  grids: z.array(ReportGridPreviewSchema).optional(),
}));

export const ReportRowPreviewSchema = z.lazy(() => z.object({
  label: z.string(),
  cells: z.array(ReportCellSchema).optional(),
  total: ReportCellSchema.nullable().optional(),
}));

export const ReportSpecificationSchema = z.lazy(() => z.object({
  schemaVersion: z.string().optional(),
  reportType: ReportTypeSchema.optional(),
  name: z.string(),
  description: z.string().nullable().optional(),
  application: z.string(),
  cube: z.string(),
  folder: z.string().optional(),
  grids: z.array(ReportGridSchema).optional(),
  display: DisplayOptionsSchema.optional(),
  businessRuleAssociations: z.array(BusinessRuleAssociationSchema).optional(),
  contextVersion: z.string().nullable().optional(),
  generation: GenerationMetadataSchema.nullable().optional(),
}));

export const ReportTypeSchema = z.enum(["grid", "dashboard", "financial"]);

export const ResolvedMemberSchema = z.lazy(() => z.object({
  name: z.string(),
  alias: z.string().nullable().optional(),
}));

export const RuleExecutionOutSchema = z.lazy(() => z.object({
  id: z.string(),
  projectId: z.string(),
  ruleName: z.string(),
  application: z.string().nullable().optional(),
  cube: z.string().nullable().optional(),
  status: z.string(),
  promptValues: z.record(z.string(), z.unknown()).optional(),
  jobResult: z.string().nullable().optional(),
  durationMs: z.number().nullable().optional(),
  output: z.string().nullable().optional(),
  demoMode: z.boolean().optional(),
  createdAt: z.string(),
}));

export const RuleExecutionReportSchema = z.lazy(() => z.object({
  ruleName: z.string(),
  application: z.string(),
  cube: z.string().nullable().optional(),
  status: RuleExecutionStatusSchema.optional(),
  promptValues: z.record(z.string(), z.string()).optional(),
  jobId: z.string().nullable().optional(),
  jobResult: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  endedAt: z.string().nullable().optional(),
  durationMs: z.number().nullable().optional(),
  output: z.string().nullable().optional(),
  errors: z.array(z.string()).optional(),
}));

export const RuleExecutionStatusSchema = z.enum(["waitingForPrompts", "ready", "queued", "running", "completed", "failed", "cancelled", "unknown"]);

export const RuleRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  application: z.string(),
  cube: z.string().nullable().optional(),
  type: z.string().optional(),
  runtimePrompts: z.array(z.string()).optional(),
  hasSource: z.boolean().optional(),
}));

export const RuleSpecificationSchema = z.lazy(() => z.object({
  schemaVersion: z.string().optional(),
  name: z.string(),
  type: RuleTypeSchema.optional(),
  application: z.string(),
  cube: z.string(),
  purpose: z.string().nullable().optional(),
  runtimePrompts: z.array(RuntimePromptSchema).optional(),
  referencedDimensions: z.array(z.string()).optional(),
  referencedMembers: z.array(z.string()).optional(),
  referencedVariables: z.array(z.string()).optional(),
  formAssociations: z.array(z.string()).optional(),
  source: z.string().nullable().optional(),
  contextVersion: z.string().nullable().optional(),
  generation: GenerationMetadataSchema.nullable().optional(),
}));

export const RuleTypeSchema = z.enum(["businessRule", "calcScript", "groovy", "ruleset"]);

export const RuntimePromptSchema = z.lazy(() => z.object({
  name: z.string(),
  promptText: z.string().nullable().optional(),
  type: RuntimePromptTypeSchema.optional(),
  dimension: z.string().nullable().optional(),
  defaultValue: z.string().nullable().optional(),
  required: z.boolean().optional(),
  choices: z.array(z.string()).nullable().optional(),
}));

export const RuntimePromptFormPayloadSchema = z.lazy(() => z.object({
  ruleName: z.string(),
  application: z.string(),
  cube: z.string().nullable().optional(),
  fields: z.array(z.record(z.string(), z.unknown())).optional(),
  prefilledFrom: z.record(z.string(), z.string()).optional(),
  actions: z.array(ChatActionSchema).optional(),
}));

export const RuntimePromptTypeSchema = z.enum(["member", "members", "dimension", "numeric", "text", "date", "percent", "smartList", "crossDimension"]);

export const SelectionTypeSchema = z.enum(["member", "memberList", "children", "inclusiveChildren", "descendants", "inclusiveDescendants", "levelZeroDescendants", "ancestors", "inclusiveAncestors", "siblings", "range", "relativeRange", "substitutionVariable", "userVariable", "attribute", "povReference", "pageReference", "namedSelection"]);

export const SeveritySchema = z.enum(["error", "warning", "info"]);

export const SizeEstimateSchema = z.lazy(() => z.object({
  rowCombinations: z.number().optional(),
  columnCombinations: z.number().optional(),
  pageCombinations: z.number().optional(),
  totalCells: z.number().optional(),
  warningThreshold: z.number().optional(),
}));

export const SkillSpecSchema = z.lazy(() => z.object({
  name: z.string(),
  description: z.string(),
  intentExamples: z.array(z.string()).optional(),
  requiredContext: z.boolean().optional(),
  allowedTools: z.array(z.string()).optional(),
  approvalRequired: z.boolean().optional(),
  version: z.string().optional(),
}));

export const SmartFormatSchema = z.lazy(() => z.object({
  decimalPlaces: z.number().optional(),
  thousandsSeparator: z.boolean().optional(),
  scale: z.number().optional(),
  negativeStyle: NegativeStyleSchema.optional(),
  prefix: z.string().optional(),
  suffix: z.string().optional(),
  conditionalRules: z.array(ConditionalRuleSchema).optional(),
}));

export const StreamEventSchema = z.lazy(() => z.object({
  type: StreamEventTypeSchema,
  data: z.record(z.string(), z.unknown()).optional(),
}));

export const StreamEventTypeSchema = z.enum(["title", "process", "token", "block", "toolCall", "toolResult", "messageSaved", "error", "done", "usage"]);

export const SubsystemStatusSchema = z.lazy(() => z.object({
  name: z.string(),
  status: z.string(),
  detail: z.string().nullable().optional(),
}));

export const ToolCallSchema = z.lazy(() => z.object({
  name: z.string(),
  arguments: z.record(z.string(), z.unknown()).optional(),
}));

export const ToolInvocationPayloadSchema = z.lazy(() => z.object({
  tool: z.string(),
  operationClass: z.string(),
  status: z.string(),
  summary: z.string().nullable().optional(),
  detail: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
}));

export const ToolResultSchema = z.lazy(() => z.object({
  name: z.string(),
  ok: z.boolean().optional(),
  data: z.record(z.string(), z.unknown()).optional(),
  error: z.string().nullable().optional(),
  errorCategory: z.string().nullable().optional(),
  operationClass: OperationClassSchema.optional(),
  durationMs: z.number().nullable().optional(),
}));

export const ToolSpecSchema = z.lazy(() => z.object({
  name: z.string(),
  description: z.string(),
  operationClass: OperationClassSchema.optional(),
  readOnly: z.boolean().optional(),
  modifiesOracle: z.boolean().optional(),
  requiredRole: z.string().optional(),
  requiresApproval: z.boolean().optional(),
  timeoutS: z.number().optional(),
  retryable: z.boolean().optional(),
  audit: z.boolean().optional(),
}));

export const ValidationIssueSchema = z.lazy(() => z.object({
  layer: ValidationLayerSchema,
  severity: SeveritySchema,
  code: z.string(),
  message: z.string(),
  path: z.string().nullable().optional(),
  suggestedFix: z.string().nullable().optional(),
  candidates: z.array(z.string()).optional(),
}));

export const ValidationLayerSchema = z.enum(["schema", "application", "axis", "selection", "display", "performance", "security", "deployment"]);

export const ValidationReportSchema = z.lazy(() => z.object({
  schemaVersion: z.string().optional(),
  artifactName: z.string(),
  valid: z.boolean().optional(),
  blocking: z.boolean().optional(),
  issues: z.array(ValidationIssueSchema).optional(),
  sizeEstimate: SizeEstimateSchema.nullable().optional(),
  resolvedMemberCounts: z.record(z.string(), z.number()).optional(),
}));

export const VariableRecordSchema = z.lazy(() => z.object({
  name: z.string(),
  application: z.string(),
  scope: z.string().optional(),
  dimension: z.string().nullable().optional(),
  value: z.string().nullable().optional(),
  cube: z.string().nullable().optional(),
}));
