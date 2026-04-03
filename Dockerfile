FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

ENV GITHUB_TOKEN=""

ENTRYPOINT ["opencollab-mcp"]
