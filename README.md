# LibreSprite MCP Server

An MCP (Model Context Protocol) server that lets an AI assistant generate pixel-art sprites by driving [LibreSprite](https://github.com/LibreSprite/LibreSprite) inside a sandboxed Docker container.

**Flow:** User prompt → AI writes Lua script → MCP server executes it in LibreSprite → sprite saved to `output/`

---

## Critique of the Original Plan

The original `IMPLEMENTATION_PLAN.md` had several issues that are fixed in this implementation:

| # | Issue | Severity | Fix Applied |
|---|-------|----------|-------------|
| 1 | **Lua code injection** – user-supplied Lua was interpolated directly into a script with no sanitization. The "security header" only set a variable that user code could trivially overwrite, and dangerous functions like `os.execute()`, `io.popen()` remained available. | **Critical** | Added regex-based pre-validation AND runtime sandbox that nils out dangerous globals (`os.execute`, `io.open`, `require`, `debug`, etc.) before user code runs. |
| 2 | **AppImage requires FUSE** – Docker containers do not provide FUSE by default. Running the AppImage directly would fail with a cryptic error. | **High** | The Dockerfile now extracts the AppImage with `--appimage-extract` and symlinks the resulting `AppRun` binary. |
| 3 | **Missing `mcp[cli]` extras** – `pip install mcp` does not install the CLI/transport extras needed by `FastMCP.run(transport="stdio")`. | **Medium** | Changed to `pip install "mcp[cli]"`. |
| 4 | **No explicit transport** – `mcp.run()` without arguments may default to the wrong transport. | **Medium** | Server now calls `mcp.run(transport="stdio")`. |
| 5 | **Missing output directory** – Dockerfile never created `/app/output`; the bind-mount would shadow it anyway, but without a mount the server would crash. | **Low** | Added `mkdir -p /app/output` in Dockerfile. |
| 6 | **No input validation** – Empty `lua_code` would produce an empty script and a confusing LibreSprite error. | **Low** | Added empty-input check. |
| 7 | **Single tool only** – The original plan only exposed `generate_sprite`. | **Low** | Added `list_sprites` (list output files) and `create_pixel_art` (text-based pixel map convenience tool). |
| 8 | **No `.dockerignore` / `.gitignore`** – Build context would include unnecessary files; generated sprites would be committed. | **Low** | Added both files. |
| 9 | **Bare `CMD` string** – `CMD Xvfb ... & python server.py` uses shell form which doesn't handle signals correctly. | **Low** | Changed to exec form with explicit `sh -c` and added a `sleep 1` to let Xvfb initialize. |
| 10 | **Missing system libraries** – LibreSprite depends on several image/font libraries not listed in the original Dockerfile. | **Medium** | Added `libgif7`, `libfreetype6`, `libfontconfig1`, `libjpeg62-turbo`, `libpng16-16`, `libtiff6`, `libwebp7`, and X11 libraries. |

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (and Docker Compose)
- An MCP-compatible client (e.g., Claude Desktop, Cursor)

### Build

```bash
cd libresprite-mcp
docker build -t libresprite-mcp .
```

### Run (standalone test)

```bash
mkdir -p output
docker run --rm -i -v "$(pwd)/output:/app/output" libresprite-mcp
```

The server starts and waits for MCP JSON-RPC messages on stdin/stdout.

### Connect to an MCP Client

Add this to your MCP client configuration (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "libresprite": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/absolute/path/to/output:/app/output",
        "libresprite-mcp"
      ]
    }
  }
}
```

### Using Docker Compose

```bash
cd libresprite-mcp
docker compose up --build
```

---

## Available Tools

### `generate_sprite(lua_code: str) -> str`

Execute arbitrary (sandboxed) Lua code inside LibreSprite. The script runs in headless batch mode. Dangerous Lua functions are disabled.

### `list_sprites() -> str`

List all sprite files that have been generated in the output directory.

### `create_pixel_art(width, height, pixel_data, palette?) -> str`

Convenience tool to create sprites from a simple text-based pixel map without writing Lua. Example:

```
width: 3, height: 3
pixel_data: ".1.\n111\n.1."
palette: "#ff0000"
```

---

## Security Model

1. **Container isolation** – all code runs inside a disposable Docker container.
2. **Non-root user** – the server process runs as `spriteuser`.
3. **Lua sandbox** – dangerous globals (`os.execute`, `io.open`, `require`, `debug`, etc.) are set to `nil` before user code runs.
4. **Pre-validation** – user Lua code is scanned for blocked patterns before execution.
5. **Timeout** – scripts are killed after 30 seconds.
6. **Resource limits** – Docker Compose sets CPU and memory caps.
7. **Output isolation** – only the bind-mounted `output/` directory is writable to the host.
