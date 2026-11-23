# MLflow tracking server for LLM traces, evaluations and feedback (WP5).
# OTLP trace ingestion needs MLflow >= 3.6 and a SQL backend store.
FROM python:3.12-slim

RUN pip install --no-cache-dir "mlflow==3.17.2" "psycopg[binary]>=3.2,<4"

# Runs under any UID (OpenShift assigns a random one in group 0).
RUN mkdir -p /mlartifacts /home/mlflow /routes && chown 1001:0 /routes \
    && chgrp -R 0 /mlartifacts /home/mlflow /routes && chmod -R g=u /mlartifacts /home/mlflow /routes
COPY setup_experiments.py /opt/setup_experiments.py
ENV HOME=/home/mlflow
USER 1001

EXPOSE 5000
