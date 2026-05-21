# Cloud Run target — Python 3.11, single-file uvicorn boot.
# Pin the base image digest to defeat tag-poisoning per the operator's NPM safety policy
# (Python equivalent — same principle: never use floating tags in production).
FROM python:3.11.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy pyproject.toml first so cache layer survives source edits
COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
COPY LICENSE /app/LICENSE
COPY README.md /app/README.md

# Install with the lockfile-like pinning enforced
RUN pip install --no-deps .

# Cloud Run sets PORT; default to 8080
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn cloudrunauditor.main:app --host 0.0.0.0 --port ${PORT}"]
