FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Run as non-root for safety
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Default to stdio. Override with TRANSPORT=streamable-http for remote.
ENV TRANSPORT=stdio \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "opencollab_mcp"]
