"use client";

import { useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import DeleteConfirmationModal from "@/components/ui/delete-confirmation-modal";
import CopyButton from "@/components/misc/copy-button";
import { toast } from "@/components/ui/use-toast";
import { api } from "@/utils/api";
import { ENTITY_ENDPOINTS } from "@/utils/api-endpoints";
import { getErrorMessage } from "@/lib/error-message";
import { useApiQuery } from "@/hooks/use-api-query";
import { Entity, EntityType } from "@/types/api";

const TYPE_FILTERS = [
  { value: "all", label: "全部" },
  { value: "user", label: "用户" },
  { value: "agent", label: "代理" },
  { value: "run", label: "运行" },
] as const;

const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  user: "用户",
  agent: "代理",
  run: "运行",
};

const getEntityBadge = (type: EntityType): "violet" | "lime" | "pink" => {
  switch (type) {
    case "user":
      return "violet";
    case "agent":
      return "lime";
    case "run":
      return "pink";
  }
};

export default function EntitiesPage() {
  const [entityToDelete, setEntityToDelete] = useState<Entity | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const {
    data: entities = [],
    isLoading,
    refetch,
  } = useApiQuery<Entity[]>(
    async () => {
      const res = await api.get<Entity[]>(ENTITY_ENDPOINTS.BASE);
      return res.data ?? [];
    },
    { errorToast: "加载实体失败", initialData: [] },
  );

  const typeCounts = useMemo(() => {
    const counts: Record<EntityType, number> = { user: 0, agent: 0, run: 0 };
    for (const entity of entities) {
      counts[entity.type] = (counts[entity.type] ?? 0) + 1;
    }
    return counts;
  }, [entities]);

  const filteredEntities = useMemo(() => {
    if (typeFilter === "all") return entities;
    return entities.filter((entity) => entity.type === typeFilter);
  }, [entities, typeFilter]);

  const handleDelete = async () => {
    if (!entityToDelete) return;
    try {
      await api.delete(
        ENTITY_ENDPOINTS.BY_ID(entityToDelete.type, entityToDelete.id),
      );
      toast({ title: "实体已删除", variant: "success" });
      setEntityToDelete(null);
      void refetch();
    } catch (error) {
      toast({
        title: "删除实体失败",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    }
  };

  const columns = [
    {
      key: "type" as keyof Entity,
      label: "类型",
      width: 100,
      render: (value: Entity["type"]) => (
        <Badge variant="outline" className="capitalize">
          {value}
        </Badge>
      ),
    },
    {
      key: "id" as keyof Entity,
      label: "ID",
      width: 280,
      render: (value: string) => (
        <span className="font-mono text-sm truncate">{value}</span>
      ),
    },
    {
      key: "total_memories" as keyof Entity,
      label: "记忆数",
      width: 100,
      align: "right" as const,
    },
    {
      key: "updated_at" as keyof Entity,
      label: "最后活跃",
      width: 140,
      render: (value: string | null) =>
        value ? format(new Date(value), "MMM d, yyyy") : "--",
    },
    {
      key: "id" as keyof Entity,
      label: "",
      width: 40,
      render: (_: string, row: Entity) => (
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.stopPropagation();
            setEntityToDelete(row);
          }}
          className="size-7"
        >
          <Trash2 className="size-3.5 text-onSurface-danger-primary" />
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold font-fustat">实体</h1>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {[
          { label: "实体总数", value: entities.length },
          { label: "用户", value: typeCounts.user },
          { label: "代理", value: typeCounts.agent },
          { label: "运行", value: typeCounts.run },
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

      {isLoading ? (
        <TableSkeleton rows={5} columns={5} />
      ) : entities.length === 0 ? (
        <EmptyState
          title="还没有实体"
          description="当记忆以 user_id、agent_id 或 run_id 存储后，实体才会出现。"
        />
      ) : (
        <>
          <div className="flex items-end gap-4">
            <div className="space-y-1.5">
              <Label className="text-[11px] font-semibold uppercase tracking-[0.06em] text-onSurface-default-tertiary">
                类型
              </Label>
              <Select
                value={typeFilter}
                onValueChange={(v) => setTypeFilter(v)}
              >
                <SelectTrigger variant="dropdown" className="w-40">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  {TYPE_FILTERS.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {filteredEntities.length === 0 ? (
            <EmptyState
              title="没有匹配的实体"
              description="尝试切换类型筛选以查看更多实体。"
            />
          ) : (
            <Card className="border-memBorder-primary overflow-hidden">
              <DataTable
                data={filteredEntities}
                columns={columns}
                getRowKey={(row) => `${row.type}:${row.id}`}
                onRowClick={(row) => setSelectedEntity(row)}
              />
            </Card>
          )}
        </>
      )}

      <Sheet
        open={!!selectedEntity}
        onOpenChange={(open) => {
          if (!open) setSelectedEntity(null);
        }}
      >
        <SheetContent className="sm:max-w-md overflow-y-auto">
          <SheetHeader>
            <SheetTitle>实体详情</SheetTitle>
            <SheetDescription className="sr-only">
              查看实体信息
            </SheetDescription>
          </SheetHeader>
          {selectedEntity && (
            <div className="mt-6 space-y-4">
              <Badge variant={getEntityBadge(selectedEntity.type)}>
                {ENTITY_TYPE_LABELS[selectedEntity.type]}
              </Badge>
              <div className="space-y-1">
                <Label className="text-xs text-onSurface-default-tertiary">
                  ID
                </Label>
                <div className="flex items-start gap-2">
                  <p className="flex-1 text-xs font-mono break-all text-onSurface-default-primary">
                    {selectedEntity.id}
                  </p>
                  <CopyButton textToCopy={selectedEntity.id} label="复制 ID" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label className="text-xs text-onSurface-default-tertiary">
                    关联记忆数
                  </Label>
                  <p className="text-sm tabular-nums">
                    {selectedEntity.total_memories}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label className="text-xs text-onSurface-default-tertiary">
                    创建时间
                  </Label>
                  <p className="text-sm">
                    {selectedEntity.created_at
                      ? format(new Date(selectedEntity.created_at), "PPpp")
                      : "--"}
                  </p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-onSurface-default-tertiary">
                    更新时间
                  </Label>
                  <p className="text-sm">
                    {selectedEntity.updated_at
                      ? format(new Date(selectedEntity.updated_at), "PPpp")
                      : "--"}
                  </p>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      <DeleteConfirmationModal
        isOpen={!!entityToDelete}
        onClose={() => setEntityToDelete(null)}
        onConfirm={handleDelete}
        title="删除实体"
        description="与该实体关联的所有记忆都将被永久删除。此操作无法撤销。"
        itemName={entityToDelete?.id ?? ""}
        confirmButtonText="删除"
      />
    </div>
  );
}
