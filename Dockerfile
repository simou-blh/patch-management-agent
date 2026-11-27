FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENT_DATA_DIR=/data \
    NOYAU_URL=http://host.docker.internal:8000

WORKDIR /app

COPY requirements-agent.txt .
RUN pip install --no-cache-dir -r requirements-agent.txt

COPY agent ./agent
COPY patch_agent ./patch_agent
COPY schemas ./schemas
COPY policies ./policies
COPY lab ./lab
COPY agent.manifest.json .

RUN useradd --create-home agent \
    && mkdir -p /data \
    && chown -R agent:agent /data /app

USER agent

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health', timeout=5)"

CMD ["uvicorn", "agent.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "9000"]
