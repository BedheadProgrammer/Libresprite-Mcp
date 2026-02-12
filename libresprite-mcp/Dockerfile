# Use a lightweight Python base
FROM python:3.11-slim-bookworm

# 1. Install System Dependencies (X11 + Build tools + libraries for LibreSprite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xvfb \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libgif7 \
    libfreetype6 \
    libfontconfig1 \
    libjpeg62-turbo \
    libpng16-16 \
    libtiff6 \
    libwebp7 \
    libx11-6 \
    libxcursor1 \
    libxi6 \
    zlib1g \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Install LibreSprite via AppImage (extracted for Docker compatibility)
#    AppImages require FUSE to self-mount, which is unavailable in most
#    Docker containers. Extracting the AppImage avoids this issue entirely.
WORKDIR /app/bin
RUN wget -q https://github.com/LibreSprite/LibreSprite/releases/download/continuous/LibreSprite-x86_64.AppImage \
    && chmod +x LibreSprite-x86_64.AppImage \
    && ./LibreSprite-x86_64.AppImage --appimage-extract \
    && mv squashfs-root libresprite \
    && rm LibreSprite-x86_64.AppImage \
    && ln -s /app/bin/libresprite/AppRun /usr/local/bin/libresprite

# 3. Install Python MCP SDK (with CLI extras for FastMCP transport support)
RUN pip install --no-cache-dir "mcp[cli]"

# 4. Setup Working Directory and output directory
WORKDIR /app
RUN mkdir -p /app/output
COPY server.py .
COPY resources/ resources/

# 5. Create a non-root user (Security Best Practice)
RUN useradd -m spriteuser \
    && chown -R spriteuser:spriteuser /app

USER spriteuser

# 6. Env vars to force headless execution and docker mode
ENV DISPLAY=:99
ENV LIBRESPRITE_MODE=docker

# 7. Start command: Run Xvfb in background, then the Python Server
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset & while ! test -e /tmp/.X99-lock; do sleep 0.1; done && python server.py"]
