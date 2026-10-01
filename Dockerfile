FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RGC_ENV=production \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-documents.txt ./
RUN pip install --no-cache-dir -r requirements-documents.txt

COPY config.py main.py ./
COPY crawler ./crawler
COPY processors ./processors
COPY service ./service
COPY openapi.yaml ./openapi.yaml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["sh", "-c", "uvicorn service.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
