# LibreSprite MCP — Agent Guide

When the user asks you to create a sprite, call the `mcp_libresprite_run_script` tool with JavaScript. That's it.

## Steps

1. User says "Create X sprite"
2. You call `mcp_libresprite_run_script` with the `script` parameter containing JavaScript
3. The server returns the output PNG path
4. Tell the user it's done

## Template

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
