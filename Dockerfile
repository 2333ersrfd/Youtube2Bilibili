# Multi-purpose Dockerfile for running the auto runner or the API server
# Default runs the auto-runner. Set APP_MODE=server to run api_server.py

FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Basic OS deps; ffmpeg is useful for media handling (biliup/yt-dlp)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl ffmpeg wget nano xz-utils\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first to leverage Docker layer cache
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir yt-dlp

# Install biliup
RUN wget "https://github.com/biliup/biliup-rs/releases/download/v0.2.4/biliupR-v0.2.4-x86_64-linux-musl.tar.xz" -O biliup.tar.xz && \
    tar -xf biliup.tar.xz && \
    rm biliup.tar.xz && \
    chmod +x biliupR-v0.2.4-x86_64-linux-musl/biliup && \
    mv biliupR-v0.2.4-x86_64-linux-musl/biliup /usr/local/bin/ && \
    rm -rf biliupR-v0.2.4-x86_64-linux-musl

# Copy project files
COPY . .

# Simple entrypoint wrapper
RUN printf '#!/bin/sh\nset -e\necho "Starting Youtube2Bilibili auto runner..."\n  exec python scripts/auto_runner.py\n' > /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
