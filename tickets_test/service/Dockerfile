FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       poppler-utils tesseract-ocr tesseract-ocr-spa \
       fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY tickets_test/service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY tickets_test/service/service /app/service
COPY tickets_test/service/tests /app/tests
COPY jarvis/tickets /app/jarvis/tickets

CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
