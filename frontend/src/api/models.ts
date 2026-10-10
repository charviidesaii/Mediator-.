/**
 * TypeScript interfaces matching the Mediator FastAPI backend OpenAPI schemas.
 */

export interface TeamMember {
  id: string;
  name: string;
  role?: string | null;
  email?: string | null;
  created_at?: string;
  // UI helper properties
  initials?: string;
  tone?: "dark" | "lilac" | "petal" | "slate";
}

export interface TeamMemberCreate {
  name: string;
  role?: string | null;
  email?: string | null;
}

export interface Project {
  id: string;
  title: string;
  description?: string | null;
  created_at?: string;
  members: TeamMember[];
}

export interface ProjectCreate {
  title: string;
  description?: string | null;
}

export interface MemberResponseSubmit {
  member_name: string;
  raw_text: string;
  source?: string;
}

export interface MemberResponse {
  id: string;
  project_id: string;
  member_name: string;
  raw_text: string;
  source: string;
  submitted_at: string;
}

export type ConflictSeverity = "HIGH" | "MEDIUM" | "LOW";
export type ConflictCategory = "DIRECT_DISAGREEMENT" | "COMPATIBLE_DIFFERENCE" | "UNRESOLVED_DEPENDENCY";
export type ConflictType =
  | "DEADLINE_CONTRADICTION"
  | "GOAL_INCOMPATIBILITY"
  | "PRIORITY_MISMATCH"
  | "RESPONSIBILITY_OVERLAP_OR_GAP"
  | "INFORMATION_GAP"
  | "PROCESS_MISALIGNMENT";

export interface EvidenceItem {
  member_name: string;
  quote: string;
  interpretation: string;
}

export interface DetectedConflict {
  conflict_id: string;
  title: string;
  conflict_type: ConflictType;
  category: ConflictCategory;
  severity: ConflictSeverity;
  severity_reasoning: string;
  parties_involved: string[];
  evidence: EvidenceItem[];
  impact_description: string;
}

export interface ResolutionOption {
  option_id: string;
  title: string;
  description: string;
  pros: string[];
  cons: string[];
  compromise_notes: string;
}

export interface ProposedResolution {
  resolution_id: string;
  conflict_id: string;
  conflict_title: string;
  recommended_solution: string;
  reasoning: string;
  alternative_options: ResolutionOption[];
  impacted_members: string[];
  unresolved_questions_for_team: string[];
  status: "PROPOSED";
}

export interface SynthesisReport {
  report_id: string;
  project_id: string;
  executive_summary: string;
  alignment_score: number;
  key_findings: string[];
  proposed_resolutions: ProposedResolution[];
  human_action_items: string[];
  disclaimer: string;
  generated_at: string;
}

export interface PerspectiveItem {
  statement: string;
  source_quote: string;
  clarity?: string;
}

export interface ExtractedPerspective {
  member_name: string;
  goals: Array<{ statement: string; source_quote: string; clarity?: string }>;
  priorities: Array<{ priority_item: string; urgency_level: string; source_quote: string }>;
  responsibilities: Array<{ responsibility: string; assigned_to: string; source_quote: string }>;
  deadlines: Array<{ milestone: string; expected_deadline: string; is_tentative?: boolean; source_quote: string }>;
  ambiguities_or_missing_details: string[];
  key_quotes: string[];
}

export interface PerspectiveAnalysisOutput {
  perspectives: ExtractedPerspective[];
  total_members_analyzed: number;
  overall_summary: string;
  identified_gaps: string[];
}

export interface ConflictDetectionOutput {
  conflicts: DetectedConflict[];
  compatible_differences: string[];
  critical_information_gaps: string[];
  synthesis_summary: string;
}

export interface AlignmentWorkflowResult {
  workflow_id: string;
  project_id: string;
  perspectives_output: PerspectiveAnalysisOutput;
  conflicts_output: ConflictDetectionOutput;
  synthesis_output: SynthesisReport;
  intermediate_results: Record<string, unknown>;
  execution_metadata: Record<string, unknown>;
  execution_mode: string;
}

export type DecisionStatus = "PROPOSED" | "APPROVED" | "REJECTED" | "MODIFIED";

export interface DecisionActionRequest {
  resolution_id: string;
  action: "APPROVE" | "REJECT" | "MODIFY";
  decision_text?: string | null;
  decided_by: string;
  notes?: string | null;
}

export interface ConfirmedDecision {
  id: string;
  project_id: string;
  resolution_id: string;
  status: DecisionStatus;
  decision_text: string;
  decided_by: string;
  decided_at: string;
  notes?: string | null;
}

export interface APIErrorResponse {
  error: string;
  detail: string;
  status_code: number;
  timestamp: string;
}

export type ResourceState<T> =
  | { status: "idle"; data?: undefined; error?: undefined }
  | { status: "loading"; data?: undefined; error?: undefined }
  | { status: "success"; data: T; error?: undefined }
  | { status: "error"; data?: undefined; error: Error }
  | { status: "demo"; data: T; error?: Error };
