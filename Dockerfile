# One image for all three services. Which one runs is chosen at start-up by
# SERVICE=api|optimizer|simulation, so the monolith and the microservice
# deployment use byte-for-byte the same code (a fair Experiment A).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE=api \
    MODE=monolith \
    PORT=8000 \
    WORKERS=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 10 --timeout 60 -r requirements.txt

COPY scm_core ./scm_core
COPY services ./services

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# WORKERS stays 1 by default: on Container Apps we scale by adding replicas,
# so one process per replica keeps "replicas" and "capacity" the same thing.
CMD ["sh", "-c", "uvicorn services.${SERVICE}.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS}"]