"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Moon, Sun, Trash2 } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "@/components/ui/use-toast";
import { useAuth } from "@/hooks/use-auth";
import { getErrorMessage } from "@/lib/error-message";
import { cn } from "@/lib/utils";
import { api } from "@/utils/api";
import {
  AUTH_ENDPOINTS,
  MEMORY_ENDPOINTS,
  SEARCH_KEYWORDS_ENDPOINTS,
} from "@/utils/api-endpoints";

type ProviderBlock = {
  provider?: string;
  config?: { model?: string };
};

type InstanceConfig = {
  llm?: ProviderBlock;
  embedder?: ProviderBlock;
  reranker?: ProviderBlock | null;
  vector_store?: { provider?: string };
  graph_store?: {
    provider?: string;
    llm?: ProviderBlock;
    embedder?: ProviderBlock;
  };
};

type DepthKeyword = {
  id: number;
  keyword: string;
  category: "minimal" | "standard" | "full";
  match_type?: "exact" | "contains";
  lang?: string;
};

type SearchDepth = DepthKeyword["category"];

const DEPTH_META: Record<SearchDepth, { label: string; dot: string }> = {
  minimal: { label: "精简", dot: "bg-sentry-lime" },
  standard: { label: "标准", dot: "bg-sentry-violet" },
  full: { label: "完整", dot: "bg-sentry-pink" },
};

const DEPTH_ORDER: SearchDepth[] = ["minimal", "standard", "full"];

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-memBorder-primary/60 py-2 last:border-b-0">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-onSurface-default-tertiary">
        {label}
      </span>
      <span className="text-sm text-onSurface-default-primary">{value}</span>
    </div>
  );
}

function providerModel(block?: ProviderBlock | null): string | null {
  const provider = block?.provider;
  const model = block?.config?.model;
  if (!provider) return null;
  return model ? `${provider} · ${model}` : provider;
}

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const { setTheme, resolvedTheme } = useTheme();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  const [instanceConfig, setInstanceConfig] = useState<InstanceConfig | null>(
    null,
  );
  const [instanceLoading, setInstanceLoading] = useState(true);
  const [instanceError, setInstanceError] = useState("");

  const [keywords, setKeywords] = useState<DepthKeyword[]>([]);
  const [keywordsLoading, setKeywordsLoading] = useState(true);
  const [keywordsError, setKeywordsError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [depth, setDepth] = useState<SearchDepth>("standard");
  const [matchType, setMatchType] = useState<"exact" | "contains">("exact");
  const [addingKeyword, setAddingKeyword] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DepthKeyword | null>(null);
  const [deletingKeyword, setDeletingKeyword] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
    }
  }, [user]);

  useEffect(() => {
    let cancelled = false;
    api
      .get<InstanceConfig>(MEMORY_ENDPOINTS.CONFIGURE)
      .then((res) => {
        if (!cancelled) setInstanceConfig(res.data);
      })
      .catch((error) => {
        if (!cancelled) setInstanceError(getErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setInstanceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchKeywords = useCallback(async () => {
    setKeywordsLoading(true);
    try {
      const res = await api.get<DepthKeyword[]>(SEARCH_KEYWORDS_ENDPOINTS.BASE);
      setKeywords(res.data ?? []);
      setKeywordsError("");
    } catch (error) {
      setKeywordsError(getErrorMessage(error));
    } finally {
      setKeywordsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeywords();
  }, [fetchKeywords]);

  const groupedKeywords = useMemo(() => {
    const groups: Record<SearchDepth, DepthKeyword[]> = {
      minimal: [],
      standard: [],
      full: [],
    };
    for (const kw of keywords) {
      if (kw.category in groups) groups[kw.category].push(kw);
    }
    return groups;
  }, [keywords]);

  const profileDirty =
    user !== null && (name !== user.name || email !== user.email);
  const profileValid = name.trim().length > 0 && email.trim().length > 0;

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    try {
      await api.patch(AUTH_ENDPOINTS.ME, {
        name: name.trim(),
        email: email.trim(),
      });
      await refreshUser();
      toast({ title: "个人资料已更新", variant: "success" });
    } catch (error) {
      toast({
        title: "更新个人资料失败",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast({
        title: "两次输入的密码不一致",
        variant: "destructive",
      });
      return;
    }

    setSavingPassword(true);
    try {
      await api.post(AUTH_ENDPOINTS.CHANGE_PASSWORD, {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast({ title: "密码已更新", variant: "success" });
    } catch (error) {
      toast({
        title: "更新密码失败",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setSavingPassword(false);
    }
  };

  const handleAddKeyword = async () => {
    const kw = keyword.trim();
    if (!kw || addingKeyword) return;
    setAddingKeyword(true);
    try {
      await api.post(SEARCH_KEYWORDS_ENDPOINTS.BASE, {
        keyword: kw,
        category: depth,
        match_type: matchType,
      });
      setKeyword("");
      toast({ title: "词汇已添加", variant: "success" });
      await fetchKeywords();
    } catch (error) {
      toast({
        title: "添加失败",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setAddingKeyword(false);
    }
  };

  const handleDeleteKeyword = async () => {
    if (!deleteTarget || deletingKeyword) return;
    setDeletingKeyword(true);
    try {
      await api.delete(SEARCH_KEYWORDS_ENDPOINTS.BY_ID(deleteTarget.id));
      toast({ title: "词汇已删除", variant: "success" });
      setDeleteTarget(null);
      await fetchKeywords();
    } catch (error) {
      toast({
        title: "删除失败",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setDeletingKeyword(false);
    }
  };

  const llmModel = providerModel(instanceConfig?.llm);
  const embedderModel = providerModel(instanceConfig?.embedder);
  const rerankerModel = providerModel(instanceConfig?.reranker);
  const graphHasOwn = !!(
    instanceConfig?.graph_store?.llm || instanceConfig?.graph_store?.embedder
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold font-fustat">设置</h1>

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">个人资料</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="settings-name" className="text-xs">
                姓名
              </Label>
              <Input
                id="settings-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="settings-email" className="text-xs">
                邮箱
              </Label>
              <Input
                id="settings-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>
          <Button
            onClick={handleSaveProfile}
            disabled={!profileDirty || !profileValid || savingProfile}
          >
            {savingProfile ? "保存中..." : "保存个人资料"}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">密码</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="settings-current-password" className="text-xs">
              当前密码
            </Label>
            <Input
              id="settings-current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="settings-new-password" className="text-xs">
                新密码
              </Label>
              <Input
                id="settings-new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="至少 8 个字符"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="settings-confirm-password" className="text-xs">
                确认新密码
              </Label>
              <Input
                id="settings-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
          </div>
          <Button
            onClick={handleChangePassword}
            disabled={
              !currentPassword ||
              newPassword.length < 8 ||
              !confirmPassword ||
              savingPassword
            }
          >
            {savingPassword ? "保存中..." : "更新密码"}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">外观</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <span className="text-sm text-onSurface-default-secondary">
              主题
            </span>
            <div className="inline-flex items-center rounded-md border border-memBorder-primary bg-surface-default-secondary p-1">
              <button
                type="button"
                onClick={() => setTheme("dark")}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors",
                  resolvedTheme === "dark"
                    ? "bg-onSurface-default-primary text-surface-default-primary"
                    : "text-onSurface-default-tertiary hover:text-onSurface-default-primary",
                )}
              >
                <Moon className="size-3.5" />
                深色
              </button>
              <button
                type="button"
                onClick={() => setTheme("light")}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors",
                  resolvedTheme === "light"
                    ? "bg-onSurface-default-primary text-surface-default-primary"
                    : "text-onSurface-default-tertiary hover:text-onSurface-default-primary",
                )}
              >
                <Sun className="size-3.5" />
                浅色
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">实例信息</CardTitle>
        </CardHeader>
        <CardContent>
          {instanceLoading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-5 w-full" />
              ))}
            </div>
          ) : instanceError ? (
            <p className="text-sm text-sentry-danger">{instanceError}</p>
          ) : (
            <div>
              <InfoRow
                label="LLM"
                value={
                  <span className="font-mono text-xs">{llmModel ?? "—"}</span>
                }
              />
              <InfoRow
                label="嵌入模型"
                value={
                  <span className="font-mono text-xs">
                    {embedderModel ?? "—"}
                  </span>
                }
              />
              <InfoRow
                label="重排序"
                value={
                  rerankerModel ? (
                    <span className="font-mono text-xs">{rerankerModel}</span>
                  ) : (
                    <span className="text-xs text-onSurface-default-tertiary">
                      未配置
                    </span>
                  )
                }
              />
              <InfoRow
                label="存储后端"
                value={
                  <span className="flex items-center gap-1.5">
                    <Badge variant="violet" className="font-mono text-[10px]">
                      向量 {instanceConfig?.vector_store?.provider ?? "—"}
                    </Badge>
                    <Badge variant="pink" className="font-mono text-[10px]">
                      图 {instanceConfig?.graph_store?.provider ?? "—"}
                    </Badge>
                  </span>
                }
              />
              <InfoRow
                label="图数据独立模型"
                value={
                  <Badge variant={graphHasOwn ? "success" : "outline"}>
                    {graphHasOwn ? "已单独配置" : "使用全局"}
                  </Badge>
                }
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">深度路由词汇</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-onSurface-default-secondary">
            查询命中词汇时路由到对应搜索深度（minimal 精简 / standard 标准 /
            full 完整），优先级 full &gt; standard &gt; minimal
          </p>

          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="settings-keyword" className="text-xs">
                词汇
              </Label>
              <Input
                id="settings-keyword"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAddKeyword();
                }}
                placeholder="如：收到"
                className="w-40"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">深度</Label>
              <Select
                value={depth}
                onValueChange={(v) => setDepth(v as SearchDepth)}
              >
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="minimal">精简</SelectItem>
                  <SelectItem value="standard">标准</SelectItem>
                  <SelectItem value="full">完整</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">匹配方式</Label>
              <Select
                value={matchType}
                onValueChange={(v) => setMatchType(v as "exact" | "contains")}
              >
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="exact">精确</SelectItem>
                  <SelectItem value="contains">包含</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleAddKeyword}
              disabled={addingKeyword || !keyword.trim()}
            >
              {addingKeyword ? "添加中..." : "添加"}
            </Button>
          </div>

          {keywordsError ? (
            <p className="text-sm text-sentry-danger">{keywordsError}</p>
          ) : keywordsLoading ? (
            <div className="space-y-4">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              {DEPTH_ORDER.map((d) => {
                const items = groupedKeywords[d];
                const meta = DEPTH_META[d];
                return (
                  <div
                    key={d}
                    className="rounded-md border border-memBorder-primary bg-surface-default-secondary p-3"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <span className={cn("size-1.5 rounded-full", meta.dot)} />
                      <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-onSurface-default-secondary">
                        {meta.label}
                      </span>
                      <span className="text-xs tabular-nums text-onSurface-default-tertiary">
                        {items.length}
                      </span>
                    </div>
                    {items.length === 0 ? (
                      <p className="py-2 text-xs text-onSurface-default-tertiary">
                        暂无词汇
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {items.map((kw) => (
                          <div
                            key={kw.id}
                            className="flex items-center justify-between gap-2 rounded border border-memBorder-primary bg-surface-default-primary px-2.5 py-1.5"
                          >
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="truncate text-sm text-onSurface-default-primary">
                                {kw.keyword}
                              </span>
                              {kw.lang && (
                                <span className="text-[10px] uppercase text-onSurface-default-tertiary">
                                  {kw.lang}
                                </span>
                              )}
                            </div>
                            <div className="flex shrink-0 items-center gap-1.5">
                              <Badge
                                variant={
                                  kw.match_type === "exact" ? "violet" : "pink"
                                }
                                className="text-[10px]"
                              >
                                {kw.match_type === "exact" ? "精确" : "包含"}
                              </Badge>
                              <button
                                type="button"
                                onClick={() => setDeleteTarget(kw)}
                                className="rounded p-1 text-onSurface-default-tertiary transition-colors hover:bg-surface-default-fg-secondary hover:text-sentry-danger"
                                aria-label={`删除词汇 ${kw.keyword}`}
                              >
                                <Trash2 className="size-3.5" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除词汇</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除「{deleteTarget?.keyword}
              」吗？删除后该词汇将不再参与搜索深度路由。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteKeyword}
              disabled={deletingKeyword}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingKeyword ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
