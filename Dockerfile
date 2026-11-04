FROM python:3.12-slim-bookworm AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.18
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
RUN groupadd --gid 10001 memory && useradd --uid 10001 --gid memory --create-home memory \
    && mkdir /app/data && chown memory:memory /app/data
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 4180
HEALTHCHECK --interval=5s --timeout=4s --start-period=15s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4180/healthz', timeout=3)"
CMD ["project-memory", "serve", "--host", "0.0.0.0"]
