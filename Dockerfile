# Stage 1: build the React frontend with Node
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime serving the API and the built frontend
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend/dist \
    DATA_DIR=/app/data

# UID 1000 matches the itzg/minecraft-server default, so both can write server folders.
RUN useradd --uid 1000 --create-home mcpanel
WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir -p /app/data && chown mcpanel:mcpanel /app/data

USER mcpanel
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
