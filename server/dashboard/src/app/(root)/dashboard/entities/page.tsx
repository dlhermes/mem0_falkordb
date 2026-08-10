"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/shared/data-table";
import { TableSkeleton } from "@/components/shared/table-skeleton";
import { EmptyState } from "@/components/self-hosted/empty-state";
import DeleteConfirmationModal from "@/components/ui/delete-confirmation-modal";
import { toast } from "@/components/ui/use-toast";
import { api } from "@/utils/api";
import { ENTITY_ENDPOINTS } from "@/utils/api-endpoints";
import { getErrorMessage } from "@/lib/error-message";
import { useApiQuery } from "@/hooks/use-api-query";
import { Entity } from "@/types/api";

export default function EntitiesPage() {
  const [entityToDelete, setEntityToDelete] = useState<Entity | null>(null);

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
          onClick={() => setEntityToDelete(row)}
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

      {isLoading ? (
        <TableSkeleton rows={5} columns={5} />
      ) : entities.length === 0 ? (
        <EmptyState
          title="还没有实体"
          description="当记忆以 user_id、agent_id 或 run_id 存储后，实体才会出现。"
        />
      ) : (
        <Card className="border-memBorder-primary overflow-hidden">
          <DataTable
            data={entities}
            columns={columns}
            getRowKey={(row) => `${row.type}:${row.id}`}
          />
        </Card>
      )}

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
