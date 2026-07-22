# EPM Wizard backend — local FastAPI service (Python 3.12).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    EPMW_DATA_DIR=/data

# Install OpenJDK 21 for EPM Automate (EPM Automate works with Java 11+)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cached layer). Copies pyproject so the deps
# resolve; the package itself is imported from the working directory at runtime.
COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/README.md /app/README.md
COPY backend/app /app/app
# The hosted image always ships the PostgreSQL driver so EPMW_DATABASE_URL can
# point at a hosted PostgreSQL; SQLite stays the default.
RUN pip install ".[postgres]"

# Application source (migrations, fixtures, scripts).
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY backend/fixtures /app/fixtures
COPY backend/scripts /app/scripts
# Generated JSON schema is served by /api/schema; ship a copy.
COPY frontend/src/schemas/schemas.json /frontend/src/schemas/schemas.json

RUN mkdir -p /data
EXPOSE 8000

# Migrations + seeding run on startup (app lifespan).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
