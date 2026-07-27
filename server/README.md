# Mem0 自部署 Server（Fork 版）

> 基于 mem0-graph v2.0.14.post1，带 FalkorDB 图存储支持。

本目录包含 FastAPI 后端 + Next.js Dashboard，一键 `docker compose up` 部署。

## 快速开始

```bash
cd server
# 无需 .env 文件，配置通过 docker-compose.yaml 环境变量注入即可
```

### 1. 创建 Provider 配置

```bash
cat > config.json << 'EOF'
{
  "llm": {
    "provider": "openai",
    "config": {
      "api_key": "sk-你的Key",
      "model": "gpt-4o-mini",
      "temperature": 0.1,
      "max_tokens": 8000
    }
  },
  "embedder": {
    "provider": "openai",
    "config": {
      "api_key": "sk-你的Key",
      "model": "text-embedding-3-small"
    }
  },
  "graph_store": {
    "provider": "falkordb",
    "config": {
      "host": "falkordb",
      "port": 6379,
      "database": "mem0"
    }
  }
}
EOF
```

### 2. 启动

```bash
docker compose up -d
```

等几秒让 PostgreSQL 和 alembic 完成初始化。

### 3. 获取管理员凭据

Server 容器启动时**自动创建**管理员账号。查看容器日志：

```bash
docker compose logs mem0 | grep -E "(admin|密码)"
```

日志中会打印：

```
👤 Admin user created:
   Email: admin@mem0.dev
   Password: <随机生成的密码>
```

直接用这个邮箱和密码登录，不需要手动创建管理员。

### 4. 打开 Dashboard

浏览器访问 `http://你的IP:3002`，用日志中的 admin 凭据登录。

## 管理命令

```bash
# 查看日志
docker compose logs -f

# 停止
docker compose down

# 清空所有数据（删 PostgreSQL 卷）
docker compose down -v
```

## 重置密码

```bash
docker exec -it mem0-mem0-1 python3 /app/scripts/reset_admin_password.py
```

## 日志清理

`request_logs` 表只增不减，定期清理：

```bash
docker exec -it mem0-mem0-1 python3 /app/scripts/prune_request_logs.py
```

## 本地访问地址

- Dashboard: `http://localhost:3002`
- API: `http://localhost:8888`
- OpenAPI 文档: `http://localhost:8888/docs`

## Dashboard 功能

登录后可访问：

- **Requests** — API 调用审计日志
- **Memories** — 浏览和搜索记忆
- **Entities** — 用户/Agent/会话列表及计数
- **API Keys** — 创建和管理 API Key
- **Configuration** — 查看当前 Provider 配置
- **Settings** — 修改密码和个人信息

## 安全

- Dashboard 使用 JWT 登录
- API 使用 `X-API-Key` 头鉴权
- Auth 默认开启，本地开发可设 `AUTH_DISABLED=true`
- Dashboard 自动设置 `X-Frame-Options: DENY`、`CSP: frame-ancestors 'none'` 等安全头

## 遥测

默认开启（与 mem0 OSS 一致），发送至匿名 PostHog。设 `MEM0_TELEMETRY=false` 可关闭。

## 参考

更多文档见 [docs.mem0.ai](https://docs.mem0.ai/open-source/overview) 和项目根目录 [README.md](../README.md)。
