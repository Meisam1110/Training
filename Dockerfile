# One image serves /api/* and the built SPA at /.  Everything is fetched at BUILD time; the
# runtime stage installs nothing and downloads nothing (air-gapped installs receive the image).
#
#   docker build -t tms:latest .

# --- stage 1: the frontend ---------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- stage 2: python wheels (so the runtime stage needs no compiler / network) ---
FROM python:3.12-slim AS wheels
WORKDIR /w
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[postgres]"

# --- stage 3: runtime ---------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 \
    TMS_ENV=production TMS_STATIC_ROOT=/app/static TMS_STORAGE_DIR=/data \
    TMS_TEMPLATES_DIR=/app/templates
WORKDIR /app
COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels tms-backend[postgres] && rm -rf /wheels
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY templates/ ./templates/
COPY --from=frontend /build/dist/ ./static/

# Not root, and the code is read-only to the process that runs it. /data is the only writable path.
RUN useradd --system --uid 10001 --home /app tms && mkdir -p /data && chown tms:tms /data
USER tms
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

# The schema is NOT migrated on start (a race between replicas): run `alembic upgrade head` explicitly
# (compose does it in the one-shot `migrate` service). SIGTERM => graceful shutdown within 20 s.
# --no-proxy-headers: the app resolves the client address itself from X-Forwarded-For, trusting ONLY TMS_TRUSTED_PROXIES
# (default: loopback + the docker bridge range) -- see docs/DEPLOYMENT.md. --no-server-header hides the uvicorn banner.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--timeout-graceful-shutdown", "20", \
     "--no-proxy-headers", "--no-server-header"]
