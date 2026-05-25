FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.104.0 \
    uvicorn[standard]==0.24.0 \
    httpx==0.25.0 \
    tavily-python==0.5.0

COPY ai_assistant.py /app/ai_assistant.py

CMD ["uvicorn", "ai_assistant:app", "--host", "0.0.0.0", "--port", "8000"]
