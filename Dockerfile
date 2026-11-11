FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TUNEBRIDGE_HOST=0.0.0.0 \
    TUNEBRIDGE_PORT=8787

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY deploy/entrypoint.sh /usr/local/bin/tunebridge-entrypoint

RUN useradd --create-home --uid 10001 tunebridge \
    && mkdir -p /app/data \
    && chown -R tunebridge:tunebridge /app \
    && chmod +x /usr/local/bin/tunebridge-entrypoint

USER tunebridge

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${TUNEBRIDGE_PORT}/api/health" || exit 1

ENTRYPOINT ["tunebridge-entrypoint"]
