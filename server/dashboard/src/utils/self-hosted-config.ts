type ProviderConfig = {
  provider?: string;
  fallbacks?: ProviderConfig[];
  config?: {
    model?: string;
    api_key?: string;
    openai_base_url?: string;
    siliconflow_base_url?: string;
    host?: string;
    port?: number;
    database?: string;
  };
};

export type GraphStoreConfig = {
  provider?: string;
  config?: {
    host?: string;
    port?: number;
    database?: string;
  };
  llm?: ProviderConfig;
  embedder?: ProviderConfig;
  threshold?: number;
  custom_prompt?: string;
};

export type EffectiveConfig = {
  llm?: ProviderConfig;
  embedder?: ProviderConfig;
  reranker?: ProviderConfig;
  graph_store?: GraphStoreConfig;
  enable_search_depth?: boolean;
  enable_lane?: boolean;
  rerank_score_threshold?: number;
  custom_instructions?: string;
};

export const getEffectiveConfig = (data: unknown): EffectiveConfig | null => {
  if (!data || typeof data !== "object") {
    return null;
  }

  const record = data as Record<string, unknown>;
  return (
    (record.effective_config as EffectiveConfig) ||
    (record.config as EffectiveConfig) ||
    (record as EffectiveConfig)
  );
};

export const buildProviderConfig = ({
  provider,
  model,
  apiKey,
  baseUrl,
  baseUrlKey = "openai_base_url",
}: {
  provider: string;
  model: string;
  apiKey?: string;
  baseUrl?: string;
  baseUrlKey?: "openai_base_url" | "siliconflow_base_url";
}) => {
  if (!provider) {
    return undefined;
  }

  const config: Record<string, string> = {};
  if (model) {
    config.model = model;
  }
  if (apiKey && apiKey !== "[redacted]") {
    config.api_key = apiKey;
  }
  if (baseUrl) {
    config[baseUrlKey] = baseUrl;
  }

  return {
    provider,
    config,
  };
};
