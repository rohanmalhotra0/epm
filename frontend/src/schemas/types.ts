/* eslint-disable */
// ---------------------------------------------------------------------------
// GENERATED FILE — DO NOT EDIT BY HAND.
// Source of truth: backend Pydantic models (app/schemas/*.py).
// Regenerate with:  python -m scripts.export_schema  (from backend/)
// A backend drift test fails if this file is out of sync.
// ---------------------------------------------------------------------------


export interface ApplicationRecord {
  name: string;
  type?: string;
  description?: string | null;
}

export type ArtifactKind =
  "formSpec" |
  "reportSpec";

export interface ArtifactOut {
  id: string;
  projectId: string;
  kind: string;
  name: string;
  version?: number;
  checksum?: string | null;
  contextVersion?: string | null;
  hasContent?: boolean;
  hasFile?: boolean;
  payload?: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export type ArtifactType =
  "planningForm" |
  "businessRule" |
  "calcScript" |
  "groovyRule" |
  "ruleset" |
  "contextPackage";

export interface AxisMember {
  dimension: string;
  selection: MemberSelection;
  suppressMissing?: boolean;
}

export interface BusinessRuleAssociation {
  ruleName: string;
  ruleType?: string;
  /** actionMenu | runAfterSave | runBeforeSave | manualLaunch | epmWizardOnly */
  associationType?: string;
  promptMappings: Array<PromptMapping>;
}

export interface CellIntersection {
  application: string;
  cube: string;
  members: Array<CellMember>;
  expression?: string;
  note?: string;
}

export interface CellMember {
  dimension: string;
  member: string;
  source?: string;
}

export interface CellOverride {
  /** Override the sampled value */
  value?: number | null;
  /** Per-cell formatting override */
  format?: SmartFormat | null;
  /** Analyst annotation shown on hover */
  note?: string | null;
}

export type ChartType =
  "none" |
  "bar" |
  "line" |
  "area" |
  "pie";

export interface ChatAction {
  key: string;
  label: string;
  value: string;
  style?: string;
  disabled?: boolean;
}

export interface ChatBlock {
  id: string;
  type: ChatBlockType;
  data: Record<string, unknown>;
}

export type ChatBlockType =
  "markdown" |
  "code" |
  "formPreview" |
  "formSpecification" |
  "reportPreview" |
  "reportSpecification" |
  "rulePreview" |
  "runtimePromptForm" |
  "memberSearchResults" |
  "contextSummary" |
  "validationReport" |
  "deploymentPlan" |
  "deploymentProgress" |
  "deploymentResult" |
  "diff" |
  "confirmation" |
  "spreadsheetPreview" |
  "snapshotSummary" |
  "groundingSources" |
  "downloadableFile" |
  "errorDiagnostics" |
  "connectionStatus" |
  "toolInvocation" |
  "processSteps" |
  "cubeArchitecture" |
  "cellIntersection" |
  "cubeComparison" |
  "dimensionCoverage" |
  "dimensionHierarchy";

export type Comparator =
  "lt" |
  "le" |
  "gt" |
  "ge" |
  "eq" |
  "ne";

export type CompletenessStatus =
  "complete" |
  "partial" |
  "derived" |
  "unavailable" |
  "notRequested";

export interface ConditionalRule {
  comparator?: Comparator;
  value?: number;
  /** Hex text colour, e.g. #da1e28 */
  color?: string | null;
  /** Hex cell background */
  background?: string | null;
  bold?: boolean;
  label?: string | null;
}

export type Confidence =
  "exact" |
  "high" |
  "medium" |
  "low";

export interface ConfirmationPayload {
  prompt: string;
  detail?: string | null;
  actions: Array<ChatAction>;
  severity?: Severity;
}

export interface ConnectionResult {
  connected: boolean;
  environmentId: string;
  message: string;
  application?: string | null;
  detail?: string | null;
  diagnostics: Record<string, unknown>;
}

export interface ConnectionStatusPayload {
  connected: boolean;
  environmentName?: string | null;
  classification?: EnvironmentClassification | null;
  application?: string | null;
  contextStatus?: string | null;
  demoMode?: boolean;
}

export interface ContextManifest {
  format?: string;
  schemaVersion?: string;
  generatedAt: string;
  application: string;
  environmentClassification: EnvironmentClassification;
  environmentFingerprint: string;
  mode: ContextMode;
  counts: Record<string, number>;
  includedFiles: Array<string>;
  checksums: Record<string, string>;
  sections: Array<ContextSectionStatus>;
  knownLimitations: Array<string>;
  contextVersion: string;
}

export type ContextMode =
  "quick" |
  "deep" |
  "imported" |
  "snapshot" |
  "hybrid";

export interface ContextSectionStatus {
  name: string;
  status: CompletenessStatus;
  count?: number;
  note?: string | null;
}

export interface ContextVersionOut {
  id: string;
  projectId: string;
  application: string;
  label: string;
  mode: string;
  counts: Record<string, unknown>;
  active?: boolean;
  manifest: Record<string, unknown>;
  createdAt: string;
}

export interface ConversationOut {
  id: string;
  projectId: string;
  title: string;
  pinned?: boolean;
  archived?: boolean;
  provider?: string | null;
  model?: string | null;
  lastMessageAt?: string | null;
  messageCount?: number;
  createdAt: string;
  updatedAt: string;
}

export interface CrossDimArea {
  area: string;
  detail: string;
  count: number;
}

export interface CrossDimSize {
  cube: string;
  areas: Array<CrossDimArea>;
  totalPotentialCells?: number;
  sizeEstimate?: SizeEstimate | null;
  warning?: string | null;
  label?: string;
}

export interface CubeArchitecture {
  application: string;
  cube: string;
  cubeType?: string | null;
  dimensionCount?: number;
  dimensions: Array<DimensionNode>;
  formName?: string | null;
  formCoverage?: FormCoverage | null;
}

export interface CubeComparison {
  application: string;
  cubeA: string;
  cubeB: string;
  rows: Array<CubeComparisonRow>;
  shared?: number;
  onlyA: Array<string>;
  onlyB: Array<string>;
}

export interface CubeComparisonRow {
  dimension: string;
  inA: boolean;
  inB: boolean;
  detailA?: string | null;
  detailB?: string | null;
}

export interface CubeRecord {
  name: string;
  application: string;
  type?: string;
  description?: string | null;
  dimensions: Array<string>;
}

export type DeploymentOperation =
  "create" |
  "update" |
  "replace" |
  "delete";

export interface DeploymentOut {
  id: string;
  projectId: string;
  conversationId?: string | null;
  environmentName?: string | null;
  classification: string;
  application?: string | null;
  artifactName: string;
  artifactType: string;
  operation: string;
  operationClass: string;
  approved: boolean;
  success: boolean;
  verified: boolean;
  demoMode: boolean;
  checksum?: string | null;
  contextVersion?: string | null;
  rollbackAvailable?: boolean;
  report: Record<string, unknown>;
  errors: Array<string>;
  warnings: Array<string>;
  createdAt: string;
}

export interface DeploymentPlan {
  schemaVersion?: string;
  artifactType: ArtifactType;
  artifactName: string;
  application: string;
  cube?: string | null;
  folder?: string | null;
  environmentName: string;
  environmentClassification: EnvironmentClassification;
  operation: DeploymentOperation;
  operationClass?: OperationClass;
  overwritesExisting?: boolean;
  backupRequired?: boolean;
  validationPassed?: boolean;
  contextFresh?: boolean;
  demoMode?: boolean;
  requiresConfirmationPhrase?: boolean;
  steps: Array<DeploymentStep>;
  warnings: Array<string>;
}

export interface DeploymentReport {
  plan: DeploymentPlan;
  state?: FormWorkflowState;
  success?: boolean;
  verified?: boolean;
  verificationNotes: Array<string>;
  jobId?: string | null;
  jobResult?: string | null;
  packageChecksum?: string | null;
  backupArtifact?: string | null;
  rollbackAvailable?: boolean;
  startedAt?: string | null;
  endedAt?: string | null;
  durationMs?: number | null;
  errors: Array<string>;
  warnings: Array<string>;
}

export interface DeploymentStep {
  key: string;
  label: string;
  status?: DeploymentStepStatus;
  detail?: string | null;
  startedAt?: string | null;
  endedAt?: string | null;
}

export type DeploymentStepStatus =
  "pending" |
  "running" |
  "completed" |
  "failed" |
  "skipped";

export interface DiagnosticsReport {
  appVersion: string;
  subsystems: Array<SubsystemStatus>;
  storagePath: string;
  activeProvider?: string | null;
  activeModel?: string | null;
  demoMode?: boolean;
  schemaVersions: Record<string, unknown>;
  featureFlags: Record<string, unknown>;
  redactionHealthy?: boolean;
}

export interface DiffPayload {
  title: string;
  before: string;
  after: string;
  language?: string;
}

export interface DimensionCoverageReport {
  cube: string;
  valid?: boolean;
  coveredDimensions: Array<string>;
  missingDimensions: Array<string>;
  duplicateDimensions: Array<string>;
  invalidSelections: Array<string>;
  warnings: Array<string>;
  suggestions: Array<MissingSuggestion>;
}

export interface DimensionHierarchy {
  application: string;
  dimension: string;
  root: string;
  nodes: Array<HierarchyNode>;
  truncated?: boolean;
  cap?: number;
}

export interface DimensionNode {
  name: string;
  alias?: string | null;
  type?: string;
  group?: string;
  memberCount?: number | null;
  rootMembers: Array<string>;
  selectedMember?: string | null;
  selectionSummary?: string | null;
  usedOnAxis?: string | null;
  status?: string;
}

export interface DimensionRecord {
  name: string;
  application: string;
  type?: string;
  cubes: Array<string>;
  dense?: boolean | null;
}

export interface DisplayOptions {
  useAliases?: boolean;
  aliasTable?: string;
  hiddenMembers: Array<string>;
  suppressMissingRows?: boolean;
  suppressMissingColumns?: boolean;
  readOnly?: boolean;
}

export interface DownloadableFilePayload {
  filename: string;
  artifactId: string;
  mediaType?: string;
  sizeBytes?: number | null;
  checksum?: string | null;
}

export type EditScope =
  "artifact" |
  "table" |
  "cell";

export type EnvironmentClassification =
  "development" |
  "test" |
  "production";

export interface EnvironmentOut {
  id: string;
  projectId: string;
  name: string;
  baseUrl?: string | null;
  username?: string | null;
  authMethod?: string;
  classification: EnvironmentClassification;
  preferredApplication?: string | null;
  demo?: boolean;
  connected?: boolean;
  lastConnectedAt?: string | null;
  lastContextRefreshAt?: string | null;
}

export interface ErrorDiagnosticsPayload {
  category: string;
  message: string;
  likelyCause?: string | null;
  suggestedAction?: string | null;
  technicalDetail?: string | null;
  actions: Array<ChatAction>;
}

export interface FormCoverage {
  pov: Array<Record<string, unknown>>;
  pages: Array<Record<string, unknown>>;
  rows: Array<Record<string, unknown>>;
  columns: Array<Record<string, unknown>>;
  implicitOrDefault: Array<string>;
  missing: Array<string>;
  duplicate: Array<string>;
}

export interface FormPreview {
  formName: string;
  application: string;
  cube: string;
  folder: string;
  validationStatus?: string;
  referenceTemplate?: string | null;
  useAliases?: boolean;
  hiddenMembers: Array<string>;
  ruleAssociations: Array<string>;
  pov: Array<PreviewAxis>;
  pages: Array<PreviewAxis>;
  rows: Array<PreviewAxis>;
  columns: Array<PreviewAxis>;
  rowLabels: Array<string>;
  columnLabels: Array<string>;
  rowsTruncated?: boolean;
  columnsTruncated?: boolean;
  sizeEstimate?: SizeEstimate | null;
}

export interface FormRecord {
  name: string;
  application: string;
  cube?: string | null;
  folder?: string | null;
  description?: string | null;
  definition?: Record<string, unknown> | null;
}

export interface FormSpecification {
  schemaVersion?: string;
  artifactType?: ArtifactType;
  name: string;
  description?: string | null;
  application: string;
  cube: string;
  folder?: string;
  referenceTemplate?: ReferenceTemplate | null;
  pov: Array<AxisMember>;
  pages: Array<AxisMember>;
  rows: Array<AxisMember>;
  columns: Array<AxisMember>;
  display?: DisplayOptions;
  businessRuleAssociations: Array<BusinessRuleAssociation>;
  contextVersion?: string | null;
  generation?: GenerationMetadata | null;
}

export type FormWorkflowState =
  "REQUEST_RECEIVED" |
  "REQUIREMENTS_COLLECTING" |
  "CONTEXT_SEARCHING" |
  "REFERENCE_FORM_SELECTING" |
  "SPECIFICATION_DRAFTED" |
  "VALIDATING" |
  "PREVIEW_READY" |
  "AWAITING_USER_CHANGES" |
  "AWAITING_APPROVAL" |
  "BUILDING_ARTIFACT" |
  "DEPLOYING" |
  "VERIFYING" |
  "COMPLETED" |
  "CONTEXT_REQUIRED" |
  "MEMBER_NOT_FOUND" |
  "AMBIGUOUS_MEMBER" |
  "INVALID_SPECIFICATION" |
  "PACKAGE_BUILD_FAILED" |
  "DEPLOYMENT_FAILED" |
  "VERIFICATION_FAILED" |
  "CANCELLED";

export interface GenerationMetadata {
  rendererVersion?: string | null;
  templateVersion?: string | null;
  generatedAt?: string | null;
  conversationId?: string | null;
  messageId?: string | null;
}

export interface GroundingChunk {
  kind: string;
  name: string;
  cube?: string | null;
  dimension?: string | null;
  snippet: string;
  score: number;
  method: string;
  contextVersion?: string | null;
}

export interface HierarchyNode {
  name: string;
  alias?: string | null;
  parent?: string | null;
  depth?: number;
  hasChildren?: boolean;
}

export interface MemberMatch {
  query: string;
  member: string;
  alias?: string | null;
  dimension: string;
  application: string;
  cube?: string | null;
  parent?: string | null;
  sourceArtifact?: string | null;
  retrievalMethod?: string;
  confidence?: Confidence;
  contextVersion?: string | null;
}

export interface MemberRecord {
  name: string;
  dimension: string;
  application: string;
  alias?: string | null;
  parent?: string | null;
  children: Array<string>;
  storage?: string | null;
  level?: number | null;
  formula?: string | null;
  dataType?: string | null;
}

export interface MemberSelection {
  type: SelectionType;
  /** Anchor member for hierarchy functions */
  member?: string | null;
  /** Explicit member list */
  members?: Array<string> | null;
  /** Range start member */
  start?: string | null;
  /** Range end member */
  end?: string | null;
  /** relativeRange start offset */
  offsetStart?: number | null;
  /** relativeRange end offset */
  offsetEnd?: number | null;
  /** Substitution or user variable name */
  variable?: string | null;
  /** Attribute dimension member */
  attribute?: string | null;
  /** Existing named member selection */
  namedSelection?: string | null;
}

export interface MessageOut {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: string;
  blocks: Array<ChatBlock>;
  processSteps: Array<ProcessStep>;
  parentId?: string | null;
  createdAt: string;
  model?: string | null;
  provider?: string | null;
  usage?: Record<string, unknown> | null;
}

export type MessageRole =
  "user" |
  "assistant" |
  "system";

export interface MissingSuggestion {
  dimension: string;
  suggestedHandling: string;
}

export type NegativeStyle =
  "minus" |
  "parentheses" |
  "red" |
  "redParentheses";

export type OperationClass =
  "readOnly" |
  "execution" |
  "modifying" |
  "destructive";

export interface PreviewAxis {
  kind: string;
  dimension: string;
  selectionSummary: string;
  resolvedCount?: number;
  sampleMembers: Array<ResolvedMember>;
  suppressMissing?: boolean;
  truncated?: boolean;
}

export interface ProcessStep {
  key: string;
  label: string;
  state?: ProcessStepState;
}

export type ProcessStepState =
  "pending" |
  "active" |
  "done" |
  "error";

export interface ProjectOut {
  id: string;
  name: string;
  description?: string | null;
  isDefault?: boolean;
  activeEnvironmentId?: string | null;
  activeContextVersionId?: string | null;
  settings: Record<string, unknown>;
  conversationCount?: number;
  createdAt: string;
  updatedAt: string;
}

export interface PromptEditRequest {
  artifactKind: ArtifactKind;
  scope?: EditScope;
  instruction: string;
  /** Current artifact spec (camelCase JSON) */
  spec: Record<string, unknown>;
  /** Target grid for table/cell scope (reports) */
  gridIndex?: number;
  /** Target row label for cell scope */
  rowLabel?: string | null;
  /** Target column label for cell scope */
  columnLabel?: string | null;
}

export interface PromptEditResult {
  changed: boolean;
  changes: Array<string>;
  questions: Array<string>;
  /** Updated spec (camelCase JSON) */
  spec: Record<string, unknown>;
  /** Fresh preview for the updated spec */
  preview?: Record<string, unknown> | null;
  /** Fresh validation report (forms only) */
  validation?: Record<string, unknown> | null;
}

export interface PromptMapping {
  promptName: string;
  /** formPov | formPage | gridMember | fixed | userEntered */
  source?: string;
  dimension?: string | null;
  value?: string | null;
}

export interface ProviderOut {
  id: string;
  name: string;
  providerType: string;
  baseUrl?: string | null;
  defaultModel?: string | null;
  models: Array<string>;
  roleModels: Record<string, unknown>;
  enabled?: boolean;
  hasKey?: boolean;
}

export interface ReferenceTemplate {
  /** existingForm | projectTemplate | goldenTemplate | generic */
  type?: string;
  name: string;
}

export interface ReportCell {
  value?: number | null;
  formatted?: string;
  color?: string | null;
  background?: string | null;
  bold?: boolean;
  negative?: boolean;
  note?: string | null;
}

export interface ReportChart {
  type?: ChartType;
  title?: string | null;
  /** 'columns' or 'rows' — which axis becomes series */
  seriesFrom?: string;
  stacked?: boolean;
}

export interface ReportGrid {
  name?: string;
  pov: Array<AxisMember>;
  pages: Array<AxisMember>;
  rows: Array<AxisMember>;
  columns: Array<AxisMember>;
  smartFormat?: SmartFormat;
  columnFormats: Record<string, SmartFormat>;
  cellOverrides: Record<string, CellOverride>;
  showRowTotals?: boolean;
  showColumnTotals?: boolean;
  chart?: ReportChart | null;
}

export interface ReportGridPreview {
  name: string;
  pov: Array<string>;
  pages: Array<string>;
  columnLabels: Array<string>;
  rows: Array<ReportRowPreview>;
  columnTotals: Array<ReportCell>;
  showRowTotals?: boolean;
  showColumnTotals?: boolean;
  rowsTruncated?: boolean;
  columnsTruncated?: boolean;
  chartType?: string;
  chartTitle?: string | null;
  sizeEstimate?: SizeEstimate | null;
}

export interface ReportPreview {
  reportName: string;
  application: string;
  cube: string;
  folder: string;
  reportType?: string;
  validationStatus?: string;
  useAliases?: boolean;
  ruleAssociations: Array<string>;
  grids: Array<ReportGridPreview>;
}

export interface ReportRowPreview {
  label: string;
  cells: Array<ReportCell>;
  total?: ReportCell | null;
}

export interface ReportSpecification {
  schemaVersion?: string;
  reportType?: ReportType;
  name: string;
  description?: string | null;
  application: string;
  cube: string;
  folder?: string;
  grids: Array<ReportGrid>;
  display?: DisplayOptions;
  businessRuleAssociations: Array<BusinessRuleAssociation>;
  contextVersion?: string | null;
  generation?: GenerationMetadata | null;
}

export type ReportType =
  "grid" |
  "dashboard" |
  "financial";

export interface ResolvedMember {
  name: string;
  alias?: string | null;
}

export interface RuleExecutionOut {
  id: string;
  projectId: string;
  ruleName: string;
  application?: string | null;
  cube?: string | null;
  status: string;
  promptValues: Record<string, unknown>;
  jobResult?: string | null;
  durationMs?: number | null;
  output?: string | null;
  demoMode?: boolean;
  createdAt: string;
}

export interface RuleExecutionReport {
  ruleName: string;
  application: string;
  cube?: string | null;
  status?: RuleExecutionStatus;
  promptValues: Record<string, string>;
  jobId?: string | null;
  jobResult?: string | null;
  startedAt?: string | null;
  endedAt?: string | null;
  durationMs?: number | null;
  output?: string | null;
  errors: Array<string>;
}

export type RuleExecutionStatus =
  "waitingForPrompts" |
  "ready" |
  "queued" |
  "running" |
  "completed" |
  "failed" |
  "cancelled" |
  "unknown";

export interface RuleRecord {
  name: string;
  application: string;
  cube?: string | null;
  type?: string;
  runtimePrompts: Array<string>;
  hasSource?: boolean;
}

export interface RuleSpecification {
  schemaVersion?: string;
  name: string;
  type?: RuleType;
  application: string;
  cube: string;
  purpose?: string | null;
  runtimePrompts: Array<RuntimePrompt>;
  referencedDimensions: Array<string>;
  referencedMembers: Array<string>;
  referencedVariables: Array<string>;
  formAssociations: Array<string>;
  source?: string | null;
  contextVersion?: string | null;
  generation?: GenerationMetadata | null;
}

export type RuleType =
  "businessRule" |
  "calcScript" |
  "groovy" |
  "ruleset";

export interface RuntimePrompt {
  name: string;
  promptText?: string | null;
  type?: RuntimePromptType;
  dimension?: string | null;
  defaultValue?: string | null;
  required?: boolean;
  choices?: Array<string> | null;
}

export interface RuntimePromptFormPayload {
  ruleName: string;
  application: string;
  cube?: string | null;
  fields: Array<Record<string, unknown>>;
  prefilledFrom: Record<string, string>;
  actions: Array<ChatAction>;
}

export type RuntimePromptType =
  "member" |
  "members" |
  "dimension" |
  "numeric" |
  "text" |
  "date" |
  "percent" |
  "smartList" |
  "crossDimension";

export type SelectionType =
  "member" |
  "memberList" |
  "children" |
  "inclusiveChildren" |
  "descendants" |
  "inclusiveDescendants" |
  "levelZeroDescendants" |
  "ancestors" |
  "inclusiveAncestors" |
  "siblings" |
  "range" |
  "relativeRange" |
  "substitutionVariable" |
  "userVariable" |
  "attribute" |
  "povReference" |
  "pageReference" |
  "namedSelection";

export type Severity =
  "error" |
  "warning" |
  "info";

export interface SizeEstimate {
  rowCombinations?: number;
  columnCombinations?: number;
  pageCombinations?: number;
  totalCells?: number;
  warningThreshold?: number;
}

export interface SkillSpec {
  name: string;
  description: string;
  intentExamples: Array<string>;
  requiredContext?: boolean;
  allowedTools: Array<string>;
  approvalRequired?: boolean;
  version?: string;
}

export interface SmartFormat {
  decimalPlaces?: number;
  thousandsSeparator?: boolean;
  /** Divide display value by 10**scale (0=none, 3=K, 6=M) */
  scale?: number;
  negativeStyle?: NegativeStyle;
  /** Leading symbol, e.g. $ */
  prefix?: string;
  /** Trailing symbol, e.g. % */
  suffix?: string;
  conditionalRules: Array<ConditionalRule>;
}

export interface SnapshotAnalysis {
  filename?: string | null;
  application?: string | null;
  applications: Array<string>;
  provenance?: SnapshotProvenance | null;
  components: Array<SnapshotComponent>;
  cubes: Array<string>;
  dimensions: Array<string>;
  counts: Record<string, number>;
  issues: Array<string>;
}

export interface SnapshotComponent {
  key: string;
  product: string;
  application: string;
  artifactCount?: number;
}

export interface SnapshotProvenance {
  exportedBy?: string | null;
  exportedAt?: string | null;
  serviceInstance?: string | null;
  domain?: string | null;
  exportedVersion?: string | null;
}

export interface StreamEvent {
  type: StreamEventType;
  data: Record<string, unknown>;
}

export type StreamEventType =
  "title" |
  "process" |
  "token" |
  "block" |
  "toolCall" |
  "toolResult" |
  "messageSaved" |
  "error" |
  "done" |
  "usage";

export interface SubsystemStatus {
  name: string;
  status: string;
  detail?: string | null;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolInvocationPayload {
  tool: string;
  operationClass: string;
  status: string;
  summary?: string | null;
  detail?: string | null;
  error?: string | null;
}

export interface ToolResult {
  name: string;
  ok?: boolean;
  data: Record<string, unknown>;
  error?: string | null;
  errorCategory?: string | null;
  operationClass?: OperationClass;
  durationMs?: number | null;
}

export interface ToolSpec {
  name: string;
  description: string;
  operationClass?: OperationClass;
  readOnly?: boolean;
  modifiesOracle?: boolean;
  requiredRole?: string;
  requiresApproval?: boolean;
  timeoutS?: number;
  retryable?: boolean;
  audit?: boolean;
}

export interface ValidationIssue {
  layer: ValidationLayer;
  severity: Severity;
  code: string;
  message: string;
  path?: string | null;
  suggestedFix?: string | null;
  candidates: Array<string>;
}

export type ValidationLayer =
  "schema" |
  "application" |
  "axis" |
  "selection" |
  "display" |
  "performance" |
  "security" |
  "deployment";

export interface ValidationReport {
  schemaVersion?: string;
  artifactName: string;
  valid?: boolean;
  blocking?: boolean;
  issues: Array<ValidationIssue>;
  sizeEstimate?: SizeEstimate | null;
  resolvedMemberCounts: Record<string, number>;
}

export interface VariableRecord {
  name: string;
  application: string;
  scope?: string;
  dimension?: string | null;
  value?: string | null;
  cube?: string | null;
}
