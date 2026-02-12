# LibreSprite MCP Server

An MCP server that lets AI assistants generate pixel-art sprites by driving [LibreSprite](https://github.com/LibreSprite/LibreSprite) via its JavaScript scripting API. Works with GitHub Copilot (VS Code), Claude Code, Cursor, and Claude Desktop.

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

The repo includes `.vscode/mcp.json` — it works out of the box. If you need to set it up manually, create `.vscode/mcp.json`:

```json
{
  "servers": {
    "libresprite": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "${workspaceFolder}/libresprite-mcp/output:/app/output",
        "libresprite-mcp"
      ]
    }
  }
}
```

#### Claude Code

```bash
claude mcp add libresprite -- docker run --rm -i -v "$(pwd)/libresprite-mcp/output:/app/output" libresprite-mcp
```

#### Claude Desktop / Cursor

Add to your MCP config (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "libresprite": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/absolute/path/to/libresprite-mcp/output:/app/output",
        "libresprite-mcp"
      ]
    }
  }
}
```

### 3. Use It

Ask your AI assistant to create a sprite. Example:

> "Create a 64x64 Pyromancer with a fireball"

The AI calls `run_script` with JavaScript, the server generates a PNG in `libresprite-mcp/output/`.

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `run_script(script)` | Execute JavaScript in LibreSprite — the main tool for creating sprites |
| `create_pixel_art(width, height, pixel_data, palette?)` | Create sprites from a text-based pixel map |
| `list_sprites()` | List generated PNGs in the output directory |

## MCP Resources

| Resource | Description |
|----------|-------------|
| `docs://reference` | LibreSprite JavaScript API reference |
| `docs://examples` | Example scripts for common sprite operations |

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
.vscode/mcp.json          ← MCP client config (VS Code)
AGENT_GUIDE.md             ← Instructions for AI agents
libresprite-mcp/
  server.py                ← MCP server
  Dockerfile               ← Builds the headless LibreSprite image
  docker-compose.yml       ← Optional compose config
  resources/
    reference.txt          ← JS API docs (served as MCP resource)
    examples.txt           ← Example scripts (served as MCP resource)
  remote/
    mcp.js                 ← LibreSprite relay script (for relay mode)
  output/                  ← Generated sprites land here
```
