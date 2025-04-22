# worker/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for uploads and output
RUN mkdir -p storage/uploads storage/output

# Set permissions
RUN chmod -R 777 storage

# Copy the application code
COPY . .

# Run the worker
CMD ["python", "worker.py"]