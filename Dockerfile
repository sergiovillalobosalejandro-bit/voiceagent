FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    HF_HUB_DISABLE_SSL_VERIFY=1

# PyTorch CPU primero (~200 MB) para evitar descargar CUDA (~1.5 GB) en Render
COPY backend/requirements.txt .
RUN pip install --no-cache-dir "torch==2.5.1" --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Precarga del modelo de embeddings en build (evita timeout en primer request)
RUN python -c "from embeddings import get_encoder; get_encoder()"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
