FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && useradd --create-home --uid 10001 appuser

COPY app ./app
COPY static ./static

USER appuser
EXPOSE 8080

# Cloud Run sets $PORT and terminates TLS in front of the container.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
