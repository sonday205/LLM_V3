FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.runtime/huggingface

WORKDIR /app

COPY requirements.txt requirements-embedding-cpu.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-embedding-cpu.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY data ./data
COPY frontend ./frontend
COPY scripts ./scripts
COPY evaluation ./evaluation

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.runtime/huggingface \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8005/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
