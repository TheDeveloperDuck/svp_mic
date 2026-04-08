# =============================================================================
# Stage 1 — builder
# Compile all Python dependencies into wheels.  No source code here.
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

COPY planning_service/requirements.txt .

RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt


# =============================================================================
# Stage 2 — runtime
# Install from pre-built wheels and copy only the application source.
# =============================================================================
FROM python:3.12-slim AS runtime

# Create a non-root user and group.
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --no-create-home appuser

WORKDIR /app

ENV PYTHONPATH=/app

# Install wheels built in the builder stage — no internet access required.
COPY --from=builder /app/wheels /app/wheels
RUN pip install --no-cache-dir --no-index --find-links /app/wheels /app/wheels/*.whl

# Copy application source.
COPY shared/ /app/shared/
COPY planning_service/ /app/planning_service/

# Drop privileges before starting the process.
USER appuser

EXPOSE 8000

CMD alembic -c planning_service/alembic.ini upgrade head && uvicorn planning_service.main:app --host 0.0.0.0 --port 8000
