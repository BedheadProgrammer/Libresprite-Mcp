# LibreSprite MCP Server

An MCP server that lets AI assistants generate pixel-art sprites by driving [LibreSprite](https://github.com/LibreSprite/LibreSprite) via its JavaScript scripting API. Works with GitHub Copilot (VS Code), Claude Code, Cursor, and Claude Desktop.

## Two Modes

| Mode | How it works | Use when… |
|------|-------------|----------|
| **docker** (headless) | Runs LibreSprite inside a Docker container via `--batch --script`. No UI needed. | You want the AI to work solo — no LibreSprite window required. |
| **relay** (interactive) | Container runs a Flask HTTP bridge. LibreSprite on your desktop polls it via `remote/mcp.js`. | You have LibreSprite open and want the AI to drive it interactively. |

## Setup (Clone → Ready)

### Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/)
- An MCP-compatible AI client (VS Code w/ Copilot, Claude Code, Cursor, Claude Desktop)

### 1. Clone & Build

```bash
git clone <this-repo>
cd Libresprite-Mcp/libresprite-mcp
docker build -t libresprite-mcp .
```

### 2. Configure Your AI Client

#### VS Code (GitHub Copilot)

The repo includes `.vscode/mcp.json` with **both** servers pre-configured — it works out of the box.

To set it up manually, create `.vscode/mcp.json`:

```json
{
  "servers": {
    "libresprite-docker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "${workspaceFolder}/libresprite-mcp/output:/app/output",
        "libresprite-mcp"
      ]
    },
    "libresprite-relay": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-p", "64823:64823",
        "-e", "LIBRESPRITE_MODE=relay",
        "-e", "LIBRESPRITE_RELAY_HOST=0.0.0.0",
        "-v", "${workspaceFolder}/libresprite-mcp/output:/app/output",
        "libresprite-mcp"
      ]
    }
  }
}
```

#### Claude Code

```bash
# Docker (headless) mode
claude mcp add libresprite-docker -- docker run --rm -i -v "$(pwd)/libresprite-mcp/output:/app/output" libresprite-mcp

# Relay (interactive) mode
claude mcp add libresprite-relay -- docker run --rm -i -p 64823:64823 -e LIBRESPRITE_MODE=relay -e LIBRESPRITE_RELAY_HOST=0.0.0.0 -v "$(pwd)/libresprite-mcp/output:/app/output" libresprite-mcp
```

#### Claude Desktop / Cursor

Add to your MCP config (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "libresprite-docker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/absolute/path/to/libresprite-mcp/output:/app/output",
        "libresprite-mcp"
      ]
    },
    "libresprite-relay": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-p", "64823:64823",
        "-e", "LIBRESPRITE_MODE=relay",
        "-e", "LIBRESPRITE_RELAY_HOST=0.0.0.0",
        "-v", "/absolute/path/to/libresprite-mcp/output:/app/output",
        "libresprite-mcp"
      ]
    }
  }
}
```

### 3. Use It

**Docker mode** — just ask:

> "Create a 64x64 Pyromancer with a fireball"

The AI calls tools on the `libresprite-docker` server, renders headlessly, and outputs a PNG to `libresprite-mcp/output/`.

**Relay mode** — open LibreSprite first:

1. Open LibreSprite on your desktop
2. Run `File → Scripts → remote/mcp.js` (or paste the script into the console)
3. Click **Connect** in the dialog that appears
4. Ask the AI to create a sprite — it will draw directly in your LibreSprite window

---

## MCP Tools

### Both Modes (docker + relay)

| Tool | Description |
|------|-------------|
| `draw_image(width, height, pixel_colors)` | **Primary tool.** Draw a complete sprite by providing every pixel colour as a flat JSON array of hex strings. |
| `create_sprite(width, height)` | Create a new empty sprite with the given dimensions. |
| `set_pixels(pixels)` | Set a sparse set of individual pixels by coordinate and hex colour. |
| `draw_rect(x, y, width, height, color)` | Draw a filled rectangle on the active image. |
| `fill_sprite(color)` | Fill the entire active image with a single colour. |
| `create_pixel_art(width, height, pixel_data, palette?)` | Create sprites from a text-based pixel map. |
| `run_script(script)` | Execute JavaScript in LibreSprite. **Advanced** — use the tools above for standard tasks. |
| `screenshot()` | Capture the current sprite as an inline image for visual inspection. |
| `get_sprite_info()` | Get info about the active sprite (width, height, layers, etc.). In relay mode reads from live LibreSprite; in docker mode reads from the latest generated PNG. |
| `get_pixel_data(x, y, width?, height?)` | Read pixel colour data from the active image. In relay mode reads from live LibreSprite; in docker mode reads from the latest generated PNG. |

### Docker Only

| Tool | Description |
|------|-------------|
| `list_sprites()` | List all generated sprite files in the output directory. |

## MCP Resources

| Resource | Description |
|----------|-------------|
| `docs://reference` | LibreSprite JavaScript API reference |
| `docs://examples` | Example scripts for common sprite operations |

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| All tools timeout after 60s | Relay mode active but LibreSprite not connected | Open LibreSprite, run `remote/mcp.js`, click Connect |
| `list_sprites` not visible | Connected to the relay server | Use `libresprite-docker` server instead |
| Docker image not found | Image not built yet | Run `docker build -t libresprite-mcp ./libresprite-mcp` |

---

## Scripting Reference

Scripts are **JavaScript (ES5)** — not Lua. Key rules:

- Use `var` (no `let`/`const`)
- Colors: `app.pixelColor.rgba(r, g, b, a)` — values 0–255
- Drawing: `app.activeImage.putPixel(x, y, color)`
- Canvas: `app.activeImage.width` / `.height`
- The server auto-saves output — do not call `saveAs()`

See `AGENT_GUIDE.md` for the full template that AI agents use.

---

## Project Structure

```
.vscode/mcp.json          ← MCP client config (two servers: docker + relay)
AGENT_GUIDE.md             ← Instructions for AI agents
libresprite-mcp/
  server.py                ← MCP server (mode-aware tool registration)
  Dockerfile               ← Builds the headless LibreSprite image
  docker-compose.yml       ← Optional compose config (both services)
  resources/
    reference.txt          ← JS API docs (served as MCP resource)
    examples.txt           ← Example scripts (served as MCP resource)
  remote/
    mcp.js                 ← LibreSprite relay script (for relay mode)
  output/                  ← Generated sprites land here
```
