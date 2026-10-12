# Playwright's image already contains Chromium and its system libraries.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Non-interactive: tzdata (pulled in by the X/VNC packages) otherwise blocks forever on a time zone prompt.
ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Etc/UTC
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc novnc curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "playwright==1.48.0" "beautifulsoup4>=4.12" "aiohttp>=3.9"

# Optional scrape engine: Obscura (third-party headless browser, Apache-2.0). Pinned release;
# upstream publishes no checksums, so these hashes were taken from the v0.2.4 downloads (trust on first use).
ARG OBSCURA_VERSION=v0.2.4
ARG OBSCURA_SHA256_X86_64=757e7b597ba5cdd53af9fc701e0a9b80f0a8d788f545d4f82ec9ad32db77f000
ARG OBSCURA_SHA256_AARCH64=d9ba3719c2442a227567d7664b5505b38ab68236f3f5388884eee2e27f55db28
RUN set -e; arch="$(uname -m)"; \
    case "$arch" in x86_64) sha="$OBSCURA_SHA256_X86_64";; aarch64) sha="$OBSCURA_SHA256_AARCH64";; *) echo "unsupported arch $arch"; exit 1;; esac; \
    curl -fsSL -o /tmp/obscura.tgz "https://github.com/h4ckf0r0day/obscura/releases/download/${OBSCURA_VERSION}/obscura-${arch}-linux.tar.gz"; \
    echo "${sha}  /tmp/obscura.tgz" | sha256sum -c -; \
    tar xzf /tmp/obscura.tgz -C /usr/local/bin obscura obscura-worker; rm /tmp/obscura.tgz

WORKDIR /app
COPY netflix_history /app/netflix_history
COPY run.sh /run.sh
RUN chmod +x /run.sh

ENV DISPLAY=:99
CMD ["/run.sh"]
