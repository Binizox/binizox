FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY app ./app

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 1000 binizox \
    && mkdir -p /data /app/user-data \
    && chown -R binizox:binizox /data /app/user-data

USER binizox

ENV BINIZOX_WORKSPACE_ROOT=/app/user-data
ENV BINIZOX_TOOL_STATE_PATH=/data/tool-runner.sqlite3

EXPOSE 8091

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
