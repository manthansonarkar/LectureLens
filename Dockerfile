# Stage 1: Build Frontend Studio UI
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python + FFmpeg + Node Runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LECTURELENS_HOST=0.0.0.0 \
    LECTURELENS_PORT=8000 \
    LECTURELENS_AUTO_CLEANUP=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt README.md ./
COPY backend/ ./backend/
COPY --from=frontend-builder /app/backend/lecturelens/static ./backend/lecturelens/static

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps -e .

EXPOSE 8000
CMD ["sh", "-c", "lecturelens serve --host 0.0.0.0 --port ${PORT:-8000}"]
