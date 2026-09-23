FROM python:3.11-slim

WORKDIR /app

# System dependencies needed by some PDF/DOCX parsing libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY start.sh .
RUN chmod +x start.sh

ENV CHROMA_DIR=/app/chroma_db
ENV BACKEND_URL=http://localhost:8000

# 7860 is the port Hugging Face Docker Spaces expects; 8000 is the internal API
EXPOSE 7860
EXPOSE 8000

CMD ["./start.sh"]
