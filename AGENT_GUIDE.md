# LibreSprite MCP — Agent Guide

This project exposes **two MCP servers**.  Pick the one that matches your situation:

| Server | When to use |
|--------|-------------|
| **libresprite-docker** | You want the AI to work **autonomously** — no LibreSprite window needed. Sprites are rendered headlessly inside Docker. |
| **libresprite-relay** | You have **LibreSprite open** on your desktop and want the AI to drive it interactively. Requires `remote/mcp.js` loaded inside LibreSprite. |

---

## Available Tools

### Declarative Tools (preferred)

| Tool | Description |
|------|-------------|
| `draw_image(width, height, pixel_colors)` | **Primary tool.** Draw a complete sprite by providing every pixel colour as a flat JSON array of hex strings in row-major order. A 64×64 image is only ~10k tokens. |
| `create_sprite(width, height)` | Create a new empty sprite. Call this before `set_pixels`, `draw_rect`, or `fill_sprite` when no sprite exists yet. |
| `set_pixels(pixels)` | Set a sparse set of individual pixels by coordinate and hex colour. Best for touch-ups. |
| `draw_rect(x, y, width, height, color)` | Draw a filled rectangle on the active image. |
| `fill_sprite(color)` | Fill the entire active image with a single colour. |
| `create_pixel_art(width, height, pixel_data, palette?)` | Create sprites from a text-based pixel map using character-to-colour mapping. |

### Inspection Tools

| Tool | Description |
|------|-------------|
| `screenshot()` | Capture the current sprite as an inline image for visual inspection. **Use after every draw operation.** |
| `get_sprite_info()` | Get width, height, colour mode, layer count, and filename of the active sprite. Works in both modes. |
| `get_pixel_data(x, y, width?, height?)` | Read pixel RGBA data from a region. Works in both modes. |

### Advanced / Mode-specific

| Tool | Description |
|------|-------------|
| `run_script(script)` | Execute raw JavaScript inside LibreSprite. Only use when declarative tools can't do the job (animation frames, layers, palette manipulation, procedural generation). Read `docs://reference` and `docs://examples` first. |
| `list_sprites()` | List all generated sprite files in the output directory. **Docker mode only.** |

### MCP Resources

| Resource | Description |
|----------|-------------|
| `docs://reference` | LibreSprite JavaScript API reference — read before using `run_script`. |
| `docs://examples` | Example scripts for common sprite operations. |

---

## Quick Start (Docker / Solo)

1. User says "Create X sprite"
2. Call `draw_image` with the full pixel grid (preferred), or use `create_sprite` + `set_pixels` / `draw_rect` for incremental work
3. Call `screenshot` to see the result
4. Evaluate — if it looks wrong, fix with `set_pixels` or another tool
5. Call `screenshot` again to verify, then tell the user it's done

## Quick Start (Relay / Interactive)

1. User opens LibreSprite and loads `remote/mcp.js` (connects to the relay)
2. Call `draw_image` or other declarative tools on the **libresprite-relay** server
3. The changes appear live in the user's LibreSprite window
4. Call `screenshot` to capture the current sprite
5. Use `get_sprite_info` and `get_pixel_data` to inspect the live state

---

## Preferred Workflow

Use the **declarative tools** (`draw_image`, `create_sprite`, `set_pixels`, etc.) for all standard pixel-art tasks. Only fall back to `run_script` for advanced operations. Always call `screenshot` after drawing to verify your work.

**Iterative loop:** draw → screenshot → evaluate → fix → screenshot → done

---

## Template (for `run_script` only)

Every sprite script follows this exact structure. Copy it, fill in the drawing code:

```javascript
app.command.setParameter("width", "64");
app.command.setParameter("height", "64");
app.command.setParameter("colorMode", "rgb");
app.command.NewFile();
app.command.clearParameters();

var col = app.pixelColor;
var img = app.activeImage;
var W = 64, H = 64;
img.clear(col.rgba(0, 0, 0, 0));

function px(x, y, c) {
    if (x >= 0 && x < W && y >= 0 && y < H) img.putPixel(x, y, c);
}
function rect(x, y, w, h, c) {
    for (var j = y; j < y + h; j++)
        for (var i = x; i < x + w; i++)
            px(i, j, c);
}
function circle(cx, cy, r, c) {
    for (var j = cy - r; j <= cy + r; j++)
        for (var i = cx - r; i <= cx + r; i++)
            if ((i - cx) * (i - cx) + (j - cy) * (j - cy) <= r * r)
                px(i, j, c);
}

// Define colors with col.rgba(r, g, b, 255)
// Draw with px(), rect(), circle()
// (0,0) is top-left

console.log("Done!");
```

## Rules

- `var` only — no `let`/`const` (ES5 engine)
- Colors: `col.rgba(r, g, b, a)` — values 0–255, alpha 255 = opaque
- No `require`, `import`, `saveAs` — sandboxed, auto-saves
- JavaScript only, not Lua

## DO NOT

- Look for Docker, check containers, build images, or inspect infrastructure
- Write test scripts or Python wrappers — call the tool directly
- Use `let`, `const`, `require()`, `import`, or `saveAs()`
