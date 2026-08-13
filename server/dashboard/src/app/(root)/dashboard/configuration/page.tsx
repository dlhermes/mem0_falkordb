"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/components/ui/use-toast";
import { getErrorMessage } from "@/lib/error-message";
import { api } from "@/utils/api";
import { MEMORY_ENDPOINTS } from "@/utils/api-endpoints";
import {
  buildProviderConfig,
  getEffectiveConfig,
} from "@/utils/self-hosted-config";
import { useAuth } from "@/hooks/use-auth";
import { useApiQuery } from "@/hooks/use-api-query";

type BundledProviders = {
  llm: string[];
  embedder: string[];
};

const RERANKER_PROVIDERS = ["siliconflow", "llm_reranker"];

const MAX_LLM_FALLBACKS = 2;

type ProviderSnapshot = {
  provider: string;
  model: string;
  baseUrl: string;
};

type FallbackRow = ProviderSnapshot & { apiKey: string };

type GraphStoreSnapshot = {
  provider: string;
  config: { host: string; port: string; database: string };
  llm: ProviderSnapshot;
  embedder: ProviderSnapshot;
  threshold: string;
  customPrompt: string;
};

export default function ConfigurationPage() {
  const { isAdmin } = useAuth();
  const [isSaving, setIsSaving] = useState(false);

  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmFallbacks, setLlmFallbacks] = useState<FallbackRow[]>([]);

  const [embedderProvider, setEmbedderProvider] = useState("");
  const [embedderModel, setEmbedderModel] = useState("");
  const [embedderApiKey, setEmbedderApiKey] = useState("");
  const [embedderBaseUrl, setEmbedderBaseUrl] = useState("");

  const [rerankerProvider, setRerankerProvider] = useState("");
  const [rerankerModel, setRerankerModel] = useState("");
  const [rerankerApiKey, setRerankerApiKey] = useState("");
  const [rerankerBaseUrl, setRerankerBaseUrl] = useState("");

  const [enableSearchDepth, setEnableSearchDepth] = useState(false);
  const [enableLane, setEnableLane] = useState(false);
  const [rerankThreshold, setRerankThreshold] = useState("");
  const [customInstructions, setCustomInstructions] = useState("");

  const [graphStoreProvider, setGraphStoreProvider] = useState("falkordb");
  const [graphStoreHost, setGraphStoreHost] = useState("");
  const [graphStorePort, setGraphStorePort] = useState("");
  const [graphStoreDatabase, setGraphStoreDatabase] = useState("");

  const [graphStoreLlmProvider, setGraphStoreLlmProvider] = useState("");
  const [graphStoreLlmModel, setGraphStoreLlmModel] = useState("");
  const [graphStoreLlmApiKey, setGraphStoreLlmApiKey] = useState("");
  const [graphStoreLlmBaseUrl, setGraphStoreLlmBaseUrl] = useState("");

  const [graphStoreEmbedderProvider, setGraphStoreEmbedderProvider] =
    useState("");
  const [graphStoreEmbedderModel, setGraphStoreEmbedderModel] = useState("");
  const [graphStoreEmbedderApiKey, setGraphStoreEmbedderApiKey] = useState("");
  const [graphStoreEmbedderBaseUrl, setGraphStoreEmbedderBaseUrl] =
    useState("");

  const [graphStoreThreshold, setGraphStoreThreshold] = useState("");
  const [graphStoreCustomPrompt, setGraphStoreCustomPrompt] = useState("");

  const initialRef = useRef<{
    llm?: ProviderSnapshot;
    llmFallbacks: ProviderSnapshot[];
    embedder?: ProviderSnapshot;
    reranker?: ProviderSnapshot;
    graphStore: GraphStoreSnapshot;
    enableSearchDepth: boolean;
    enableLane: boolean;
    rerankThreshold: number | null;
    customInstructions: string;
  }>({
    enableSearchDepth: false,
    enableLane: false,
    rerankThreshold: null,
    customInstructions: "",
    llmFallbacks: [],
    graphStore: {
      provider: "",
      config: { host: "", port: "", database: "" },
      llm: { provider: "", model: "", baseUrl: "" },
      embedder: { provider: "", model: "", baseUrl: "" },
      threshold: "",
      customPrompt: "",
    },
  });

  const {
    data: config,
    isLoading: isPrefilling,
    refetch,
  } = useApiQuery(
    async () => {
      const res = await api.get(MEMORY_ENDPOINTS.CONFIGURE);
      return getEffectiveConfig(res.data);
    },
    { errorToast: "加载服务器配置失败" },
  );

  const { data: providers } = useApiQuery<BundledProviders>(
    async () => {
      const res = await api.get<BundledProviders>(
        MEMORY_ENDPOINTS.CONFIGURE_PROVIDERS,
      );
      return res.data;
    },
    { errorToast: "加载内置提供商失败" },
  );

  useEffect(() => {
    if (!config) return;

    setLlmProvider((current) => current || config.llm?.provider || "");
    setLlmModel((current) => current || config.llm?.config?.model || "");
    setLlmBaseUrl(
      (current) => current || config.llm?.config?.openai_base_url || "",
    );
    setLlmFallbacks((current) =>
      current.length
        ? current
        : (config.llm?.fallbacks || []).map((f) => ({
            provider: f.provider || "",
            model: f.config?.model || "",
            apiKey: "",
            baseUrl: f.config?.openai_base_url || "",
          })),
    );
    setEmbedderProvider(
      (current) => current || config.embedder?.provider || "",
    );
    setEmbedderModel(
      (current) => current || config.embedder?.config?.model || "",
    );
    setEmbedderBaseUrl(
      (current) => current || config.embedder?.config?.openai_base_url || "",
    );
    setRerankerProvider(
      (current) => current || config.reranker?.provider || "",
    );
    setRerankerModel(
      (current) => current || config.reranker?.config?.model || "",
    );
    setRerankerBaseUrl(
      (current) =>
        current || config.reranker?.config?.siliconflow_base_url || "",
    );
    setEnableSearchDepth(config.enable_search_depth ?? false);
    setEnableLane(config.enable_lane ?? false);
    setRerankThreshold(
      config.rerank_score_threshold != null
        ? String(config.rerank_score_threshold)
        : "",
    );
    setCustomInstructions(
      (current) => current || config.custom_instructions || "",
    );

    setGraphStoreProvider(
      (current) => current || config.graph_store?.provider || "falkordb",
    );
    setGraphStoreHost(
      (current) => current || config.graph_store?.config?.host || "",
    );
    setGraphStorePort(
      (current) =>
        current ||
        (config.graph_store?.config?.port != null
          ? String(config.graph_store.config.port)
          : ""),
    );
    setGraphStoreDatabase(
      (current) => current || config.graph_store?.config?.database || "",
    );
    setGraphStoreLlmProvider(
      (current) => current || config.graph_store?.llm?.provider || "",
    );
    setGraphStoreLlmModel(
      (current) => current || config.graph_store?.llm?.config?.model || "",
    );
    setGraphStoreLlmBaseUrl(
      (current) =>
        current || config.graph_store?.llm?.config?.openai_base_url || "",
    );
    setGraphStoreEmbedderProvider(
      (current) => current || config.graph_store?.embedder?.provider || "",
    );
    setGraphStoreEmbedderModel(
      (current) => current || config.graph_store?.embedder?.config?.model || "",
    );
    setGraphStoreEmbedderBaseUrl(
      (current) =>
        current || config.graph_store?.embedder?.config?.openai_base_url || "",
    );
    setGraphStoreThreshold(
      (current) =>
        current ||
        (config.graph_store?.threshold != null
          ? String(config.graph_store.threshold)
          : ""),
    );
    setGraphStoreCustomPrompt(
      (current) => current || config.graph_store?.custom_prompt || "",
    );

    initialRef.current = {
      llm: {
        provider: config.llm?.provider || "",
        model: config.llm?.config?.model || "",
        baseUrl: config.llm?.config?.openai_base_url || "",
      },
      llmFallbacks: (config.llm?.fallbacks || []).map((f) => ({
        provider: f.provider || "",
        model: f.config?.model || "",
        baseUrl: f.config?.openai_base_url || "",
      })),
      embedder: {
        provider: config.embedder?.provider || "",
        model: config.embedder?.config?.model || "",
        baseUrl: config.embedder?.config?.openai_base_url || "",
      },
      reranker: {
        provider: config.reranker?.provider || "",
        model: config.reranker?.config?.model || "",
        baseUrl: config.reranker?.config?.siliconflow_base_url || "",
      },
      graphStore: {
        provider: config.graph_store?.provider || "",
        config: {
          host: config.graph_store?.config?.host || "",
          port:
            config.graph_store?.config?.port != null
              ? String(config.graph_store.config.port)
              : "",
          database: config.graph_store?.config?.database || "",
        },
        llm: {
          provider: config.graph_store?.llm?.provider || "",
          model: config.graph_store?.llm?.config?.model || "",
          baseUrl: config.graph_store?.llm?.config?.openai_base_url || "",
        },
        embedder: {
          provider: config.graph_store?.embedder?.provider || "",
          model: config.graph_store?.embedder?.config?.model || "",
          baseUrl: config.graph_store?.embedder?.config?.openai_base_url || "",
        },
        threshold:
          config.graph_store?.threshold != null
            ? String(config.graph_store.threshold)
            : "",
        customPrompt: config.graph_store?.custom_prompt || "",
      },
      enableSearchDepth: config.enable_search_depth ?? false,
      enableLane: config.enable_lane ?? false,
      rerankThreshold: config.rerank_score_threshold ?? null,
      customInstructions: config.custom_instructions || "",
    };
  }, [config]);

  const handleSave = async () => {
    setIsSaving(true);

    try {
      const base = initialRef.current;
      const newConfig: Record<string, unknown> = {};

      const hasProviderChanges = (
        provider: string,
        model: string,
        baseUrl: string,
        apiKey: string,
        snapshot?: ProviderSnapshot,
      ) =>
        provider !== (snapshot?.provider || "") ||
        model !== (snapshot?.model || "") ||
        baseUrl !== (snapshot?.baseUrl || "") ||
        (apiKey && apiKey !== "[redacted]");

      const llmChanged = hasProviderChanges(
        llmProvider,
        llmModel,
        llmBaseUrl,
        llmApiKey,
        base.llm,
      );

      if (llmChanged) {
        const llm = buildProviderConfig({
          provider: llmProvider,
          model: llmModel,
          apiKey: llmApiKey,
          baseUrl: llmBaseUrl,
        });
        if (llm) {
          newConfig.llm = llm;
        }
      }

      const effectiveFallbacks = llmFallbacks.filter((f) => f.provider);
      const llmFallbacksChanged =
        effectiveFallbacks.length !== base.llmFallbacks.length ||
        effectiveFallbacks.some((f, i) => {
          const s = base.llmFallbacks[i];
          return (
            f.provider !== s.provider ||
            f.model !== s.model ||
            f.baseUrl !== s.baseUrl ||
            (f.apiKey && f.apiKey !== "[redacted]")
          );
        });

      if (llmFallbacksChanged) {
        newConfig.llm = {
          ...(newConfig.llm || {}),
          fallbacks: effectiveFallbacks.map((f) =>
            buildProviderConfig({
              provider: f.provider,
              model: f.model,
              apiKey: f.apiKey,
              baseUrl: f.baseUrl,
            }),
          ),
        };
      }

      if (
        hasProviderChanges(
          embedderProvider,
          embedderModel,
          embedderBaseUrl,
          embedderApiKey,
          base.embedder,
        )
      ) {
        const embedder = buildProviderConfig({
          provider: embedderProvider,
          model: embedderModel,
          apiKey: embedderApiKey,
          baseUrl: embedderBaseUrl,
        });
        if (embedder) {
          newConfig.embedder = embedder;
        }
      }

      if (
        hasProviderChanges(
          rerankerProvider,
          rerankerModel,
          rerankerBaseUrl,
          rerankerApiKey,
          base.reranker,
        )
      ) {
        const reranker = buildProviderConfig({
          provider: rerankerProvider,
          model: rerankerModel,
          apiKey: rerankerApiKey,
          baseUrl: rerankerBaseUrl,
          baseUrlKey: "siliconflow_base_url",
        });
        if (reranker) {
          newConfig.reranker = reranker;
        }
      }

      if (enableSearchDepth !== base.enableSearchDepth) {
        newConfig.enable_search_depth = enableSearchDepth;
      }

      const gsSnapshot = base.graphStore;
      const graphStore: Record<string, unknown> = {};
      let graphStoreHasChanges = false;

      if (graphStoreProvider !== gsSnapshot.provider) {
        graphStore.provider = graphStoreProvider;
        graphStoreHasChanges = true;
      }

      if (
        graphStoreProvider === "falkordb" &&
        (graphStoreHost !== gsSnapshot.config.host ||
          graphStorePort !== gsSnapshot.config.port ||
          graphStoreDatabase !== gsSnapshot.config.database)
      ) {
        graphStore.config = {
          host: graphStoreHost,
          port: graphStorePort ? Number(graphStorePort) : "",
          database: graphStoreDatabase,
        };
        graphStoreHasChanges = true;
      } else if (graphStoreProvider === "memory" && graphStore.provider) {
        graphStore.config = {};
        graphStoreHasChanges = true;
      }

      if (
        hasProviderChanges(
          graphStoreLlmProvider,
          graphStoreLlmModel,
          graphStoreLlmBaseUrl,
          graphStoreLlmApiKey,
          gsSnapshot.llm,
        )
      ) {
        const llm = buildProviderConfig({
          provider: graphStoreLlmProvider,
          model: graphStoreLlmModel,
          apiKey: graphStoreLlmApiKey,
          baseUrl: graphStoreLlmBaseUrl,
        });
        if (llm) {
          graphStore.llm = llm;
          graphStoreHasChanges = true;
        } else if (gsSnapshot.llm.provider) {
          graphStore.llm = null;
          graphStoreHasChanges = true;
        }
      }

      if (
        hasProviderChanges(
          graphStoreEmbedderProvider,
          graphStoreEmbedderModel,
          graphStoreEmbedderBaseUrl,
          graphStoreEmbedderApiKey,
          gsSnapshot.embedder,
        )
      ) {
        const embedder = buildProviderConfig({
          provider: graphStoreEmbedderProvider,
          model: graphStoreEmbedderModel,
          apiKey: graphStoreEmbedderApiKey,
          baseUrl: graphStoreEmbedderBaseUrl,
        });
        if (embedder) {
          graphStore.embedder = embedder;
          graphStoreHasChanges = true;
        } else if (gsSnapshot.embedder.provider) {
          graphStore.embedder = null;
          graphStoreHasChanges = true;
        }
      }

      const parsedGraphStoreThreshold =
        graphStoreThreshold.trim() === ""
          ? ""
          : String(Number(graphStoreThreshold));
      if (parsedGraphStoreThreshold !== gsSnapshot.threshold) {
        graphStore.threshold =
          parsedGraphStoreThreshold === ""
            ? null
            : Number(parsedGraphStoreThreshold);
        graphStoreHasChanges = true;
      }

      if (graphStoreCustomPrompt !== gsSnapshot.customPrompt) {
        graphStore.custom_prompt = graphStoreCustomPrompt || null;
        graphStoreHasChanges = true;
      }

      if (graphStoreHasChanges) {
        newConfig.graph_store = graphStore;
      }

      if (enableLane !== base.enableLane) {
        newConfig.enable_lane = enableLane;
      }

      const parsedThreshold =
        rerankThreshold.trim() === "" ? null : Number(rerankThreshold);
      if (parsedThreshold !== base.rerankThreshold) {
        newConfig.rerank_score_threshold = parsedThreshold;
      }

      if (customInstructions !== base.customInstructions) {
        newConfig.custom_instructions = customInstructions;
      }

      if (Object.keys(newConfig).length > 0) {
        await api.post(MEMORY_ENDPOINTS.CONFIGURE, newConfig);
        await refetch();
      }

      toast({
        title: "配置已保存到 config.json",
        description: "已热生效，重启容器后持久保留",
        variant: "success",
      });
    } catch (error) {
      toast({
        title: "保存配置失败",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const renderProviderFields = ({
    provider,
    onProviderChange,
    model,
    onModelChange,
    apiKey,
    onApiKeyChange,
    baseUrl,
    onBaseUrlChange,
    providers,
  }: {
    provider: string;
    onProviderChange: (value: string) => void;
    model: string;
    onModelChange: (value: string) => void;
    apiKey: string;
    onApiKeyChange: (value: string) => void;
    baseUrl: string;
    onBaseUrlChange: (value: string) => void;
    providers?: string[];
  }) => (
    <>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">提供商</Label>
          <Select
            value={provider}
            onValueChange={(value) => {
              onProviderChange(value);
              onApiKeyChange("");
            }}
            disabled={!isAdmin || !providers || providers.length === 0}
          >
            <SelectTrigger>
              <SelectValue placeholder="选择提供商" />
            </SelectTrigger>
            <SelectContent>
              {(providers || []).map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">模型</Label>
          <Input
            placeholder="model-name"
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            disabled={!isAdmin}
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">API 密钥</Label>
        <Input
          type="password"
          placeholder="已配置则留空不修改"
          value={apiKey}
          onChange={(e) => onApiKeyChange(e.target.value)}
          disabled={!isAdmin}
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Base URL</Label>
        <Input
          placeholder="https://api.example.com/v1"
          value={baseUrl}
          onChange={(e) => onBaseUrlChange(e.target.value)}
          disabled={!isAdmin}
        />
      </div>
    </>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold font-fustat">配置</h1>
          {isPrefilling && (
            <p className="text-xs text-onSurface-default-tertiary">
              正在加载服务器配置...
            </p>
          )}
        </div>
      </div>

      <Card className="border-memBorder-primary">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-sm">LLM 提供商</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          {renderProviderFields({
            provider: llmProvider,
            onProviderChange: setLlmProvider,
            model: llmModel,
            onModelChange: setLlmModel,
            apiKey: llmApiKey,
            onApiKeyChange: setLlmApiKey,
            baseUrl: llmBaseUrl,
            onBaseUrlChange: setLlmBaseUrl,
            providers: providers?.llm,
          })}

          <div className="space-y-3 border-t border-memBorder-primary pt-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs">兜底模型</Label>
              {llmFallbacks.length >= MAX_LLM_FALLBACKS && (
                <span className="text-xs text-onSurface-default-tertiary">
                  最多 {MAX_LLM_FALLBACKS} 个兜底模型
                </span>
              )}
            </div>

            {llmFallbacks.length === 0 && (
              <p className="text-xs text-onSurface-default-tertiary">
                未配置兜底模型，主 LLM 不可用时将直接报错
              </p>
            )}

            {llmFallbacks.map((fallback, index) => (
              <div
                key={index}
                className="space-y-3 rounded-lg border border-memBorder-primary p-3"
              >
                <div className="flex items-center justify-between">
                  <Label className="text-xs">兜底 {index + 1}</Label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setLlmFallbacks((prev) =>
                        prev.filter((_, i) => i !== index),
                      )
                    }
                    disabled={!isAdmin}
                  >
                    删除
                  </Button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">提供商</Label>
                    <Select
                      value={fallback.provider}
                      onValueChange={(value) =>
                        setLlmFallbacks((prev) =>
                          prev.map((f, i) =>
                            i === index
                              ? { ...f, provider: value, apiKey: "" }
                              : f,
                          ),
                        )
                      }
                      disabled={
                        !isAdmin ||
                        !providers?.llm ||
                        providers.llm.length === 0
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="选择提供商" />
                      </SelectTrigger>
                      <SelectContent>
                        {(providers?.llm || []).map((name) => (
                          <SelectItem key={name} value={name}>
                            {name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">模型</Label>
                    <Input
                      placeholder="model-name"
                      value={fallback.model}
                      onChange={(e) =>
                        setLlmFallbacks((prev) =>
                          prev.map((f, i) =>
                            i === index ? { ...f, model: e.target.value } : f,
                          ),
                        )
                      }
                      disabled={!isAdmin}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">API 密钥</Label>
                  <Input
                    type="password"
                    placeholder="已配置则留空不修改"
                    value={fallback.apiKey}
                    onChange={(e) =>
                      setLlmFallbacks((prev) =>
                        prev.map((f, i) =>
                          i === index ? { ...f, apiKey: e.target.value } : f,
                        ),
                      )
                    }
                    disabled={!isAdmin}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Base URL</Label>
                  <Input
                    placeholder="https://api.example.com/v1"
                    value={fallback.baseUrl}
                    onChange={(e) =>
                      setLlmFallbacks((prev) =>
                        prev.map((f, i) =>
                          i === index ? { ...f, baseUrl: e.target.value } : f,
                        ),
                      )
                    }
                    disabled={!isAdmin}
                  />
                </div>
              </div>
            ))}

            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() =>
                setLlmFallbacks((prev) => [
                  ...prev,
                  { provider: "", model: "", apiKey: "", baseUrl: "" },
                ])
              }
              disabled={!isAdmin || llmFallbacks.length >= MAX_LLM_FALLBACKS}
            >
              添加兜底
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-sm">嵌入模型</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          {renderProviderFields({
            provider: embedderProvider,
            onProviderChange: setEmbedderProvider,
            model: embedderModel,
            onModelChange: setEmbedderModel,
            apiKey: embedderApiKey,
            onApiKeyChange: setEmbedderApiKey,
            baseUrl: embedderBaseUrl,
            onBaseUrlChange: setEmbedderBaseUrl,
            providers: providers?.embedder,
          })}
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-sm">Reranker</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          {renderProviderFields({
            provider: rerankerProvider,
            onProviderChange: setRerankerProvider,
            model: rerankerModel,
            onModelChange: setRerankerModel,
            apiKey: rerankerApiKey,
            onApiKeyChange: setRerankerApiKey,
            baseUrl: rerankerBaseUrl,
            onBaseUrlChange: setRerankerBaseUrl,
            providers: RERANKER_PROVIDERS,
          })}
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-sm">图数据存储</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">提供商</Label>
              <Select
                value={graphStoreProvider}
                onValueChange={setGraphStoreProvider}
                disabled={!isAdmin}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择提供商" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="memory">memory</SelectItem>
                  <SelectItem value="falkordb">falkordb</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {graphStoreProvider === "falkordb" && (
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">主机</Label>
                <Input
                  placeholder="localhost"
                  value={graphStoreHost}
                  onChange={(e) => setGraphStoreHost(e.target.value)}
                  disabled={!isAdmin}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">端口</Label>
                <Input
                  placeholder="6379"
                  value={graphStorePort}
                  onChange={(e) => setGraphStorePort(e.target.value)}
                  disabled={!isAdmin}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">数据库</Label>
                <Input
                  placeholder="mem0"
                  value={graphStoreDatabase}
                  onChange={(e) => setGraphStoreDatabase(e.target.value)}
                  disabled={!isAdmin}
                />
              </div>
            </div>
          )}

          <div className="space-y-3 rounded-lg border border-memBorder-primary p-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs">独立 LLM</Label>
              {!graphStoreLlmProvider && (
                <span className="text-xs text-onSurface-default-tertiary">
                  未单独配置，使用全局 LLM
                </span>
              )}
            </div>
            {renderProviderFields({
              provider: graphStoreLlmProvider,
              onProviderChange: setGraphStoreLlmProvider,
              model: graphStoreLlmModel,
              onModelChange: setGraphStoreLlmModel,
              apiKey: graphStoreLlmApiKey,
              onApiKeyChange: setGraphStoreLlmApiKey,
              baseUrl: graphStoreLlmBaseUrl,
              onBaseUrlChange: setGraphStoreLlmBaseUrl,
              providers: providers?.llm,
            })}
          </div>

          <div className="space-y-3 rounded-lg border border-memBorder-primary p-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs">独立 Embedder</Label>
              {!graphStoreEmbedderProvider && (
                <span className="text-xs text-onSurface-default-tertiary">
                  未单独配置，使用全局嵌入模型
                </span>
              )}
            </div>
            {renderProviderFields({
              provider: graphStoreEmbedderProvider,
              onProviderChange: setGraphStoreEmbedderProvider,
              model: graphStoreEmbedderModel,
              onModelChange: setGraphStoreEmbedderModel,
              apiKey: graphStoreEmbedderApiKey,
              onApiKeyChange: setGraphStoreEmbedderApiKey,
              baseUrl: graphStoreEmbedderBaseUrl,
              onBaseUrlChange: setGraphStoreEmbedderBaseUrl,
              providers: providers?.embedder,
            })}
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">实体匹配阈值</Label>
              <p className="text-xs text-onSurface-default-tertiary">
                低于该阈值的实体匹配会被过滤
              </p>
            </div>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              className="w-32 text-right tabular-nums"
              placeholder="0.7"
              value={graphStoreThreshold}
              onChange={(e) => setGraphStoreThreshold(e.target.value)}
              disabled={!isAdmin}
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs">实体提取提示（可选）</Label>
            <Textarea
              className="h-[120px]"
              placeholder="可选的实体提取提示，用于指导图实体抽取..."
              value={graphStoreCustomPrompt}
              onChange={(e) => setGraphStoreCustomPrompt(e.target.value)}
              disabled={!isAdmin}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-sm">检索参数</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">深度检索</Label>
              <p className="text-xs text-onSurface-default-tertiary">
                对结果进行多轮深度检索
              </p>
            </div>
            <Switch
              checked={enableSearchDepth}
              onCheckedChange={setEnableSearchDepth}
              disabled={!isAdmin}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">车道</Label>
              <p className="text-xs text-onSurface-default-tertiary">
                启用多通道并行检索
              </p>
            </div>
            <Switch
              checked={enableLane}
              onCheckedChange={setEnableLane}
              disabled={!isAdmin}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">重排阈值</Label>
              <p className="text-xs text-onSurface-default-tertiary">
                低于该分数的结果会被过滤
              </p>
            </div>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              className="w-32 text-right tabular-nums"
              placeholder="0.5"
              value={rerankThreshold}
              onChange={(e) => setRerankThreshold(e.target.value)}
              disabled={!isAdmin}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-sm">提取指令</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          <Textarea
            className="h-[160px]"
            placeholder="可选的提取指令，用于指导记忆提取..."
            value={customInstructions}
            onChange={(e) => setCustomInstructions(e.target.value)}
            disabled={!isAdmin}
          />
        </CardContent>
      </Card>

      <p className="text-xs text-onSurface-default-tertiary">
        需要其他提供商？安装对应的 Python 包、重新构建镜像并扩展内置列表。请参阅{" "}
        <a
          href="https://docs.mem0.ai/open-source/setup#supported-providers"
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-4 hover:text-onSurface-default-primary"
        >
          设置指南
        </a>
        。
      </p>

      {isAdmin && (
        <Button onClick={handleSave} disabled={isSaving}>
          {isSaving ? "保存中..." : "保存配置"}
        </Button>
      )}
    </div>
  );
}
