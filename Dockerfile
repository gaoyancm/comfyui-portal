FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production

WORKDIR /app

# Install build deps only if needed
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copy portal code
COPY . /app/

WORKDIR /app
RUN pip install --upgrade pip && \
    pip install -r comfyui-portal/requirements.txt

# Expose port
EXPOSE 5000

# Default envs (override in runtime or compose)
ENV COMFY_URL=http://127.0.0.1:8188 \
    UPLOAD_DIR=uploads \
    RESULTS_DIR=results

# Run with gunicorn; chdir into comfyui-portal so module 'app' resolves
WORKDIR /app/comfyui-portal
CMD ["gunicorn","-b","0.0.0.0:5000","app:app","--workers","2","--timeout","120"]

