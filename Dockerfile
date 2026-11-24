# One image: builds the website, then runs the API and serves the built site from the same process.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend ./
COPY --from=web /web/dist /app/frontend/dist
ENV PATH="/app/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
# --proxy-headers: behind Caddy, use the real client IP (login lockout) and https scheme (Secure cookie).
# Safe because port 8000 is not published; only the Caddy container can reach it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
