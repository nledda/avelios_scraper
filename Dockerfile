FROM python:3.12-slim

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Tell Selenium to use the system Chromium instead of downloading one
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV HEADLESS=True

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user and runtime directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p output/linkedin output/network \
    data/linkedin data/state data/stats \
    logs && \
    chown -R appuser:appuser /app

USER appuser

# Default: run the scheduler
CMD ["bash", "auto_scraper.sh", "_loop"]
