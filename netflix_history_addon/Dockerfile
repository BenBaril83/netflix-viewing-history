# Playwright's image already contains Chromium and its system libraries.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc novnc \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "playwright==1.48.0" "beautifulsoup4>=4.12" "aiohttp>=3.9"

WORKDIR /app
COPY netflix_history /app/netflix_history
COPY run.sh /run.sh
RUN chmod +x /run.sh

ENV DISPLAY=:99
CMD ["/run.sh"]
