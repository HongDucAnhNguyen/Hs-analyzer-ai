FROM python:3.11-slim

# Install system dependencies for Chrome, headless browsing, and cron
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    dbus \
    dbus-x11 \
    libnss3 \
    libfontconfig1 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libgdk-pixbuf-2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxshmfence1 \
    libgbm1 \
    libgl1-mesa-dri \
    libgl1 \
    libegl1 \
    libxss1 \
    ca-certificates \
    fonts-liberation \
    procps \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y /tmp/google-chrome.deb \
    && rm /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8080 \
    API_WORKERS=4 \
    DISPLAY=:99

WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using uv (without lock file for flexibility)
RUN uv sync --no-dev || uv pip install --system -e .
# Ensure xlsb support is present for report worker
RUN uv pip install --system pyxlsb

# Copy service directories
COPY rag_service /app/rag_service
COPY classifier_service /app/classifier_service
COPY crawl_service /app/crawl_service
COPY hs_analyzer_service /app/hs_analyzer_service
COPY report_service /app/report_service
COPY shared /app/shared
COPY auth /app/auth

# Copy main.py
COPY main.py /app/
COPY logging_config.py /app/

# Create profiles directory for browser profiles
RUN mkdir -p /app/profiles /app/logs

# Expose port
EXPOSE 8080

# Create wrapper script for password rotation (loads env vars for cron)
RUN echo '#!/bin/bash\n\
    # Load environment variables from .env file\n\
    if [ -f /app/.env ]; then\n\
    set -a\n\
    source /app/.env\n\
    set +a\n\
    fi\n\
    \n\
    # Run password rotation\n\
    cd /app && /usr/local/bin/uv run python auth/password_rotation.py\n\
    ' > /app/run_password_rotation.sh && chmod +x /app/run_password_rotation.sh

# Create crontab file for password rotation
# Schedule: Every Sunday at 11:00 UTC (= 18:00 Vietnam Time UTC+7)
RUN echo '# Password Rotation Cron Job\n\
    # Runs every Sunday at 11:00 UTC (18:00 Vietnam Time)\n\
    0 11 * * 0 /app/run_password_rotation.sh >> /app/logs/password_rotation.log 2>&1\n\
    ' > /etc/cron.d/password-rotation \
    && chmod 0644 /etc/cron.d/password-rotation \
    && crontab /etc/cron.d/password-rotation

# Create startup script with Xvfb, dbus, cron for Chrome/Zendriver
RUN echo '#!/bin/bash\n\
    set -e\n\
    \n\
    echo "=== Starting services for headless Chrome ==="\n\
    \n\
    # Start cron daemon for scheduled tasks\n\
    echo "Starting cron daemon..."\n\
    service cron start\n\
    if service cron status > /dev/null 2>&1; then\n\
    echo "✓ Cron daemon started successfully"\n\
    echo "  Password rotation scheduled: Every Sunday at 11:00 UTC (18:00 Vietnam)"\n\
    else\n\
    echo "✗ Cron daemon failed to start"\n\
    fi\n\
    \n\
    # Start dbus (reduces error messages)\n\
    echo "Starting dbus..."\n\
    mkdir -p /run/dbus\n\
    dbus-daemon --system --fork 2>/dev/null || true\n\
    \n\
    # Start Xvfb virtual display\n\
    echo "Starting Xvfb on display :99..."\n\
    Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &\n\
    XVFB_PID=$!\n\
    sleep 2\n\
    \n\
    # Verify Xvfb is running\n\
    if ps -p $XVFB_PID > /dev/null; then\n\
    echo "✓ Xvfb started successfully (PID: $XVFB_PID)"\n\
    else\n\
    echo "✗ Xvfb failed to start"\n\
    fi\n\
    \n\
    # Set Chrome environment for Docker\n\
    export DISPLAY=:99\n\
    export CHROME_FLAGS="--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer"\n\
    \n\
    # Verify Chrome\n\
    echo "Chrome version: $(google-chrome --version 2>/dev/null || echo "not found")"\n\
    \n\
    # Quick Chrome test\n\
    echo "Testing Chrome headless..."\n\
    timeout 10 google-chrome --headless --no-sandbox --disable-gpu --disable-dev-shm-usage --dump-dom about:blank > /dev/null 2>&1 && echo "✓ Chrome headless OK" || echo "✗ Chrome headless test failed (non-critical)"\n\
    \n\
    echo "=== Starting Unified API ==="\n\
    exec uv run uvicorn main:app --host ${API_HOST} --port ${API_PORT} --workers ${API_WORKERS}\n\
    ' > /app/start.sh && chmod +x /app/start.sh

# Run the startup script
CMD ["/app/start.sh"]