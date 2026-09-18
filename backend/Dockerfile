# ---- Stage 1: builder ----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN python -m spacy download en_core_web_lg

# Pre-download the fastembed model at build time so the container never
# needs network access to Hugging Face (or GCS) at runtime.
RUN python -c "from fastembed import TextEmbedding; \
    TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed_cache')"


# ---- Stage 2: runtime ----
FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /opt/fastembed_cache /opt/fastembed_cache

ENV PATH="/opt/venv/bin:$PATH"
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache

WORKDIR /app

COPY --chown=appuser:appuser app ./app
COPY alembic.ini .
COPY alembic ./alembic

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=30s \
    --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

CMD ["sh", "-c", ". /vault/secrets/config && . /vault/secrets/gateway && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]