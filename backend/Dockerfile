FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (ffmpeg for video, espeak-ng for kokoro TTS)
RUN apt-get update && \
    apt-get install -y ffmpeg espeak-ng curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
