# DEPLOY_SERVER.md — Linux 服务器部署指南

本项目提供 `docker-compose.server.yml` 用于服务器部署，特点：
- Nginx 作为统一入口：`/` 前端、`/api` 后端、`/jupyter/` JupyterHub
- 默认更安全：部分服务端口可能绑定到 `127.0.0.1`（只允许本机访问）
- 使用 Docker volumes 持久化 Postgres、Redis、Hub 数据

---

## 1. 前置要求

服务器安装：
- Docker Engine
- Docker Compose（`docker compose` 可用）

建议：
- 服务器至少 2C4G（课堂多人建议更高）
- 磁盘空间充足（Notebook/课程资源会增长）

---

## 2. 部署步骤（最小可跑）

在仓库根目录：

1) 准备环境变量文件
```bash
cp .env.server.example .env
```

2) 编辑 `.env`（至少填写）
- `DB_PASSWORD`（Postgres 密码）
- `EXPERIMENT_MANAGER_API_TOKEN`（后端调用 Hub 的服务 token，建议长随机串）
- `DUMMY_PASSWORD`（**强烈建议设置**：Hub 登录口令，公网必设）
- `JUPYTERHUB_BASE_URL`（默认 `/jupyter`，不要随便改）
- （可选）AI keys：`DEEPSEEK_API_KEY`、`TAVILY_API_KEY`

3) 启动
```bash
docker compose -f docker-compose.server.yml up -d --build
```

4) 初始化示例数据（可重复执行）
```bash
docker compose -f docker-compose.server.yml exec -T experiment-manager python init_db.py
```

---

## 3. 访问地址（服务器）

- 门户（经 Nginx）：`http://<服务器IP>/`
- JupyterHub（经 Nginx）：`http://<服务器IP>/jupyter/`
- 后端 API（经 Nginx）：`http://<服务器IP>/api/`

如需直连检查（以 compose 端口映射为准）：
- experiment-manager：`http://<服务器IP>:8001/docs`
- jupyterhub：`http://<服务器IP>:8003`

> 生产建议始终使用 Nginx 统一入口，避免 base_url / cookie / websocket 差异。

---

## 4. 安全建议（强烈建议按这个做）

### 4.1 公网部署必须设置 DUMMY_PASSWORD
Hub 使用 DummyAuthenticator；如果不设置共享密码（或设置太弱），等同“任意登录”。  
在 `.env` 里设置：
- `DUMMY_PASSWORD=<强口令>`

### 4.2 不要把 Postgres 暴露到公网
确保 Postgres 端口不对外开放（compose 中不要绑定 `0.0.0.0:5432`）。

### 4.3 监控/AI 默认只允许本机访问（推荐保持）
很多部署会把 Grafana/Prometheus/AI 绑定到 `127.0.0.1`：
- 需要查看时用 SSH 隧道：
```bash
ssh -L 3001:127.0.0.1:3001 -L 9090:127.0.0.1:9090 user@<服务器IP>
```

### 4.4 建议开启 HTTPS
如有域名，建议加 TLS（可用 Nginx + certbot / 或上游 LB）。  
HTTPS 处理后，务必验证 `/jupyter/` 的 websocket 正常。

---

## 5. 常用运维命令

启动/更新：
```bash
docker compose -f docker-compose.server.yml up -d --build
```

查看状态：
```bash
docker compose -f docker-compose.server.yml ps
```

查看日志（网关/后端/Hub）：
```bash
docker compose -f docker-compose.server.yml logs -f nginx
docker compose -f docker-compose.server.yml logs -f experiment-manager
docker compose -f docker-compose.server.yml logs -f jupyterhub
```

停止：
```bash
docker compose -f docker-compose.server.yml down
```

---

## 6. 数据持久化与备份

### 6.1 卷（volumes）
通常包括：
- Postgres 数据卷（例如 `postgres-data`）
- Redis 数据卷
- JupyterHub 数据卷
- 上传/课程资源卷

> 卷名以你的 compose 文件为准，可用 `docker volume ls` 查看。

### 6.2 备份 Postgres（建议定期做）
在服务器上执行（把用户名/库名按你的 compose 配置替换）：
```bash
docker compose -f docker-compose.server.yml exec -T postgres   pg_dump -U jupyterhub -d jupyterhub > pg_backup.sql
```

恢复：
```bash
cat pg_backup.sql | docker compose -f docker-compose.server.yml exec -T postgres   psql -U jupyterhub -d jupyterhub
```

---

## 7. 排错指南（从最常见到最有效）

### 7.1 访问 `/` 正常但 `/api` 502
1) 查看 nginx 日志：
```bash
docker compose -f docker-compose.server.yml logs -f nginx
```
2) 确认后端是否启动：
```bash
docker compose -f docker-compose.server.yml ps
docker compose -f docker-compose.server.yml logs -f experiment-manager
```

### 7.2 访问 `/jupyter/` 白屏，或内核/终端连接失败
1) 确保通过 Nginx 访问：`http://<服务器IP>/jupyter/`
2) 确认 nginx 反代已启用 websocket（本仓库配置默认应已启用）
3) 查看 hub 日志：
```bash
docker compose -f docker-compose.server.yml logs -f jupyterhub
```

### 7.3 后端启动失败（常见原因：数据库连接失败）
查看后端日志，重点关注：
- DB host/port
- 用户名/密码
- migrations/init_db 失败信息

### 7.4 环境变量修改后未生效
Docker Compose 会将 `.env` 注入到容器启动时；修改 `.env` 后需要重启相关容器。

- 仅重启（多数情况够用）：
```bash
docker compose -f docker-compose.server.yml up -d
```

- 修改了镜像构建相关内容或需要强制刷新（建议用这个）：
```bash
docker compose -f docker-compose.server.yml up -d --build
```

- 仍不生效时，建议查看容器实际拿到的变量：
```bash
docker compose -f docker-compose.server.yml exec experiment-manager env | grep -E "DB_|JUPYTER|DUMMY|TOKEN"
```

---

## 8. 上线前检查清单

- [ ] `.env` 已设置 `DUMMY_PASSWORD`（公网必选）
- [ ] `EXPERIMENT_MANAGER_API_TOKEN` 为强随机串
- [ ] Postgres 未暴露公网端口
- [ ] `/jupyter/` websocket 正常（能开终端/跑代码）
- [ ] `init_db.py` 执行成功（或你已有生产数据）
- [ ] Grafana/Prometheus 未公网暴露（或已加鉴权/内网隔离）
- [ ]（可选）HTTPS 已配置，且 `/jupyter/` 正常
