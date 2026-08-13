"use client";

import { useEffect, useState } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import { RefreshCw } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { DataTable } from "@/components/shared/data-table";
import { TableSkeleton } from "@/components/shared/table-skeleton";
import { getErrorMessage } from "@/lib/error-message";
import { api } from "@/utils/api";
import { EVOLVE_ENDPOINTS, MEMORY_ENDPOINTS } from "@/utils/api-endpoints";
import { useApiQuery } from "@/hooks/use-api-query";
import { toast } from "@/components/ui/use-toast";
import type {
  EvolveIdleMemory,
  EvolveReport,
  Memory,
  RecallStageStat,
} from "@/types/api";

const EMPTY_REPORT: EvolveReport = {
  search_quality: { windows: {}, daily_trend: [], top_zero_hits: [] },
  feedback: {
    type_distribution: { useful: 0, useless: 0, correction: 0 },
    most_corrected: [],
  },
  heat: {
    score_distribution: {
      "lt_0.5": 0,
      "0.5_0.9": 0,
      "0.9_1.1": 0,
      "gt_1.1": 0,
    },
    high_frequency: [],
    stale: [],
    boost_adjustments: [],
  },
  operations: { windows: {} },
  recall: { stages: [], recent: [] },
};

const fmtCount = (n: number) => n.toLocaleString();
const fmtPct = (fraction: number) => `${(fraction * 100).toFixed(1)}%`;
const fmtMs = (ms: number) => `${Math.round(ms)} ms`;
const fmtScore = (s: number) => s.toFixed(2);
const fmtDay = (iso: string) =>
  format(new Date(iso), "MMM d", { locale: zhCN });
const fmtDateTime = (iso: string | null | undefined) =>
  iso ? format(new Date(iso), "MMM d, yyyy", { locale: zhCN }) : "--";

function MemoryViewer({ memoryId }: { memoryId: string }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setContent("");
    setNotFound(false);
    api
      .get<Memory>(MEMORY_ENDPOINTS.BY_ID(memoryId))
      .then((res) => {
        if (cancelled) return;
        if (res.data === null) {
          setNotFound(true);
        } else {
          setContent(res.data.memory);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, "加载记忆内容失败"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, memoryId]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="xs">
          查看
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[min(36rem,92vw)] max-h-[min(70vh,40rem)] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>记忆内容</DialogTitle>
        </DialogHeader>
        <div className="font-mono text-xs break-all text-onSurface-default-tertiary">
          {memoryId}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto pr-1">
          {loading ? (
            <p className="text-sm text-onSurface-default-secondary">
              加载中...
            </p>
          ) : error ? (
            <p className="text-sm text-onSurface-danger-primary">{error}</p>
          ) : notFound ? (
            <p className="text-sm text-onSurface-default-secondary">
              该记忆内容不存在（可能已被清理）
            </p>
          ) : (
            <p className="text-sm whitespace-pre-wrap break-words text-onSurface-default-primary">
              {content}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

const memoryIdCell = (value: string) => (
  <span className="flex items-center gap-1 font-mono text-xs">
    <span className="min-w-0 flex-1 truncate">{value}</span>
    <MemoryViewer memoryId={value} />
  </span>
);

function StaleActions({
  memoryId,
  onDone,
}: {
  memoryId: string;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState<null | "delete" | "retain">(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState("");

  const run = async (
    action: "delete" | "retain",
    fn: () => Promise<unknown>,
  ) => {
    setBusy(action);
    setError("");
    try {
      await fn();
      setConfirmOpen(false);
      toast({
        title: action === "delete" ? "记忆已清理" : "记忆已保留",
        variant: "success",
      });
      onDone();
    } catch (err) {
      setError(
        getErrorMessage(err, action === "delete" ? "清理失败" : "保留失败"),
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="outline"
        size="xs"
        onClick={() => setConfirmOpen(true)}
        disabled={busy !== null}
      >
        清理
      </Button>
      <Button
        variant="outline"
        size="xs"
        onClick={() =>
          void run("retain", () => api.post(EVOLVE_ENDPOINTS.RETAIN(memoryId)))
        }
        disabled={busy !== null}
      >
        保留
      </Button>
      {error && (
        <span className="text-[10px] text-onSurface-danger-primary">
          {error}
        </span>
      )}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>确认清理</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-onSurface-default-secondary">
            删除记忆后不可恢复，热度数据会一并清理。确认清理这条记忆？
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              disabled={busy === "delete"}
              onClick={() =>
                void run("delete", () =>
                  api.delete(MEMORY_ENDPOINTS.BY_ID(memoryId)),
                )
              }
            >
              {busy === "delete" ? "清理中..." : "确认清理"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Panel({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="border-memBorder-primary">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">{title}</CardTitle>
        {description && (
          <p className="text-xs text-onSurface-default-tertiary">
            {description}
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-6 p-4">{children}</CardContent>
    </Card>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-onSurface-default-secondary">
        {title}
      </h4>
      {children}
    </div>
  );
}

function NoData({ text = "暂无数据" }: { text?: string }) {
  return (
    <p className="py-4 text-center text-xs text-onSurface-default-tertiary">
      {text}
    </p>
  );
}

function DistributionBars({
  items,
}: {
  items: { label: string; value: number; barClass: string }[];
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-onSurface-default-secondary">
              {item.label}
            </span>
            <span className="text-onSurface-default-primary">
              {fmtCount(item.value)}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-default-secondary">
            <div
              className={`h-full rounded-full ${item.barClass}`}
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ScoreHistogram({
  buckets,
}: {
  buckets: { label: string; value: number }[];
}) {
  const max = Math.max(...buckets.map((b) => b.value), 1);
  return (
    <div>
      <div className="flex h-[100px] items-end gap-3">
        {buckets.map((b) => (
          <div key={b.label} className="relative flex h-full flex-1 items-end">
            <span className="absolute -top-1 left-0 right-0 text-center text-[10px] text-onSurface-default-secondary">
              {b.value}
            </span>
            <div
              className="w-full rounded-t bg-sentry-violet"
              style={{ height: `${(b.value / max) * 100}%` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-3">
        {buckets.map((b) => (
          <div
            key={b.label}
            className="flex-1 text-center text-xs text-onSurface-default-tertiary"
          >
            {b.label}
          </div>
        ))}
      </div>
    </div>
  );
}

const RECALL_STAGES: { key: string; name: string }[] = [
  { key: "candidates", name: "候选池" },
  { key: "threshold", name: "阈值过滤" },
  { key: "decay", name: "时间衰减" },
  { key: "graph", name: "图召回" },
  { key: "temporal", name: "时间声部" },
  { key: "rerank", name: "重排序" },
  { key: "final", name: "最终" },
];

function RecallFunnel({ stages }: { stages: RecallStageStat[] }) {
  const byStage = new Map(stages.map((s) => [s.stage, s]));
  const rows = RECALL_STAGES.map(({ key, name }) => ({
    name,
    avg_count: byStage.get(key)?.avg_count ?? 0,
    avg_latency_ms: byStage.get(key)?.avg_latency_ms ?? 0,
  }));
  const maxCount = Math.max(...rows.map((r) => r.avg_count), 1);
  const maxLatency = Math.max(...rows.map((r) => r.avg_latency_ms), 1);
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div
            key={r.name}
            className="grid grid-cols-[56px_1fr_64px] items-center gap-2 text-xs"
          >
            <span className="text-onSurface-default-secondary">{r.name}</span>
            <div className="flex h-5 items-center justify-center">
              <div
                className="h-full rounded bg-sentry-violet"
                style={{ width: `${(r.avg_count / maxCount) * 100}%` }}
              />
            </div>
            <span className="text-right text-onSurface-default-primary">
              {fmtCount(Math.round(r.avg_count))}
            </span>
          </div>
        ))}
      </div>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.name}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-onSurface-default-secondary">{r.name}</span>
              <span className="text-onSurface-default-primary">
                {fmtMs(r.avg_latency_ms)}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-default-secondary">
              <div
                className="h-full rounded-full bg-sentry-lime"
                style={{ width: `${(r.avg_latency_ms / maxLatency) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[var(--sentry-hairline)] bg-[var(--sentry-night)]/95 px-3 py-2 shadow-lg">
      <div className="mb-1.5 text-xs text-[var(--sentry-ink-muted)]">{fmtDay(String(label))}</div>
      <div className="space-y-1">
        {payload.map((entry) => (
          <div key={entry.dataKey as string} className="flex items-center gap-2 text-[13px]">
            <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: entry.color }} />
            <span className="text-[var(--sentry-ink-muted)]">{entry.name}</span>
            <span className="ml-auto font-medium text-[var(--sentry-ink)]">
              {fmtCount(Number(entry.value))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const {
    data: report = EMPTY_REPORT,
    isLoading,
    error,
    refetch,
  } = useApiQuery<EvolveReport>(
    async () => {
      const res = await api.get<EvolveReport>(EVOLVE_ENDPOINTS.REPORT, {
        params: { days: 30 },
      });
      setLastUpdated(new Date().toISOString());
      return res.data;
    },
    { errorToast: "加载分析数据失败", initialData: EMPTY_REPORT },
  );

  const { search_quality, feedback, heat, operations, recall } = report;

  const searchRows = Object.entries(search_quality.windows).map(
    ([days, w]) => ({
      window: `${days} 天`,
      total: w.total_queries ?? 0,
      zeroRate: w.zero_hit_rate ?? 0,
      avgScore: w.avg_score ?? 0,
      latency: w.avg_latency_ms ?? 0,
    }),
  );

  const opRows = Object.entries(operations.windows).map(([days, w]) => ({
    window: `${days} 天`,
    total: w.total_requests ?? 0,
    latency: w.avg_latency_ms ?? 0,
    successRate: w.success_rate ?? 0,
  }));

  const windowColumns = [
    { key: "window" as const, label: "时间窗口", width: 90 },
    {
      key: "total" as const,
      label: "请求数",
      width: 100,
      render: (v: number) => fmtCount(v),
    },
    {
      key: "latency" as const,
      label: "平均延迟",
      width: 110,
      render: (v: number) => fmtMs(v),
    },
    {
      key: "successRate" as const,
      label: "成功率",
      width: 110,
      render: (v: number) => fmtPct(v),
    },
  ];

  const searchColumns = [
    { key: "window" as const, label: "时间窗口", width: 90 },
    {
      key: "total" as const,
      label: "总查询数",
      width: 100,
      render: (v: number) => fmtCount(v),
    },
    {
      key: "zeroRate" as const,
      label: "零命中率",
      width: 110,
      render: (v: number) => fmtPct(v),
    },
    {
      key: "avgScore" as const,
      label: "平均分",
      width: 90,
      render: (v: number) => fmtScore(v),
    },
    {
      key: "latency" as const,
      label: "平均延迟",
      width: 110,
      render: (v: number) => fmtMs(v),
    },
  ];

  const zeroHitColumns = [
    {
      key: "query" as const,
      label: "查询",
      width: 300,
      render: (v: string) => <span className="line-clamp-1">{v}</span>,
    },
    { key: "count" as const, label: "命中数", width: 100 },
  ];

  const correctedColumns = [
    {
      key: "memory_id" as const,
      label: "记忆 ID",
      width: 300,
      render: memoryIdCell,
    },
    { key: "count" as const, label: "纠正次数", width: 100 },
  ];

  const hotColumns = [
    {
      key: "memory_id" as const,
      label: "记忆 ID",
      width: 300,
      render: memoryIdCell,
    },
    { key: "access_count" as const, label: "访问次数", width: 100 },
    {
      key: "salience_score" as const,
      label: "显著性",
      width: 100,
      render: (v: number) => fmtScore(v),
    },
  ];

  const idleColumns = [
    {
      key: "memory_id" as const,
      label: "记忆 ID",
      width: 220,
      render: memoryIdCell,
    },
    { key: "access_count" as const, label: "访问次数", width: 80 },
    {
      key: "last_access_at" as const,
      label: "最后访问",
      width: 120,
      render: (v: string | null) => fmtDateTime(v),
    },
    {
      key: "memory_id" as const,
      label: "操作",
      width: 140,
      render: (_: string, row: EvolveIdleMemory) => (
        <StaleActions memoryId={row.memory_id} onDone={() => void refetch()} />
      ),
    },
  ];

  const boostColumns = [
    {
      key: "memory_id" as const,
      label: "记忆 ID",
      width: 300,
      render: memoryIdCell,
    },
    {
      key: "delta" as const,
      label: "增量",
      width: 100,
      render: (v: number) => (
        <span
          className={
            v >= 0
              ? "text-onSurface-positive-primary"
              : "text-onSurface-danger-primary"
          }
        >
          {v >= 0 ? "+" : ""}
          {v.toFixed(3)}
        </span>
      ),
    },
    {
      key: "created_at" as const,
      label: "时间",
      width: 140,
      render: (v: string | null) => fmtDateTime(v),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold font-fustat">分析</h1>
          <p className="text-sm text-onSurface-default-secondary">
            了解记忆库中的搜索质量、反馈与热度健康。
          </p>
          {lastUpdated && (
            <p className="text-xs text-onSurface-default-tertiary">
              上次更新于{" "}
              {formatDistanceToNow(new Date(lastUpdated), {
                addSuffix: true,
                locale: zhCN,
              })}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          onClick={() => void refetch()}
          disabled={isLoading}
        >
          <RefreshCw className="size-4 mr-2" />
          刷新
        </Button>
      </div>

      {error && (
        <Card className="border-memBorder-primary">
          <CardContent className="p-4 text-sm text-onSurface-danger-primary">
            {error}
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <div className="space-y-4">
          <TableSkeleton rows={3} columns={5} />
          <TableSkeleton rows={3} columns={4} />
        </div>
      ) : (
        <>
          <Panel
            title="搜索质量"
            description="过去 7/30 天的查询量、零命中率、平均分与延迟。"
          >
            <Section title="时间窗口">
              {searchRows.length > 0 ? (
                <DataTable
                  data={searchRows}
                  columns={searchColumns}
                  getRowKey={(row) => row.window}
                />
              ) : (
                <NoData />
              )}
            </Section>
            <Section title="每日趋势（7 天）">
              {search_quality.daily_trend.length > 0 ? (
                <div className="h-[200px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={search_quality.daily_trend}
                      margin={{ top: 5, right: 10, bottom: 0, left: -15 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="var(--mem-border-secondary)"
                      />
                      <XAxis
                        dataKey="date"
                        tickFormatter={fmtDay}
                        tick={{ fontSize: 11 }}
                        stroke="var(--mem-neutral-400)"
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11 }}
                        stroke="var(--mem-neutral-400)"
                        width={40}
                      />
                      <Tooltip content={<TrendTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="queries"
                        name="查询量"
                        stroke="#c2ef4e"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="zero_hits"
                        name="零命中"
                        stroke="#fa7faa"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <NoData />
              )}
            </Section>
            <Section title="零命中热门查询">
              {search_quality.top_zero_hits.length > 0 ? (
                <DataTable
                  data={search_quality.top_zero_hits}
                  columns={zeroHitColumns}
                  getRowKey={(row) => row.query}
                />
              ) : (
                <NoData />
              )}
            </Section>
          </Panel>

          <Panel
            title="反馈回路"
            description="用户如何评价与纠正检索到的记忆。"
          >
            <Section title="反馈分布">
              <DistributionBars
                items={[
                  {
                    label: "有用",
                    value: feedback.type_distribution.useful,
                    barClass: "bg-sentry-success",
                  },
                  {
                    label: "无用",
                    value: feedback.type_distribution.useless,
                    barClass: "bg-sentry-danger",
                  },
                  {
                    label: "纠正",
                    value: feedback.type_distribution.correction,
                    barClass: "bg-sentry-warning",
                  },
                ]}
              />
            </Section>
            <Section title="纠正最多的记忆">
              {feedback.most_corrected.length > 0 ? (
                <DataTable
                  data={feedback.most_corrected}
                  columns={correctedColumns}
                  getRowKey={(row) => row.memory_id}
                />
              ) : (
                <NoData />
              )}
            </Section>
          </Panel>

          <Panel
            title="热度健康"
            description="显著性评分分布，以及热门、闲置与提升记忆。"
          >
            <Section title="评分分布">
              <ScoreHistogram
                buckets={[
                  { label: "< 0.5", value: heat.score_distribution["lt_0.5"] },
                  {
                    label: "0.5 – 0.9",
                    value: heat.score_distribution["0.5_0.9"],
                  },
                  {
                    label: "0.9 – 1.1",
                    value: heat.score_distribution["0.9_1.1"],
                  },
                  { label: "> 1.1", value: heat.score_distribution["gt_1.1"] },
                ]}
              />
            </Section>
            <Section title="高频记忆">
              {heat.high_frequency.length > 0 ? (
                <DataTable
                  data={heat.high_frequency}
                  columns={hotColumns}
                  getRowKey={(row) => row.memory_id}
                />
              ) : (
                <NoData />
              )}
            </Section>
            <Section title="闲置记忆（14 天以上未召回）">
              {heat.stale.length > 0 ? (
                <DataTable
                  data={heat.stale}
                  columns={idleColumns}
                  getRowKey={(row) => row.memory_id}
                />
              ) : (
                <NoData />
              )}
            </Section>
            <Section title="提升记录">
              {heat.boost_adjustments.length > 0 ? (
                <DataTable
                  data={heat.boost_adjustments}
                  columns={boostColumns}
                  getRowKey={(row) => row.memory_id}
                />
              ) : (
                <NoData />
              )}
            </Section>
          </Panel>

          <Panel
            title="操作"
            description="过去 7/30 天的请求量、延迟与成功率。"
          >
            <Section title="时间窗口">
              {opRows.length > 0 ? (
                <DataTable
                  data={opRows}
                  columns={windowColumns}
                  getRowKey={(row) => row.window}
                />
              ) : (
                <NoData />
              )}
            </Section>
          </Panel>

          <Panel
            title="召回漏斗"
            description="近 7 天检索各阶段平均命中数与耗时，观察召回逐级收窄。"
          >
            {recall.stages.length > 0 ? (
              <RecallFunnel stages={recall.stages} />
            ) : (
              <NoData text="暂无召回数据" />
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
