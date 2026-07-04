# Vahini PP-OCRv5 recognition service
# Build:  docker build -t vahini-ocr ./server
# Run:    docker run -p 8080:8080 vahini-ocr
# First request per language downloads PP-OCRv5 weights into the image's cache.
FROM python:3.11-slim

ARG VAHINI_OCR_PRELOAD_LANGS=en,te

# PaddleOCR needs a few native libs for image decoding / OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ppocr-server.py .
COPY warmup_models.py .

ENV PADDLE_PDX_CACHE_HOME=/opt/paddle-models
RUN mkdir -p /opt/paddle-models
RUN VAHINI_OCR_PRELOAD_LANGS=${VAHINI_OCR_PRELOAD_LANGS} python warmup_models.py

ENV PORT=8080
EXPOSE 8080
CMD ["python", "ppocr-server.py"]
