# DEV_MODE.md — 前端热更新开发模式

本项目提供 **开发模式** 用于前端快速迭代：
- 后端相关服务（experiment-manager / ai-service / postgres / redis / jupyterhub 等）通过 Docker 运行
- 前端（React）使用本机 `npm start` 热更新
- 通常 **不会使用 Nginx 统一入口**，而是直接前端 dev server + API 直连

> 适用场景：改前端页面、联调 API、快速看效果  
> 不适用：模拟线上完整路径（请用完整模式 `docker compose up`）

---

## 1. 启动/停止（Windows）

在仓库根目录：

启动开发模式：
```bat
start-dev.bat
```

停止开发模式：
```bat
stop-dev.bat
```

只启动后端容器（不启动前端 dev server）：
```bat
set SKIP_FRONTEND=1 && start-dev.bat
```

---

## 2. 开发模式的端口与访问

默认常用入口：

- 前端（热更新）：`http://localhost:3000`
- 后端 API（experiment-manager）：`http://localhost:8001`
  - Swagger：`http://localhost:8001/docs`
- AI 服务：`http://localhost:8002`
  - Swagger：`http://localhost:8002/docs`
- JupyterHub（直连）：`http://localhost:8003`
  - 注意：直连 Hub 有时会遇到 websocket / base_url 的限制，推荐用完整模式走网关验证。
- Grafana：`http://localhost:3001`（默认 `admin/admin`）
- Prometheus：`http://localhost:9090`

---

## 3. 前端如何访问后端

开发时建议两种方式之一：

### 方式 A：前端通过 proxy 走 `/api`

如果你的前端 `package.json` 配了：
```json
"proxy": "http://localhost:8001"
```

那么前端代码里调用 API 就用相对路径：
- `/api/...` 或者直接 `/...`（看你项目现有约定）

优点：不需要处理 CORS，浏览器同源体验好。  
缺点：如果你需要同时代理 Hub/AI，可能要额外配置 dev server 代理规则。

### 方式 B：前端直接请求 `http://localhost:8001`

优点：简单直观。  
缺点：需要后端允许 CORS（或你本地浏览器会拦截）。

> 推荐：优先用方式 A（proxy），少踩坑。

---

## 4. 开发模式与“完整模式”的差异（重要）

开发模式通常具备这些差异：

1) **入口不同**
- 开发模式：`http://localhost:3000`
- 完整模式：`http://localhost:8080`（Nginx 统一入口）

2) **路径前缀不同**
- 完整模式里 Hub 多为 `/jupyter/` 前缀（通过 Nginx 反代）
- 开发模式直连 Hub 通常是根路径（`http://localhost:8003`）

3) **Cookie/Token 行为可能不同**
- 完整模式里网关可能会处理 token -> cookie -> authorization 的桥接
- 开发模式直连时，这些桥接不一定生效

> 如果你在开发模式能用 API，但在完整模式打不开 Hub（或内核连不上），优先用完整模式验证 `/jupyter/` 链路。

---

## 5. 常见问题（FAQ）

### 5.1 前端调用 API 404 / 走错地址
- 确认你请求的是 `localhost:3000` 下的 `/api/...`（proxy 生效）
- 或直接请求 `http://localhost:8001/...`（直连）

建议打开浏览器 Network 看最终请求 URL。

### 5.2 CORS 报错
- 优先改成 **proxy 方式**（方式 A）
- 如果必须直连：后端需要允许 `http://localhost:3000` 的跨域

### 5.3 Hub 里终端/内核无法连接（WebSocket）
- 开发模式直连 Hub 容易遇到 websocket 或 base_url 的差异
- 建议切换到完整模式：`http://localhost:8080/jupyter/` 做验证

### 5.4 我只想改后端，不想跑前端
用：
```bat
set SKIP_FRONTEND=1 && start-dev.bat
```
然后直接访问 `http://localhost:8001/docs` 进行联调。

---

## 6. 调试命令（最常用）

看容器状态：
```bash
docker compose ps
```

看后端日志：
```bash
docker compose logs -f experiment-manager
```

看 Hub 日志：
```bash
docker compose logs -f jupyterhub
```

进入后端容器：
```bash
docker compose exec experiment-manager bash
```

---

## 7. 建议的开发工作流

1) `start-dev.bat` 启动
2) 浏览器打开 `http://localhost:3000`
3) API 用 `http://localhost:8001/docs` 验证
4) 涉及 Hub 的改动，用完整模式走 `http://localhost:8080/jupyter/` 再验一遍
