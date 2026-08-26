export type PermissionLevel = 'GREEN' | 'YELLOW' | 'RED';

export interface ToolActionSpec {
  [actionName: string]: PermissionLevel;
}

export interface ToolSpec {
  enabled: boolean;
  permission_default?: PermissionLevel;
  draft_permission?: PermissionLevel;
  send_permission?: PermissionLevel;
  analysis_permission?: PermissionLevel;
  transaction_permission?: PermissionLevel;
  preview_permission?: PermissionLevel;
  production_permission?: PermissionLevel;
  description: string;
  timeout_seconds: number;
  retries: number;
  idempotent: boolean;
  secrets: string[];
  health_check: string;
  rollback: string;
  actions?: ToolActionSpec;
}

export interface RedPattern {
  id: string;
  pattern: string;
  permission: PermissionLevel;
  tools?: string[];
}

export interface Decision {
  tool: string;
  action: string;
  permission: PermissionLevel;
  reason: string;
  requires_approval: boolean;
  rollback_available: boolean;
  idempotency_key: string;
  matched_rule: string;
  audit_required: boolean;
  evidence_refs: string[];
  dispatch_plan: 'DISPATCH' | 'CHECKPOINT_AUDIT_DISPATCH' | 'REQUEST_APPROVAL_BLOCK_TASK';
}

export type TaskStatus =
  | 'QUEUED'
  | 'WAITING_FOR_APPROVAL'
  | 'DISPATCHED'
  | 'RUNNING'
  | 'VALIDATING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BLOCKED'
  | 'CANCELLED'
  | 'DEAD_LETTER';

export interface TaskItem {
  task_id: string;
  mission_id: string;
  type: string;
  priority: number;
  permission: PermissionLevel;
  status: TaskStatus;
  payload: Record<string, any>;
  created_at: string;
  scheduled_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  attempt: number;
  max_attempts: number;
  timeout_seconds: number;
  idempotency_key: string;
  depends_on: string[];
  evidence_refs: string[];
  last_error?: string | null;
  worker_id?: string | null;
  approval?: {
    approver: string;
    granted_at: string;
    expires_at?: string | null;
    scope: { task_id: string; type: string };
  };
}

export type MissionState =
  | 'CREATED'
  | 'INTAKE_VALIDATED'
  | 'PLANNED'
  | 'WAITING_FOR_APPROVAL'
  | 'QUEUED'
  | 'DISPATCHED'
  | 'RUNNING'
  | 'VALIDATING'
  | 'COMPLETED'
  | 'CLOSED'
  | 'FAILED'
  | 'BLOCKED'
  | 'CANCELLED'
  | 'ROLLED_BACK'
  | 'HARAKIRI';

export interface EvidenceItem {
  id: string;
  name: string;
  status: 'PENDING' | 'CLAIMED' | 'ARTIFACT_PRESENT' | 'MECHANICALLY_VERIFIED' | 'INDEPENDENTLY_VERIFIED';
  proof?: string;
  verified_at?: string;
}

export interface Mission {
  mission_id: string;
  title: string;
  state: MissionState;
  created_at: string;
  updated_at: string;
  // Hydra City Genesis additions
  genesis_hash?: string;
  goal?: string;
  constraints?: string[];
  scope?: string[];
  forbidden?: string[];
  required_evidence?: EvidenceItem[];
  notary_entry_id?: string;
  buzz_room_id?: string;
  assigned_worker?: string;
  apr_seal?: string;
}

export interface LedgerEvent {
  seq: number;
  mission_id: string;
  task_id: string;
  from_state: string;
  to_state: string;
  timestamp: string;
  actor: string;
  reason: string;
  evidence_refs: string[];
  previous_event_hash: string;
  event_hash: string;
}

export type ModelCapability =
  | 'text'
  | 'reasoning'
  | 'code'
  | 'tools'
  | 'long_context'
  | 'classification'
  | 'vision';

export interface ModelSpec {
  provider: string;
  context_window: number;
  local: boolean;
  capabilities: ModelCapability[];
  notes?: string;
}

export type ProviderHealthStatus = 'HEALTHY' | 'DEGRADED' | 'DOWN';

export interface ProviderHealth {
  provider: string;
  model: string;
  status: ProviderHealthStatus;
  last_check: string;
  latency_ms: number;
  recent_failures: number;
  supported_capabilities: string[];
}

export interface RoutingDecision {
  task_class: string;
  selected: string | null;
  provider: string | null;
  status: 'ROUTED' | 'DEGRADED' | 'BLOCKED';
  reason: string;
  considered: string[];
  rejected: Record<string, string>;
}

export type LeadState =
  | 'new'
  | 'researched'
  | 'audit_ready'
  | 'draft_ready'
  | 'approved_to_send'
  | 'sent'
  | 'replied'
  | 'qualified'
  | 'proposal'
  | 'won'
  | 'lost'
  | 'follow_up_due';

export interface Lead {
  lead_id: string;
  company: string;
  contact_name: string;
  email: string;
  website: string;
  industry: string;
  problem: string;
  team_size: string;
  current_tools: string[];
  urgency: string;
  estimated_value: number;
  score: number;
  consent: boolean;
  source: string;
  state: LeadState;
  created_at: string;
  updated_at: string;
  last_contact?: string;
  follow_up_date?: string;
}

export interface AuditItem {
  audit_id: string;
  lead_id: string;
  track: string;
  body: string;
  opportunity_score: number;
  created_at: string;
}

export interface DraftItem {
  draft_id: string;
  lead_id: string;
  kind: string;
  subject: string;
  body: string;
  sent: boolean;
  created_at: string;
}

export interface FollowupItem {
  followup_id: string;
  lead_id: string;
  due_date: string;
  body: string;
  done: boolean;
  created_at: string;
}

export interface ScheduleItem {
  name: string;
  cadence: string;
  script: string;
  level: PermissionLevel;
  description: string;
}

export interface SystemHealthReport {
  status: 'ok' | 'degraded';
  timestamp: string;
  checks: {
    soul: {
      ok: boolean;
      version: string;
      sha256: string;
      missing_sections: string[];
      total_bytes: number;
    };
    tools: {
      ok: boolean;
      registered: number;
      enabled: number;
    };
    models: {
      ok: boolean;
      selected: string | null;
      detail: string;
    };
    queue: {
      ok: boolean;
      counts: Record<string, number>;
      lag_seconds: number;
    };
    ledger: {
      ok: boolean;
      detail: string;
    };
    revenue: {
      ok: boolean;
      counts: Record<string, number>;
      totals: Record<string, number>;
    };
  };
}

// --------------------------------------------------------------------------
// HYDRA CITY ARCHITECTURE EXTENSIONS
// --------------------------------------------------------------------------

export interface UnderstandingGateState {
  raw_intent: string;
  understanding_score: number; // 0 - 100
  goal_clarity: 'HIGH' | 'MEDIUM' | 'LOW';
  scope_bounded: boolean;
  forbidden_defined: boolean;
  success_criteria_clear: boolean;
  verdict: 'PASS' | 'ASK_USER' | 'BLOCKED';
  clarification_needed?: string[];
  compiled_genesis?: {
    goal: string;
    constraints: string[];
    scope: string[];
    forbidden: string[];
    required_evidence: string[];
  };
}

export interface WorkerLease {
  lease_id: string;
  worker_id: string;
  worker_name: string;
  role: 'PRIMARY_BUILDER' | 'SPECIALIST' | 'AUDITOR' | 'SCOUT';
  mission_id: string;
  task_id: string;
  granted_at: string;
  expires_at: string;
  heartbeat_at: string;
  status: 'ACTIVE' | 'EXPIRED' | 'REVOKED' | 'HANDOFF_PENDING';
  checkpoint_hash: string;
  budget_tokens_limit: number;
  budget_tokens_used: number;
}

export type PinokioVerificationLevel =
  | 'CLAIMED'
  | 'ARTIFACT_PRESENT'
  | 'MECHANICALLY_VERIFIED'
  | 'INDEPENDENTLY_VERIFIED'
  | 'REJECTED';

export interface PinokioClaim {
  claim_id: string;
  worker_id: string;
  worker_name: string;
  mission_id: string;
  claim_text: string;
  claim_type: 'BUILD' | 'TEST' | 'DEPLOY' | 'HEALTH' | 'SECURITY';
  verification_level: PinokioVerificationLevel;
  command_executed: string;
  exit_code?: number;
  artifact_path?: string;
  artifact_sha256?: string;
  timestamp: string;
  notes: string;
}

export interface BuzzMessage {
  id: string;
  room_id: string;
  sender_id: string;
  sender_name: string;
  role: 'OPERATOR' | 'GOVERNMENT' | 'RUNTIME' | 'MICHAEL_ANGELO' | 'NOTARY' | 'APR' | 'OBSERVATORY';
  text: string;
  timestamp: string;
  type: 'INTENT' | 'EVENT' | 'TELEMETRY' | 'APPROVAL' | 'SEAL' | 'WARNING';
}

export interface BuzzRoom {
  room_id: string;
  mission_id: string;
  name: string;
  topic: string;
  status: 'ACTIVE' | 'ARCHIVED';
  created_at: string;
  participants: Array<{ id: string; name: string; role: string; avatar: string }>;
  messages: BuzzMessage[];
}

export interface GcpServiceStatus {
  service_name: string;
  type: 'Cloud Run' | 'Cloud Logging' | 'Secret Manager' | 'Workload Identity' | 'Cloud Storage';
  status: 'READY' | 'HEALTHY' | 'UPDATING' | 'DEGRADED';
  revision: string;
  preview_url: string;
  region: string;
  last_health_check: string;
  traffic_share: number;
  memory_limit: string;
  cpu_limit: string;
}

export interface NotaryLedgerEntry {
  entry_id: string;
  mission_id: string;
  opened_at: string;
  sealed_at?: string | null;
  genesis_hash: string;
  source_sha: string;
  events_count: number;
  status: 'OPEN' | 'SEALED' | 'TAMPER_DETECTED';
  notary_seal_hash?: string;
  apr_proof_receipt?: string;
}
