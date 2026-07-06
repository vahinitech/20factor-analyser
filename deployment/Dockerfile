# Combined Vahini analyser + OCR service. Build context is the repo root
# (docker-compose.yml's `context: .`), since this image needs both
# frontend/ (static app/pages) and backend/ (the FastAPI service).
# - Serves /analyser static app/pages
# - Runs PP-OCRv5 API on /ocr

FROM python:3.11-slim

ARG VAHINI_OCR_PRELOAD_LANGS=

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Copy ALL requirement tiers (requirements.txt references the core/paddle tiers
# via -r, so they must be present before install). Default image = core+paddle;
# add trocr/surya tiers by extending this build if you need them (both are
# needed for hybrid mode).
COPY backend/requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- Optional handwriting engines (baked in via build args) ------------------
# TrOCR  : English-handwriting refiner (CPU torch). Default ON in compose.
# Surya  : multilingual/Indic VLM; needs a llama.cpp `llama-server` backend,
#          which we build from source. Heavy + slow on CPU, default OFF.
ARG VAHINI_WITH_TROCR=0
ARG VAHINI_WITH_SURYA=0

# CPU torch (shared by both engines), small CPU wheel, no CUDA.
RUN if [ "$VAHINI_WITH_TROCR" = "1" ] || [ "$VAHINI_WITH_SURYA" = "1" ]; then \
        pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu ; \
    fi

# TrOCR deps + pre-download the handwriting model so the first request is
# fast. requirements-trocr.txt pins transformers>=5.3.0 (a critical RCE
# affects every earlier version); it is NOT confirmed whether 5.3.0+ still
# has the "Couldn't instantiate the backend tokenizer" issue seen at 5.13.0
# (microsoft/trocr-base-handwritten's Hub repo only ships a legacy tokenizer
# format). This warm-up is best-effort, not a build gate: if it fails, the
# model lazy-loads on first request instead (same graceful "not ready" path
# as torch/transformers being absent entirely), one optional engine's model
# download must never block the whole image build.
RUN if [ "$VAHINI_WITH_TROCR" = "1" ]; then \
        pip install --no-cache-dir -r requirements-trocr.txt && \
        (python -c "from transformers import TrOCRProcessor, VisionEncoderDecoderModel; m='microsoft/trocr-base-handwritten'; TrOCRProcessor.from_pretrained(m); VisionEncoderDecoderModel.from_pretrained(m)" \
            || echo "[build] trocr pre-download failed -- will lazy-load on first request instead") ; \
    fi

# Surya deps + a source-built llama-server (its required CPU inference backend).
ENV LLAMA_CPP_BINARY=/usr/local/bin/llama-server
RUN if [ "$VAHINI_WITH_SURYA" = "1" ]; then \
        pip install --no-cache-dir -r requirements-surya.txt && \
        apt-get update && apt-get install -y --no-install-recommends build-essential cmake git && \
        git clone --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama.cpp && \
        cmake -S /tmp/llama.cpp -B /tmp/llama.cpp/build -DLLAMA_CURL=OFF -DGGML_NATIVE=OFF && \
        cmake --build /tmp/llama.cpp/build --target llama-server -j 2 && \
        cp /tmp/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server && \
        rm -rf /tmp/llama.cpp && \
        apt-get purge -y build-essential cmake git && apt-get autoremove -y && \
        rm -rf /var/lib/apt/lists/* && \
        python -c "from surya.detection import DetectionPredictor; DetectionPredictor()" ; \
    fi

COPY backend /app/backend
COPY frontend /app/frontend

ENV PADDLE_PDX_CACHE_HOME=/opt/paddle-models
ENV PADDLEOCR_HOME=/opt/paddle-models/.paddleocr
RUN mkdir -p /opt/paddle-models/.paddleocr /root \
 && rm -rf /root/.paddleocr \
 && ln -s /opt/paddle-models/.paddleocr /root/.paddleocr
RUN if [ -n "${VAHINI_OCR_PRELOAD_LANGS}" ]; then \
            VAHINI_OCR_PRELOAD_LANGS=${VAHINI_OCR_PRELOAD_LANGS} python /app/backend/warmup_models.py; \
        fi

ENV PORT=8080
EXPOSE 8080

CMD ["python", "/app/backend/analyser-ocr-server.py"]
