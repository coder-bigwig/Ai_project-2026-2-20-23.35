# Local Relay API

这是一个独立的本地中转服务，适合直接在 VSCode 里启动，不依赖当前项目。

默认上游配置：

- `RELAY_UPSTREAM_BASE_URL=https://codeflow.asia`
- `RELAY_DEFAULT_MODEL=claude-sonnet-4-6`

## 1. 准备环境

```powershell
cd local-relay-api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

然后编辑 `.env`，只填你自己的真实 Key，不要把 Key 写进代码：

```env
RELAY_UPSTREAM_BASE_URL=https://codeflow.asia
RELAY_UPSTREAM_API_KEY=你的真实Key
RELAY_DEFAULT_MODEL=claude-sonnet-4-6
RELAY_ACCESS_TOKEN=
RELAY_LISTEN_HOST=127.0.0.1
RELAY_LISTEN_PORT=8010
```

## 2. 启动

```powershell
cd local-relay-api
.venv\Scripts\Activate.ps1
python app.py
```

启动后本地地址：

- `http://127.0.0.1:8010/health`
- `http://127.0.0.1:8010/v1/models`
- `http://127.0.0.1:8010/v1/chat/completions`

## 3. 调用示例

不加本地鉴权：

```powershell
$body = @{
  model = "claude-sonnet-4-6"
  stream = $false
  messages = @(
    @{ role = "user"; content = "你好，回复一句测试成功" }
  )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8010/v1/chat/completions" `
  -ContentType "application/json" `
  -Body $body
```

如果你设置了 `RELAY_ACCESS_TOKEN`，则本地调用时要加：

```powershell
-Headers @{ Authorization = "Bearer 你设置的本地token" }
```

## 4. 给客户端使用

如果你要在别的工具里接这个中转：

- Base URL 填 `http://127.0.0.1:8010/v1`
- Model 填 `claude-sonnet-4-6`
- API Key:
  - 如果没开 `RELAY_ACCESS_TOKEN`，很多客户端可随便填一个占位值
  - 如果开了 `RELAY_ACCESS_TOKEN`，这里填这个本地 token

## 5. 说明

- 这是 OpenAI 兼容转发，不会把你的上游 Key 暴露给客户端。
- 默认支持流式和非流式 `/v1/chat/completions`。
- `/v1/models` 会优先尝试读取上游模型列表，失败时回退为默认模型。
