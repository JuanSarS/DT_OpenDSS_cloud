FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt

RUN pip install \
    --no-cache-dir \
    -r requirements.txt

COPY packages ./packages
COPY services ./services
COPY data ./data

RUN mkdir -p \
    /app/data/runtime/custom_models

ENV WORKER_HOST=0.0.0.0
ENV WORKER_PORT=8100
ENV CUSTOM_MODELS_DIR=/app/data/runtime/custom_models

EXPOSE 8100

CMD ["python","-m", "uvicorn","services.simulation_worker.main:app", "--host", "0.0.0.0", "--port","8100"]