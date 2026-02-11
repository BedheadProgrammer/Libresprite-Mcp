# Containerized LibreSprite MCP Server — Implementation Plan

This architecture solves the security risk by isolating the execution environment. The LLM sends instructions to a Python server, which writes a Lua script and executes it inside a disposable Docker container running LibreSprite headless (using Xvfb).

---

## 1. The Architecture

- **Host Machine:** Runs the MCP Client (e.g., Claude Desktop, Cursor).
- **Docker Container:**
  - **OS:** Debian Bookworm (Slim)
  - **Display:** Xvfb (Virtual Framebuffer) — Critical, as LibreSprite is a GUI app and needs a "fake" screen to launch.
  - **App:** LibreSprite (compiled or installed via flatpak/appimage).
  - **Server:** A Python script using `mcp` library (FastMCP) to listen for requests.
  - **Storage:** A bind-mounted `./output` folder to save the generated sprites.

---

## 2. Implementation Files

Create a folder named `libresprite-mcp` and add these three files.

### A. `Dockerfile`

This image sets up the "sandbox." It installs the necessary X11 dependencies to trick LibreSprite into thinking it has a monitor.

```dockerfile
# Use a lightweight Python base
FROM python:3.11-slim-bookworm

# 1. Install System Dependencies (X11 + Build tools)
RUN apt-get update && apt-get install -y \
    wget \
    xvfb \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    lua5.1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Install LibreSprite (Using AppImage for ease, or compile from source for smaller image)
# Note: In a production build, you should compile from source to remove AppImage overhead.
WORKDIR /app/bin
RUN wget https://github.com/LibreSprite/LibreSprite/releases/download/continuous/LibreSprite-x86_64.AppImage \
    && chmod +x LibreSprite-x86_64.AppImage

# 3. Install Python MCP SDK
RUN pip install mcp

# 4. Setup Working Directory
WORKDIR /app
COPY server.py .

# 5. Create a non-root user (Security Best Practice)
RUN useradd -m spriteuser
RUN chown -R spriteuser:spriteuser /app
USER spriteuser

# 6. Env vars to force headless execution
ENV DISPLAY=:99

# 7. Start command: Run Xvfb in background, then the Python Server
CMD Xvfb :99 -screen 0 1024x768x24 & python server.py
```

---

### B. `server.py` (The MCP Logic)

This script receives the prompt, creates a temporary Lua script, and fires it into LibreSprite.

```python
from mcp.server.fastmcp import FastMCP
import subprocess
import os
import uuid

# Initialize the MCP Server
mcp = FastMCP("LibreSprite Container")

@mcp.tool()
def generate_sprite(lua_code: str) -> str:
    """
    Generates a sprite by executing Lua code in LibreSprite.

    Args:
        lua_code: valid Lua script for LibreSprite/Aseprite API.
                  Example:
                  local sprite = Sprite(32, 32)
                  app.command.Clear()
                  sprite:saveCopyAs("/app/output/result.png")
    """

    # 1. Create a unique filename for the script
    script_id = str(uuid.uuid4())
    script_path = f"/tmp/{script_id}.lua"

    # 2. Security Check: Enforce output path
    # We inject code to ensure it ONLY saves to the mounted volume
    safe_lua = f"""
    -- FORCED SECURITY HEADER
    local safe_path = "/app/output/{script_id}.png"

    -- USER CODE START
    {lua_code}
    -- USER CODE END

    -- FORCED SAVE (If user didn't save, we try to save the active sprite)
    if app.activeSprite then
        app.activeSprite:saveCopyAs(safe_path)
    end
    """

    # 3. Write the script to the container's temp dir
    with open(script_path, "w") as f:
        f.write(safe_lua)

    # 4. Execute LibreSprite Headless
    # We use the AppImage we downloaded in Dockerfile
    cmd = [
        "/app/bin/LibreSprite-x86_64.AppImage",
        "--batch",     # Run without UI
        "--script",    # Execute script
        script_path
    ]

    try:
        # Run process with timeout to prevent infinite loops
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            return f"Success! Sprite generated at: output/{script_id}.png"
        else:
            return f"Error executing script:\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return "Error: Script execution timed out."
    finally:
        # Cleanup
        if os.path.exists(script_path):
            os.remove(script_path)

if __name__ == "__main__":
    mcp.run()
```

---

### C. `docker-compose.yml` (The Runner)

This makes it easy to spin up and bind the output folder.

```yaml
services:
  libresprite-mcp:
    build: .
    # Mount the local 'output' folder to the container's output folder
    volumes:
      - ./output:/app/output
    # MCP usually communicates over Stdio, but for Docker we might need
    # to use SSE (Server-Sent Events) over HTTP if connecting remotely.
    # For local Stdio usage via 'docker run', we use the command below.
    stdin_open: true
    tty: true
```

---

## 3. How to Connect (The "Tricky" Part)

Connecting an MCP client (like Claude Desktop) to a Docker container via Stdio is slightly complex because Docker wraps the input/output.

### The Command to put in your MCP Config

You need to tell your MCP client to run `docker` instead of `python`.

```json
{
  "mcpServers": {
    "libresprite": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-v", "/absolute/path/to/your/output:/app/output",
        "libresprite-mcp"
      ]
    }
  }
}
```

> - `--rm` — Delete container after use
> - `-i` — Interactive (Keep Stdin open)
> - `-v` — Bind Mount for the output directory

---

## 4. Verification & Testing

1. **Build:** `docker build -t libresprite-mcp .`
2. **Create Output Dir:** `mkdir output`
3. **Test Run:**

```bash
# This should start the server and wait for MCP JSON-RPC messages
docker run --rm -i -v $(pwd)/output:/app/output libresprite-mcp
```

### Security Validation

- Ask the LLM to write a file to `/root/`.
- It will fail (**Permission Denied**) or write to the ephemeral container which disappears immediately.
- Your host OS remains untouched.

---

## Why this video is relevant

This video covers the specific challenges and solutions for running graphical applications (like LibreSprite) inside Docker containers, which is the exact technical hurdle you will face when implementing the Xvfb portion of the Dockerfile.

🎥 [Running GUI apps in Docker](https://www.youtube.com/results?search_query=running+gui+apps+in+docker)