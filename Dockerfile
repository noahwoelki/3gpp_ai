# Stage 1: build the React UI
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Python app that serves the API and the built UI
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.9 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, so code changes don't reinstall them
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist

ENV PATH="/app/.venv/bin:$PATH"
# Cloud Run sets PORT, 8080 is its default
CMD ["sh", "-c", "uvicorn specdelta.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
