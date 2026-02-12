# LibreSprite MCP Server

An MCP (Model Context Protocol) server that lets AI assistants (GitHub Copilot, Claude Code, Cursor, Claude Desktop) generate and edit pixel-art sprites by driving [LibreSprite](https://github.com/LibreSprite/LibreSprite) via its JavaScript scripting API.

---

## How It Works

The server supports two operation modes:

### Relay Mode (recommended — default)

The MCP server runs natively on your machine and communicates with a running LibreSprite instance through a local HTTP relay. A remote script (`remote/mcp.js`) inside LibreSprite polls the relay for scripts to execute.

```
AI Client (Copilot/Claude) → MCP Server → HTTP Relay → LibreSprite (mcp.js)
```

### Docker Mode

LibreSprite runs headless inside a Docker container with a virtual display (Xvfb). Scripts are executed via `libresprite --batch --script`. Best for CI or automated sprite generation.

```
AI Client → MCP Server (Docker) → LibreSprite (headless) → output/
```

---

## Quick Start — Relay Mode (Recommended)

### Prerequisites

- Python 3.11+
- [LibreSprite](https://github.com/LibreSprite/LibreSprite) installed
- An MCP-compatible client (VS Code with GitHub Copilot, Claude Code, Cursor, Claude Desktop)

### 1. Install dependencies

```bash
cd libresprite-mcp
pip install "mcp[cli]" flask
```

### 2. Set up the LibreSprite remote script

Copy `remote/mcp.js` into your LibreSprite scripts folder:

- **Linux**: `~/.config/libresprite/scripts/`
- **macOS**: `~/Library/Application Support/LibreSprite/scripts/`
- **Windows**: `%APPDATA%\LibreSprite\scripts\`

### 3. Configure your MCP client

#### VS Code with GitHub Copilot

Add to your VS Code `settings.json` (or workspace `.vscode/settings.json`):

```json
{
    "mcp": {
        "servers": {
            "libresprite": {
                "type": "stdio",
                "command": "python",
                "args": ["/absolute/path/to/libresprite-mcp/server.py"]
            }
        }
    }
}
```

#### Claude Code

```bash
claude mcp add libresprite -- python /absolute/path/to/libresprite-mcp/server.py
```

#### Claude Desktop / Cursor

Edit your MCP config file (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
    "mcpServers": {
        "libresprite": {
            "type": "stdio",
            "command": "python",
            "args": ["/absolute/path/to/libresprite-mcp/server.py"]
        }
    }
}
```

### 4. Connect

1. Open LibreSprite
2. Run the `mcp.js` script from the Scripts menu
3. Click **Connect** in the dialog that appears
4. Start talking to your AI about sprites!

---

## Quick Start — Docker Mode

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (and Docker Compose)

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

### Connect to an MCP Client (Docker mode)

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

---

## Quick Start — Docker Relay Mode

You can also run the MCP server inside a Docker container while communicating
with a LibreSprite instance running on your host machine.  This combines the
convenience of a containerised server with live interaction in your real
LibreSprite session.

```
AI Client (Copilot/Claude) → MCP Server (Docker) → HTTP Relay (port 64823) → LibreSprite (host)
```

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (and Docker Compose)
- [LibreSprite](https://github.com/LibreSprite/LibreSprite) installed on the host

### Build

```bash
cd libresprite-mcp
docker build -t libresprite-mcp .
```

### Run

```bash
docker run --rm -i -p 64823:64823 \
    -e LIBRESPRITE_MODE=relay \
    -e LIBRESPRITE_RELAY_HOST=0.0.0.0 \
    libresprite-mcp
```

Or using Docker Compose:

```bash
docker compose run --service-ports libresprite-mcp-relay
```

### Connect LibreSprite

1. Copy `remote/mcp.js` into your LibreSprite scripts folder (same as Relay Mode above).
2. Open LibreSprite on the host.
3. Run the `mcp.js` script from the Scripts menu and click **Connect**.

### Connect to an MCP Client (Docker relay mode)

```json
{
    "mcpServers": {
        "libresprite": {
            "command": "docker",
            "args": [
                "run", "--rm", "-i",
                "-p", "64823:64823",
                "-e", "LIBRESPRITE_MODE=relay",
                "-e", "LIBRESPRITE_RELAY_HOST=0.0.0.0",
                "libresprite-mcp"
            ]
        }
    }
}
```

---

## Available MCP Tools

| Tool | Description | Modes |
|------|-------------|-------|
| `draw_image(width, height, pixel_colors)` | **Primary tool.** Draw a complete sprite by providing every pixel colour as a flat JSON array of hex strings. A 64×64 image ≈ 10 k tokens. | relay, docker |
| `create_sprite(width, height)` | Create a new empty sprite with the given dimensions. | relay, docker |
| `set_pixels(pixels)` | Set a sparse set of individual pixels by coordinate and hex colour (JSON array). | relay, docker |
| `draw_rect(x, y, width, height, color)` | Draw a filled rectangle on the active image. | relay, docker |
| `fill_sprite(color)` | Fill the entire active image with a single colour. | relay, docker |
| `create_pixel_art(width, height, pixel_data, palette?)` | Create sprites from a simple text-based pixel map without writing code. | relay, docker |
| `run_script(script)` | Execute JavaScript in LibreSprite. **Advanced** — use the tools above for standard tasks. Read the API docs first via the `docs://reference` and `docs://examples` resources. | relay, docker |
| `list_sprites()` | List all generated sprite files in the output directory. | docker |
| `get_sprite_info()` | Get info about the active sprite (width, height, layers, etc.). | relay |
| `get_pixel_data(x, y, width?, height?)` | Read pixel colour data from the active image. | relay |

## Available MCP Resources

| Resource | Description |
|----------|-------------|
| `docs://reference` | LibreSprite JavaScript scripting API reference |
| `docs://examples` | Example scripts demonstrating common sprite operations |

## Available MCP Prompts

| Prompt | Description |
|--------|-------------|
| `libresprite(prompt)` | Prompt template that conditions the AI for LibreSprite scripting with proper context |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LIBRESPRITE_MODE` | `relay` | Operation mode: `relay` or `docker` |
| `LIBRESPRITE_RELAY_HOST` | `localhost` | Relay server bind address |
| `LIBRESPRITE_RELAY_PORT` | `64823` | Relay server port |
| `LIBRESPRITE_OUTPUT_DIR` | `/app/output` | Output directory (docker mode) |
| `LIBRESPRITE_BIN` | `/usr/local/bin/libresprite` | LibreSprite binary path (docker mode) |

---

## Critique of the Original Plan

The original `IMPLEMENTATION_PLAN.md` had several issues fixed in this implementation:

| # | Issue | Severity | Fix Applied |
|---|-------|----------|-------------|
| 1 | **Used Lua scripting** — LibreSprite's scripting API is JavaScript, not Lua. Scripts written in Lua would not execute. | **Critical** | Switched entirely to JavaScript scripting API. |
| 2 | **No API documentation** — The AI had no reference material and would hallucinate API calls. | **Critical** | Added MCP resources with full API reference and examples. |
| 3 | **No MCP prompts** — The AI wasn't conditioned to use the tools correctly. | **High** | Added a prompt template that guides the AI. |
| 4 | **Docker-only** — Required Docker for all usage, limiting compatibility with VS Code Copilot and Claude Code. | **High** | Added relay mode for native usage without Docker. |
| 5 | **No live interaction** — Each script started a new LibreSprite process; couldn't interact with user's canvas. | **High** | Added relay server + remote script for live interaction. |
| 6 | **Lua code injection** — The "security header" only set a variable that user code could overwrite. | **Medium** | Docker mode wraps scripts minimally; relay mode uses LibreSprite's sandboxed JS engine. |
| 7 | **AppImage requires FUSE** — Docker containers don't provide FUSE. | **Medium** | Dockerfile extracts AppImage with `--appimage-extract`. |
| 8 | **Missing `mcp[cli]` extras** — `pip install mcp` doesn't install transport extras. | **Medium** | Changed to `pip install "mcp[cli]"`. |
| 9 | **Limited tool set** — Only had `generate_sprite`. | **Medium** | Added `run_script`, `get_sprite_info`, `get_pixel_data`, `create_pixel_art`, `list_sprites`. |
| 10 | **No `.dockerignore` / `.gitignore`** — Build context included unnecessary files. | **Low** | Added both files. |

---

## Running Tests

```bash
cd libresprite-mcp
pip install "mcp[cli]" flask
python -m unittest test_server -v
```
