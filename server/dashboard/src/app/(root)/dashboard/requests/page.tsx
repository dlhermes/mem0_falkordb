"use client";

import { useMemo, useState } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { DataTable } from "@/components/shared/data-table";
import { TableSkeleton } from "@/components/shared/table-skeleton";
import { EmptyState } from "@/components/self-hosted/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import CopyButton from "@/components/misc/copy-button";
import { api } from "@/utils/api";
import { REQUEST_ENDPOINTS } from "@/utils/api-endpoints";
import { useApiQuery } from "@/hooks/use-api-query";
import { ApiRequestLog, ApiRequestLogList } from "@/types/api";

type RequestLog = {
  id: string;
  createdAt: string;
  method: string;
  path: string;
  statusCode: number;
  latencyMs: number;
  authType: string;
};

const REQUEST_LOG_LIMIT = 200;
const PAGE_SIZE = 20;

const STATUS_FILTERS = [
  { value: "all", label: "全部状态" },
  { value: "2", label: "2xx" },
  { value: "3", label: "3xx" },
  { value: "4", label: "4xx" },
  { value: "5", label: "5xx" },
] as const;

const TIME_FILTERS = [
  { value: "all", label: "全部时间" },
  { value: "24", label: "近 24 小时" },
  { value: "168", label: "近 7 天" },
  { value: "720", label: "近 30 天" },
] as const;

const getStatusBadge = (
  statusCode: number,
): "danger" | "warning" | "success" => {
  if (statusCode >= 500) {
    return "danger";
  }

  if (statusCode >= 400) {
    return "warning";
  }

  return "success";
};

const getMethodBadge = (
  method: string,
): "lime" | "violet" | "pink" | "outline" => {
  switch (method.toUpperCase()) {
    case "POST":
      return "lime";
    case "PUT":
    case "PATCH":
      return "violet";
    case "DELETE":
      return "pink";
    default:
      return "outline";
  }
};

const getAuthLabel = (authType: string) => {
  switch (authType.toLowerCase()) {
    case "bearer":
      return "JWT";
    case "api_key":
      return "API 密钥";
    case "admin_api_key":
      return "管理员密钥";
    case "disabled":
      return "已禁用";
    default:
      return "--";
  }
};

const normalizeLog = (entry: ApiRequestLog): RequestLog => {
  return {
    id: entry.id,
    createdAt: entry.created_at,
    method: entry.method,
    path: entry.path,
    statusCode: entry.status_code,
    latencyMs: entry.latency_ms,
    authType: entry.auth_type,
  };
};

export default function RequestsPage() {
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [methodFilter, setMethodFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState("all");
  const [selectedLog, setSelectedLog] = useState<RequestLog | null>(null);

  const { data, isLoading, error, refetch } = useApiQuery<ApiRequestLogList>(
    async () => {
      const res = await api.get<ApiRequestLogList>(REQUEST_ENDPOINTS.BASE, {
        params: { limit: REQUEST_LOG_LIMIT },
      });
      setLastUpdated(new Date().toISOString());
      return res.data ?? { items: [], total: 0 };
    },
    { errorToast: "加载请求日志失败", initialData: { items: [], total: 0 } },
  );

  const logs = useMemo(() => (data?.items ?? []).map(normalizeLog), [data]);
  const totalRequests = data?.total ?? 0;

  const methodOptions = useMemo(() => {
    const methods = new Set(logs.map((log) => log.method.toUpperCase()));
    return Array.from(methods).sort();
  }, [logs]);

  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      if (methodFilter !== "all" && log.method.toUpperCase() !== methodFilter) {
        return false;
      }
      if (
        statusFilter !== "all" &&
        Math.floor(log.statusCode / 100) !== Number(statusFilter)
      ) {
        return false;
      }
      if (timeFilter !== "all") {
        const cutoff = Date.now() - Number(timeFilter) * 60 * 60 * 1000;
        if (new Date(log.createdAt).getTime() < cutoff) return false;
      }
      return true;
    });
  }, [logs, methodFilter, statusFilter, timeFilter]);

  const windowCount = filteredLogs.length;
  const successfulRequests = filteredLogs.filter(
    (log) => log.statusCode < 400,
  ).length;
  const successRate =
    windowCount > 0 ? Math.round((successfulRequests / windowCount) * 100) : 0;
  const averageLatency =
    windowCount > 0
      ? Math.round(
          filteredLogs.reduce((sum, log) => sum + log.latencyMs, 0) /
            windowCount,
        )
      : 0;

  const resetPage = () => setPage(0);

  const columns = [
    {
      key: "createdAt" as keyof RequestLog,
      label: "时间",
      width: 140,
      render: (value: string) => (
        <span title={format(new Date(value), "PPpp")}>
          {formatDistanceToNow(new Date(value), { addSuffix: true })}
        </span>
      ),
    },
    {
      key: "method" as keyof RequestLog,
      label: "方法",
      width: 96,
      render: (value: string) => (
        <Badge variant={getMethodBadge(value)}>{value.toUpperCase()}</Badge>
      ),
    },
    {
      key: "path" as keyof RequestLog,
      label: "路径",
      width: 360,
      render: (value: string) => (
        <span className="font-mono text-xs break-all text-onSurface-default-primary">
          {value}
        </span>
      ),
    },
    {
      key: "statusCode" as keyof RequestLog,
      label: "状态",
      width: 120,
      render: (value: number) => (
        <Badge variant={getStatusBadge(value)}>{value}</Badge>
      ),
    },
    {
      key: "latencyMs" as keyof RequestLog,
      label: "延迟",
      width: 100,
      render: (value: number) => <span>{value} ms</span>,
    },
    {
      key: "authType" as keyof RequestLog,
      label: "认证",
      width: 120,
      render: (value: string) => getAuthLabel(value),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold font-fustat">请求</h1>
          <p className="text-sm text-onSurface-default-secondary">
            来自你自托管实例的最近请求日志。
          </p>
          {lastUpdated && (
            <p className="text-xs text-onSurface-default-tertiary">
              上次更新于{" "}
              {formatDistanceToNow(new Date(lastUpdated), { addSuffix: true })}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          onClick={() => {
            setPage(0);
            void refetch();
          }}
          disabled={isLoading}
        >
          <RefreshCw className="size-4 mr-2" />
          刷新
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { label: "总请求数", value: totalRequests },
          {
            label: "成功率",
            value: windowCount > 0 ? `${successRate}%` : "--",
          },
          {
            label: "平均延迟",
            value: windowCount > 0 ? `${averageLatency} ms` : "--",
          },
        ].map((card) => (
          <Card
            key={card.label}
            className="relative border-sentry-hairline overflow-hidden"
          >
            <div className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-sentry-lime via-sentry-violet to-sentry-pink" />
            <CardContent className="p-4 pt-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-onSurface-default-tertiary">
                {card.label}
              </p>
              <p className="mt-1.5 text-[26px] font-bold tabular-nums leading-none text-onSurface-default-primary">
                {card.value}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {error && (
        <Card className="border-memBorder-primary">
          <CardContent className="p-4 text-sm text-onSurface-danger-primary">
            {error}
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <TableSkeleton rows={6} columns={6} />
      ) : logs.length === 0 ? (
        <EmptyState
          title="还没有请求日志"
          description="当你的实例开始收到请求时，日志会显示在这里。"
          image="requests"
        />
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <Label className="text-[11px] font-semibold uppercase tracking-[0.06em] text-onSurface-default-tertiary">
                方法
              </Label>
              <Select
                value={methodFilter}
                onValueChange={(v) => {
                  setMethodFilter(v);
                  resetPage();
                }}
              >
                <SelectTrigger variant="dropdown" className="w-40">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  {methodOptions.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] font-semibold uppercase tracking-[0.06em] text-onSurface-default-tertiary">
                状态
              </Label>
              <Select
                value={statusFilter}
                onValueChange={(v) => {
                  setStatusFilter(v);
                  resetPage();
                }}
              >
                <SelectTrigger variant="dropdown" className="w-40">
                  <SelectValue placeholder="全部状态" />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_FILTERS.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] font-semibold uppercase tracking-[0.06em] text-onSurface-default-tertiary">
                时间
              </Label>
              <Select
                value={timeFilter}
                onValueChange={(v) => {
                  setTimeFilter(v);
                  resetPage();
                }}
              >
                <SelectTrigger variant="dropdown" className="w-40">
                  <SelectValue placeholder="全部时间" />
                </SelectTrigger>
                <SelectContent>
                  {TIME_FILTERS.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Card className="border-memBorder-primary overflow-hidden">
            <DataTable
              data={filteredLogs.slice(
                page * PAGE_SIZE,
                (page + 1) * PAGE_SIZE,
              )}
              columns={columns}
              getRowKey={(row) => row.id}
              onRowClick={(row) => setSelectedLog(row)}
            />
          </Card>
          <p className="mt-2 text-xs text-onSurface-default-tertiary">
            仅显示最近 {REQUEST_LOG_LIMIT} 条请求日志（完整记录共{" "}
            {totalRequests} 条）。
          </p>
          {filteredLogs.length > PAGE_SIZE && (
            <div className="flex items-center justify-between text-sm text-onSurface-default-tertiary">
              <span>
                第 {page * PAGE_SIZE + 1}–
                {Math.min((page + 1) * PAGE_SIZE, filteredLogs.length)} 条，共{" "}
                {filteredLogs.length} 条
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={(page + 1) * PAGE_SIZE >= filteredLogs.length}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      <Sheet
        open={!!selectedLog}
        onOpenChange={(open) => {
          if (!open) setSelectedLog(null);
        }}
      >
        <SheetContent className="sm:max-w-md overflow-y-auto">
          <SheetHeader>
            <SheetTitle>请求详情</SheetTitle>
            <SheetDescription className="sr-only">
              查看请求日志详情
            </SheetDescription>
          </SheetHeader>
          {selectedLog && (
            <div className="mt-6 space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant={getMethodBadge(selectedLog.method)}>
                  {selectedLog.method.toUpperCase()}
                </Badge>
                <Badge variant={getStatusBadge(selectedLog.statusCode)}>
                  {selectedLog.statusCode}
                </Badge>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-onSurface-default-tertiary">
                  路径
                </Label>
                <div className="flex items-start gap-2">
                  <p className="flex-1 text-xs font-mono break-all text-onSurface-default-primary">
                    {selectedLog.path}
                  </p>
                  <CopyButton textToCopy={selectedLog.path} label="复制路径" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label className="text-xs text-onSurface-default-tertiary">
                    延迟
                  </Label>
                  <p className="text-sm">{selectedLog.latencyMs} ms</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-onSurface-default-tertiary">
                    认证方式
                  </Label>
                  <p className="text-sm">
                    {getAuthLabel(selectedLog.authType)}
                  </p>
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-onSurface-default-tertiary">
                  创建时间
                </Label>
                <p className="text-sm">
                  {format(new Date(selectedLog.createdAt), "PPpp")}
                </p>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
