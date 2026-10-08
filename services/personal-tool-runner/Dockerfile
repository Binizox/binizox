FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 binizox \
    && mkdir -p /data /workspace \
    && chown -R binizox:binizox /data /workspace

USER binizox

ENV BINIZOX_WORKSPACE_ROOT=/workspace
ENV BINIZOX_TOOL_STATE_PATH=/data/tool-runner.sqlite3

EXPOSE 8091

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
