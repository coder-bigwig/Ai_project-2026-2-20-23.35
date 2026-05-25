FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.104.0 \
    uvicorn[standard]==0.24.0 \
    alembic==1.13.2 \
    sqlalchemy==2.0.23 \
    asyncpg==0.30.0 \
    psycopg2-binary==2.9.7 \
    redis==5.0.1 \
    celery==5.3.4 \
    python-multipart==0.0.6 \
    requests==2.31.0 \
    openpyxl==3.1.5 \
    tavily-python==0.5.0

COPY app/ /app/app/
COPY init_db.py /app/init_db.py
COPY alembic.ini /app/alembic.ini
COPY alembic/ /app/alembic/
COPY app/scripts/ /app/scripts/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
