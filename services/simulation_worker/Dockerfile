FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/simulation_worker/requirements.lock.txt /tmp/requirements.txt
RUN pip install \
    --no-cache-dir \
    -r /tmp/requirements.txt

COPY packages/__init__.py ./packages/__init__.py
COPY packages/contracts ./packages/contracts
COPY packages/common ./packages/common
COPY packages/simulation_core ./packages/simulation_core

COPY services/__init__.py ./services/__init__.py
COPY services/simulation_worker ./services/simulation_worker

COPY data/networks ./data/networks

RUN mkdir -p /app/data/runtime/custom_models \
    && useradd \
       --create-home \
       --uid 10001 \
       appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV WORKER_HOST=0.0.0.0
ENV WORKER_PORT=8100

EXPOSE 8100

HEALTHCHECK \
  --interval=30s \
  --timeout=5s \
  --start-period=20s \
  --retries=3 \
  CMD python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/internal/health')"

CMD ["python", "-m", "uvicorn", "services.simulation_worker.main:app", "--host", "0.0.0.0", "--port", "8100"]