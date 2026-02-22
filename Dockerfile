FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1  

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download models during BUILD (not runtime)
# This means models are baked into the image — no downloading on startup
RUN python -c "from transformers import pipeline; pipeline('text-classification', model='distilbert-base-uncased-finetuned-sst-2-english')"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8000