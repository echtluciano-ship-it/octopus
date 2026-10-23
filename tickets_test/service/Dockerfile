FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN --mount=type=secret,id=host_ca,required=false \
    if [ -s /run/secrets/host_ca ]; then \
      cp /run/secrets/host_ca /usr/local/share/ca-certificates/octopus-host-proxy.crt; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates poppler-utils tesseract-ocr tesseract-ocr-spa \
       fonts-dejavu-core \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY tickets_test/service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY tickets_test/service/service /app/service
COPY tickets_test/service/tests /app/tests
COPY jarvis/tickets /app/jarvis/tickets

CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
