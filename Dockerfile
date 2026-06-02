# reconcile API service image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install deps first for layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000

# Apply migrations (no-op on SQLite first run is fine) then serve.
CMD ["sh", "-c", "alembic upgrade head || true; uvicorn reconcile.api.app:app --host 0.0.0.0 --port 8000"]
