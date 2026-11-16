FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY services/simulation_worker/requirements.lock.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY packages ./packages
COPY data/networks ./data/networks
COPY tools/evidence ./tools/evidence

RUN useradd --create-home --uid 10001 evidence \
    && mkdir -p /evidence \
    && chown -R evidence:evidence /app /evidence
USER evidence

ENTRYPOINT ["python", "-m", "tools.evidence.deliverable1_multicontext"]
