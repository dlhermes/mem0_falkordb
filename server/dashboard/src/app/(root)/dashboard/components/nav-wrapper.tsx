"use client";

import { MainNav } from "./main-nav";
import {
  PanelRight,
  LogOut,
  Settings,
  HelpCircle,
  ChevronDown,
  Search,
  Building2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { format } from "date-fns";
import { COLLAPSED_SIDEBAR_WIDTH, SIDEBAR_WIDTH } from "../../clientLayout";
import { useDispatch, useSelector } from "react-redux";
import { cn } from "@/lib/utils";
import { RootState } from "@/store/store";
import { toggleSidebar } from "@/store/reducers/layoutReducer";
import { useAuth } from "@/hooks/use-auth";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/utils/api";
import { MEMORY_ENDPOINTS } from "@/utils/api-endpoints";
import { Memory } from "@/types/api";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard/requests": "请求",
  "/dashboard/memories": "记忆",
  "/dashboard/entities": "实体",
  "/dashboard/analytics": "分析",
  "/dashboard/api-keys": "API 密钥",
  "/dashboard/configuration": "配置",
  "/dashboard/settings": "设置",
};

export default function NavWrapper() {
  const dispatch = useDispatch();
  const pathname = usePathname();
  const router = useRouter();
  const isSidebarCollapsed = useSelector(
    (state: RootState) => state.layout.isSidebarCollapsed,
  );
  const { user, logout } = useAuth();

  const instanceName = process.env.NEXT_PUBLIC_INSTANCE_NAME || "Mem0";
  const pageTitle = PAGE_TITLES[pathname] ?? "";

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Memory[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [open, setOpen] = useState(false);
  const searchWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setIsSearching(false);
      return;
    }
    let cancelled = false;
    setIsSearching(true);
    const timer = setTimeout(() => {
      api
        .get(MEMORY_ENDPOINTS.SEARCH, { params: { q, limit: 6 } })
        .then((res) => {
          if (cancelled) return;
          const raw = res.data?.results ?? [];
          setResults(Array.isArray(raw) ? raw : []);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setIsSearching(false);
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  const handleBlur = (e: React.FocusEvent<HTMLDivElement>) => {
    if (!searchWrapRef.current?.contains(e.relatedTarget as Node)) {
      setOpen(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && query.trim()) {
      router.push(`/dashboard/memories?q=${encodeURIComponent(query.trim())}`);
      setOpen(false);
    }
  };

  const truncate = (text: string, max: number) =>
    text.length > max ? `${text.slice(0, max)}…` : text;

  const formatTime = (m: Memory) => {
    const t = m.updated_at ?? m.created_at;
    return t ? format(new Date(t), "MMM d, yyyy") : "--";
  };

  const handleToggle = useCallback(() => {
    dispatch(toggleSidebar());
  }, [dispatch]);

  return (
    <>
      <div
        className="fixed top-0 left-0 h-full flex justify-between flex-col overflow-hidden transition-all duration-300 ease-in-out z-30 bg-surface-default-primary border-r border-memBorder-primary"
        style={{
          width: isSidebarCollapsed ? COLLAPSED_SIDEBAR_WIDTH : SIDEBAR_WIDTH,
        }}
      >
        <div className="flex flex-col flex-1 min-h-0 items-start gap-5 px-3 py-4 overflow-y-auto overflow-x-hidden">
          <div
            className={cn(
              "relative flex w-full",
              isSidebarCollapsed ? "p-0 justify-center" : "",
            )}
          >
            <div
              className={cn(
                "flex items-center w-full",
                isSidebarCollapsed ? "justify-center" : "gap-2",
              )}
            >
              <div className="flex items-center justify-center size-7 rounded-md bg-surface-default-tertiary shrink-0">
                <Building2 className="size-4 text-onSurface-default-primary" />
              </div>
            </div>
          </div>

          <MainNav className="w-full" />
        </div>

        {!isSidebarCollapsed && (
          <div className="flex flex-col shrink-0">
            <div className="mx-3 px-0 py-3 border-t border-memBorder-primary">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-2 w-full text-left hover:bg-surface-default-secondary-hover rounded-md p-1.5 transition-colors">
                    <div className="grid size-7 place-items-center rounded-md bg-surface-default-tertiary text-onSurface-default-secondary text-xs font-semibold shrink-0">
                      {user?.name?.charAt(0).toUpperCase() || "?"}
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="typo-body-xs text-onSurface-default-primary truncate">
                        {user?.name}
                      </span>
                      <span className="typo-caption-sm text-onSurface-default-tertiary truncate">
                        {user?.email}
                      </span>
                    </div>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="start"
                  side="top"
                  className="w-56 font-fustat bg-surface-default-primary border-memBorder-secondary"
                >
                  <div className="px-2 py-1.5">
                    <p className="typo-body-sm text-onSurface-default-primary">
                      {user?.name}
                    </p>
                    <p className="typo-body-xs text-onSurface-default-tertiary">
                      {user?.email}
                    </p>
                  </div>
                  <DropdownMenuSeparator className="bg-memBorder-primary" />
                  <DropdownMenuItem
                    asChild
                    className="typo-body-sm text-onSurface-default-primary hover:bg-surface-default-tertiary-hover focus:bg-surface-default-tertiary-hover cursor-pointer"
                  >
                    <Link href="/dashboard/settings">
                      <Settings className="size-4 mr-2" />
                      设置
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator className="bg-memBorder-primary" />
                  <DropdownMenuItem
                    onClick={logout}
                    className="typo-body-sm text-onSurface-default-primary hover:bg-surface-default-tertiary-hover focus:bg-surface-default-tertiary-hover cursor-pointer"
                  >
                    <LogOut className="size-4 mr-2" />
                    退出登录
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        )}
      </div>

      <div
        className="bg-surface-default-primary left-0 top-0 fixed flex justify-between items-center px-5 h-[52px] border-b border-memBorder-primary font-fustat z-20"
        style={{
          width: `calc(100% - ${isSidebarCollapsed ? COLLAPSED_SIDEBAR_WIDTH : SIDEBAR_WIDTH}px)`,
          left: `${isSidebarCollapsed ? COLLAPSED_SIDEBAR_WIDTH : SIDEBAR_WIDTH}px`,
        }}
      >
        <div className="flex items-center gap-3">
          {!isSidebarCollapsed && (
            <div className="flex items-center gap-2 rounded-md bg-sentry-surface-1 border border-sentry-hairline px-3 h-8 max-w-[220px]">
              <span className="size-2 shrink-0 rounded-full bg-sentry-lime" />
              <span className="text-xs font-medium text-onSurface-default-primary truncate">
                {instanceName}
              </span>
              <ChevronDown className="size-3.5 shrink-0 text-onSurface-default-tertiary" />
            </div>
          )}
          <button
            type="button"
            onClick={handleToggle}
            className="cursor-pointer text-onSurface-default-tertiary hover:text-onSurface-default-secondary"
            aria-label={isSidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
          >
            <PanelRight className="size-4" />
          </button>
          {pageTitle && (
            <span className="text-sm font-semibold tracking-tight text-onSurface-default-primary">
              {pageTitle}
            </span>
          )}
        </div>

        <div className="flex flex-1 min-w-0 justify-center px-4">
          <div
            ref={searchWrapRef}
            className="relative w-full max-w-md"
            onBlur={handleBlur}
          >
            <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-onSurface-default-tertiary pointer-events-none" />
            <Input
              variant="textField"
              className="pl-8"
              placeholder="搜索记忆…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setOpen(true)}
              onKeyDown={handleKeyDown}
            />
            {open && query.trim() !== "" && (
              <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-lg border border-sentry-hairline bg-sentry-surface-1 shadow-lg">
                {isSearching ? (
                  <div className="px-3 py-2.5 text-xs text-onSurface-default-tertiary">
                    搜索中…
                  </div>
                ) : results.length === 0 ? (
                  <div className="px-3 py-2.5 text-xs text-onSurface-default-tertiary">
                    未找到相关记忆
                  </div>
                ) : (
                  <ul className="max-h-72 overflow-y-auto">
                    {results.map((result) => (
                      <li key={result.id}>
                        <button
                          type="button"
                          onClick={() => {
                            router.push(
                              `/dashboard/memories?search=${result.id}`,
                            );
                            setOpen(false);
                          }}
                          className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-sentry-surface-2"
                        >
                          <span className="min-w-0 flex-1 text-sm leading-snug text-onSurface-default-primary">
                            {truncate(result.memory, 60)}
                          </span>
                          <Badge variant="outline" className="shrink-0">
                            {formatTime(result)}
                          </Badge>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Tooltip>
            <TooltipTrigger asChild>
              <a
                href="https://docs.mem0.ai/open-source/overview"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center text-onSurface-default-tertiary hover:text-onSurface-default-secondary"
              >
                <HelpCircle className="size-4 shrink-0" />
              </a>
            </TooltipTrigger>
            <TooltipContent>文档</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </>
  );
}
