FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PKG_DATA_DIR=/data \
    PKG_HOST=0.0.0.0

WORKDIR /app

COPY services/query_api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown app:app /data

COPY services /app/services

USER app
EXPOSE 8000

CMD ["python", "-m", "services.query_api"]
