# JupyterHub 实训平台（Docker Compose 一键部署）

基于 Docker + JupyterHub 的多租户教学实训平台，包含：

- **前端门户**（React）
- **实验管理后端**（FastAPI，PostgreSQL + Redis）
- **AI 助手服务**（FastAPI，默认 DeepSeek，可选 Tavily 联网检索）
- **JupyterHub**（DockerSpawner：每个学生独立 Notebook 容器）
- **监控**（Prometheus + Grafana）
- **统一入口网关**（Nginx：`/` 前端、`/api` 后端、`/jupyter` Hub）

> 统一入口（本地）：`http://localhost:8080`  
> 统一入口（服务器）：`http://<服务器IP>/`  
> Hub 路径前缀：默认 `/jupyter`（同源反代，适合课堂/内网/公网）  

---

## 1. 三种使用方式（先选一个）

| 目标                         | 使用方式                            | 入口                    |
| ---------------------------- | ----------------------------------- | ----------------------- |
| 本地完整运行（推荐先跑这个） | `docker-compose.yml` 或 `start.bat` | `http://localhost:8080` |
| 前端热更新开发               | `start-dev.bat`                     | `http://localhost:3000` |
| Linux 服务器部署             | `docker-compose.server.yml`         | `http://<服务器IP>/`    |

---

## 2. 目录结构（核心）

```text
.
├── ai-service/                 # AI 助手服务（FastAPI）
├── backend/                    # 实验管理后端（FastAPI）
├── frontend/                   # 前端门户（React）
├── experiments/                # 课程与实验资源（会同步到 Docker 卷）
├── jupyterhub/                 # JupyterHub 配置（DockerSpawner）
├── monitoring/                 # Prometheus / Grafana 配置
├── nginx/                      # Nginx 配置（/ /api /jupyter 反代）
├── docker-compose.yml          # 本地完整模式
├── docker-compose.server.yml   # 服务器部署模式
├── start.bat                   # Windows 一键启动（完整模式）
├── start-dev.bat               # Windows 开发模式（前端热更新）
└── stop-dev.bat                # 停止开发模式后端容器
```

------

## 3. 前置要求

- Docker Desktop（Windows/Mac）或 Docker Engine（Linux）
- Docker Compose（`docker compose` 可用）
- Node.js 18+（仅“开发模式”需要）

------

## 4. 本地完整模式（推荐）

### 4.1 Windows 一键启动

在仓库根目录运行：

```bat
start.bat
```

脚本会构建镜像并启动容器，并在 `experiment-manager` 容器内执行 `python init_db.py` 初始化示例实验数据。

### 4.2 手动启动（跨平台）

```bash
docker compose up -d --build
```

首次启动建议执行一次初始化（可重复执行，已有数据会跳过）：

```bash
docker compose exec -T experiment-manager python init_db.py
```

### 4.3 本地访问地址

- **统一入口（推荐）**：`http://localhost:8080`
- **JupyterHub（经网关）**：`http://localhost:8080/jupyter/`
- 后端 API 文档（直连容器端口）：`http://localhost:8001/docs`
- AI 助手 API 文档：`http://localhost:8002/docs`
- JupyterHub（直连端口）：`http://localhost:8003`
- Grafana：`http://localhost:3001`（默认 `admin/admin`）
- Prometheus：`http://localhost:9090`

### 4.4 停止

```bash
docker compose down
```

------

## 5. 开发模式（前端热更新）

> 开发模式会：启动后端相关容器，并**停掉生产前端/网关**，然后在本机启动 React dev server。

启动：

```bat
start-dev.bat
```

停止：

```bat
stop-dev.bat
```

只启动后端（不启动前端 dev server）：

```bat
set SKIP_FRONTEND=1 && start-dev.bat
```

开发模式入口：

- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8001`

更多说明见 `DEV_MODE.md`。

------

## 6. 服务器部署模式（Linux）

快速步骤：

```bash
cp .env.server.example .env
docker compose -f docker-compose.server.yml up -d --build
```

常用检查：

```bash
docker compose -f docker-compose.server.yml ps
docker compose -f docker-compose.server.yml logs -f nginx
```

默认入口：

- 门户：`http://<服务器IP>/`
- JupyterHub：`http://<服务器IP>/jupyter/`

详细说明见 `DEPLOY_SERVER.md`。

------

## 7. 网关路由（Nginx）

平台通过 Nginx 做统一入口：

- `/` → 前端（React 静态站点）
- `/api/` → 后端（experiment-manager）
- `/jupyter/` → JupyterHub（支持 WebSocket，内核/终端/LSP 等）

> 网关还支持将 `?token=...` 写入 Cookie，并桥接到 `Authorization`，方便浏览器同源访问 JupyterHub。

------

## 8. 账号与认证说明（重要）

### 8.1 门户/后端登录

- 登录接口：`POST /api/auth/login`
- 默认账号来源（通过环境变量配置）：
  - 管理员：`ADMIN_ACCOUNTS`（默认 `admin`）
  - 教师：`TEACHER_ACCOUNTS`（默认 `teacher_001` ~ `teacher_005`）
- 默认密码：`123456`（建议首次登录后修改）

### 8.2 JupyterHub 登录（DummyAuthenticator）

- Hub 使用 `DummyAuthenticator`：
  - 若未设置 `DUMMY_PASSWORD`：Hub 登录可使用任意密码（**公网不安全**）
  - 公网部署**务必设置** `DUMMY_PASSWORD`

------

## 9. 关键环境变量

推荐基于 `.env.server.example` 配置（服务器模式必用；本地模式也可用）：

- `DB_PASSWORD`：PostgreSQL 密码
- `EXPERIMENT_MANAGER_API_TOKEN`：后端调用 JupyterHub API 的服务 token（建议长随机串）
- `DUMMY_PASSWORD`：JupyterHub 共享登录口令（服务器强烈建议设置）
- `JUPYTERHUB_BASE_URL`：Hub 路径前缀（默认 `/jupyter`）
- `JUPYTERHUB_PUBLIC_URL`：后端返回给前端的 Hub 公网地址（默认 `/jupyter`）
- AI（可选）：
  - `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`
  - `TAVILY_API_KEY`（联网检索能力）
  - `CACHE_TTL` / `MAX_HISTORY`（AI 会话缓存参数）

------

## 10. 数据与持久化（重要）

本项目默认使用 Docker volumes 做持久化（重启/升级不丢数据）：

- `postgres-data`：PostgreSQL 数据
- `redis-data`：Redis 数据
- `jupyterhub-data`：JupyterHub 配置/密钥/运行态信息
- `training-uploads`：后端上传文件
- `course-materials`：课程与实验资源（由 `data-loader` 从 `./experiments` 同步进卷）

> 后端存储后端 **只允许 PostgreSQL**（不会回退到 JSON）。如果 Postgres 初始化失败，后端会直接退出，避免“看似能跑但没落库”的情况。

------

## 11. 常用命令

本地完整模式：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f experiment-manager
docker compose down
```

服务器模式：

```bash
docker compose -f docker-compose.server.yml up -d --build
docker compose -f docker-compose.server.yml ps
docker compose -f docker-compose.server.yml logs -f nginx
docker compose -f docker-compose.server.yml down
```

初始化示例实验数据：

```bash
docker compose exec -T experiment-manager python init_db.py
```

------

## 12. 常见问题（FAQ）

### 12.1 端口冲突

本地完整模式至少需要这些端口可用：`8080`、`8001`、`8002`、`8003`、`3001`、`9090`。
开发模式还需要 `3000`。

### 12.2 访问 `/jupyter` 白屏或内核无法连接

- 确保你是走网关：`http://localhost:8080/jupyter/`（而不是直接 `8003`）
- 确保 Nginx 配置里 WebSocket 反代启用（本仓库已配置）

### 12.3 服务器上为什么 AI/监控默认打不开？

服务器 compose 默认把 AI / Prometheus / Grafana 端口绑定到 `127.0.0.1`，适合通过 SSH 隧道访问（更安全）。如需公网开放，请修改 `docker-compose.server.yml` 的端口绑定。

------

## 13. 技术栈

- Frontend: React + axios + react-router-dom
- Backend: FastAPI + SQLAlchemy + Alembic + asyncpg/psycopg2 + Redis
- Hub: JupyterHub + DockerSpawner
- Proxy: Nginx
- Observability: Prometheus + Grafana
- AI: DeepSeek Chat Completions（可选 Tavily web search）
