export interface Memory {
  id: string;
  memory: string;
  user_id?: string;
  agent_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MemorySearchResult extends Memory {
  score?: number;
}

export interface MemoryHistoryEntry {
  id: string;
  memory_id: string;
  old_memory: string;
  new_memory: string;
  event: string;
  created_at: string;
  updated_at: string;
  is_deleted: boolean;
  actor_id?: string;
  role?: string;
}

export interface ApiKey {
  id: string;
  label: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiKeyCreateResponse {
  id: string;
  label: string;
  key: string;
  key_prefix: string;
  created_at: string;
}

export interface ApiRequestLog {
  id: string;
  created_at: string;
  method: string;
  path: string;
  status_code: number;
  latency_ms: number;
  auth_type: string;
}

export type EntityType = "user" | "agent" | "run";

export interface Entity {
  id: string;
  type: EntityType;
  total_memories: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface EvolveSearchWindow {
  total_queries: number;
  zero_hit_rate: number;
  avg_score: number;
  avg_latency_ms: number;
}

export interface EvolveTrendPoint {
  date: string;
  queries: number;
  avg_score: number;
  zero_hits: number;
}

export interface EvolveZeroHit {
  query: string;
  count: number;
}

export interface EvolveTypeDistribution {
  useful: number;
  useless: number;
  correction: number;
}

export interface EvolveMostCorrected {
  memory_id: string;
  count: number;
}

export interface EvolveScoreDistribution {
  "lt_0.5": number;
  "0.5_0.9": number;
  "0.9_1.1": number;
  "gt_1.1": number;
}

export interface EvolveHighFrequency {
  memory_id: string;
  access_count: number;
  salience_score: number;
}

export interface EvolveIdleMemory {
  memory_id: string;
  access_count: number;
  last_access_at: string | null;
}

export interface EvolveRetainResponse {
  memory_id: string;
  last_access_at: string;
}

export interface EvolveBoostRecord {
  memory_id: string;
  delta: number;
  created_at: string | null;
}

export interface EvolveOperationsWindow {
  total_requests: number;
  avg_latency_ms: number;
  success_rate: number;
}

export interface RecallStageStat {
  stage: string;
  avg_count: number;
  avg_latency_ms: number;
}

export interface RecallTraceSample {
  query: string;
  created_at: string | null;
  stages: { stage: string; count: number; latency_ms: number }[];
}

export interface RecallReport {
  stages: RecallStageStat[];
  recent: RecallTraceSample[];
}

export interface EvolveReport {
  search_quality: {
    windows: Record<string, EvolveSearchWindow>;
    daily_trend: EvolveTrendPoint[];
    top_zero_hits: EvolveZeroHit[];
  };
  feedback: {
    type_distribution: EvolveTypeDistribution;
    most_corrected: EvolveMostCorrected[];
  };
  heat: {
    score_distribution: EvolveScoreDistribution;
    high_frequency: EvolveHighFrequency[];
    stale: EvolveIdleMemory[];
    boost_adjustments: EvolveBoostRecord[];
  };
  operations: {
    windows: Record<string, EvolveOperationsWindow>;
  };
  recall: RecallReport;
}
