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
import type { EvolveReport, Memory } from "@/types/api";

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

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setContent("");
    api
      .get<Memory>(MEMORY_ENDPOINTS.BY_ID(memoryId))
      .then((res) => {
        if (!cancelled) setContent(res.data.memory);
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
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>记忆内容</DialogTitle>
        </DialogHeader>
        <div className="font-mono text-xs break-all text-onSurface-default-tertiary">
          {memoryId}
        </div>
        {loading ? (
          <p className="text-sm text-onSurface-default-secondary">加载中...</p>
        ) : error ? (
          <p className="text-sm text-onSurface-danger-primary">{error}</p>
        ) : (
          <p className="text-sm whitespace-pre-wrap text-onSurface-default-primary">
            {content}
          </p>
        )}
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

function NoData() {
  return (
    <p className="py-4 text-center text-xs text-onSurface-default-tertiary">
      暂无数据
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
              className="w-full rounded-t bg-surface-default-brand"
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

  const { search_quality, feedback, heat, operations } = report;

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
      width: 300,
      render: memoryIdCell,
    },
    { key: "access_count" as const, label: "访问次数", width: 100 },
    {
      key: "last_access_at" as const,
      label: "最后访问",
      width: 140,
      render: (v: string | null) => fmtDateTime(v),
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
                      <Tooltip
                        labelFormatter={(label) =>
                          format(new Date(String(label)), "MMM d, yyyy")
                        }
                        contentStyle={{ fontSize: 12 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="queries"
                        name="查询量"
                        stroke="#8f74e0"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="zero_hits"
                        name="零命中"
                        stroke="#f43f5e"
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
                    barClass: "bg-emerald-500",
                  },
                  {
                    label: "无用",
                    value: feedback.type_distribution.useless,
                    barClass: "bg-rose-500",
                  },
                  {
                    label: "纠正",
                    value: feedback.type_distribution.correction,
                    barClass: "bg-amber-500",
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
        </>
      )}
    </div>
  );
}
