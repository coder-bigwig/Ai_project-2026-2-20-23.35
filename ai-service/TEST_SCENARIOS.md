# AI Assistant Test Scenarios

Base URL:

```bash
http://localhost:8002
```

## 1) Need search

```bash
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"2026年2月14日有什么新闻\"}"
```

Expected:

- `used_search` is `true`
- `search_queries` is not empty
- `sources` contains search source objects

## 2) No search needed

```bash
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Python 列表推导式怎么写\"}"
```

Expected:

- usually `used_search` is `false`
- answer is generated directly from model knowledge

## 3) Multi-turn context

```bash
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"搜索最新AI模型\"}"
```

Then pass prior history:

```bash
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"它的参数量是多少\",\"history\":[{\"role\":\"user\",\"content\":\"搜索最新AI模型\"},{\"role\":\"assistant\",\"content\":\"<上一步返回的回答>\"}]}"
```

Expected:

- second response can continue from first context
- model may decide to search again depending on uncertainty

## 4) Cache hit

Call exactly the same query twice:

```bash
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"2026年2月14日有什么新闻\"}"
```

```bash
curl -X POST "http://localhost:8002/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"2026年2月14日有什么新闻\"}"
```

Check metrics:

```bash
curl "http://localhost:8002/api/stats"
```

Expected:

- `cache_hits` increases
- `cache_hit_rate` increases

## 5) WebSocket status + streaming

Connect to:

```text
ws://localhost:8002/ws/chat
```

Send:

```json
{"message":"搜索最新AI模型"}
```

Expected events:

- `{"type":"status","status":"thinking"}`
- `{"type":"status","status":"searching",...}` (if search is used)
- `{"type":"status","status":"generating"}`
- one or more `{"type":"chunk","delta":"..."}` events
- final `{"type":"final","response":"...","used_search":...}`
