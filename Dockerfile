FROM python:3.12-slim

# Don't write .pyc files; flush stdout immediately for stdio MCP transport.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Run as a non-root user. Writing files into /app at runtime isn't needed.
RUN useradd --create-home --shell /bin/bash --uid 1001 opencollab \
    && chown -R opencollab:opencollab /app
USER opencollab

# Default to streamable-http for container deployments. Override with
# `-e TRANSPORT=stdio` for a stdio-mode container if you really want it.
ENV TRANSPORT=streamable-http \
    PORT=8000 \
    OPENCOLLAB_LOG_LEVEL=INFO

# GITHUB_TOKEN is intentionally NOT baked in. Pass it at runtime:
#   docker run -e GITHUB_TOKEN=ghp_xxx -p 8000:8000 opencollab-mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; \
urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=3)" \
    || exit 1

ENTRYPOINT ["opencollab-mcp"]
