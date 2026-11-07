# Single-container image for Hugging Face Spaces: builds the React app, then serves it and the API from one uvicorn on port 7860.
# Build context is the repository root (deploy/huggingface/push.sh places this file at the Space root).

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Empty = same origin: the API is served by the same server.
ENV VITE_BACKEND_URL=
RUN npm run build

FROM python:3.12-slim
# LightGBM's native library links against OpenMP, which the slim image does not ship.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
# Spaces run the container as uid 1000; give it a home and own the app dir so SQLite and model caches are writable.
RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/requirements.txt .
# CPU-only xgboost: the default Linux wheel pulls ~300 MB of NVIDIA libraries that this app never uses.
RUN sed -i 's/^xgboost$/xgboost-cpu/' requirements.txt && pip install --no-cache-dir -r requirements.txt
COPY --chown=user backend/ ./
COPY --chown=user --from=web /web/dist ./static
USER user
ENV HOME=/home/user STATIC_DIR=/app/static PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
