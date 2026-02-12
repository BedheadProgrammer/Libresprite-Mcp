"""LibreSprite MCP Server.

Provides MCP tools, resources, and prompts for AI-assisted sprite creation
using LibreSprite's JavaScript scripting API.

Supports two modes:
  - **relay** (default): Communicates with a running LibreSprite instance via
    a local HTTP relay server. Requires the ``remote/mcp.js`` script to be
    running inside LibreSprite.
  - **docker**: Runs LibreSprite headless inside a Docker container using
    ``--batch --script``. Used when the server itself lives inside the
    container image.

Set the ``LIBRESPRITE_MODE`` environment variable to choose the mode.
"""

import json
import os
import subprocess
import threading
import uuid

from mcp.server.fastmcp import FastMCP, Context

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODE = os.environ.get("LIBRESPRITE_MODE", "relay")  # "relay" or "docker"

# Docker-mode settings
OUTPUT_DIR = os.environ.get("LIBRESPRITE_OUTPUT_DIR", "/app/output")
LIBRESPRITE_BIN = os.environ.get("LIBRESPRITE_BIN", "/usr/local/bin/libresprite")
SCRIPT_TIMEOUT = 30  # seconds

# Relay-mode settings
RELAY_HOST = os.environ.get("LIBRESPRITE_RELAY_HOST", "localhost")
RELAY_PORT = int(os.environ.get("LIBRESPRITE_RELAY_PORT", "64823"))

# ---------------------------------------------------------------------------
# Relay Server (for live interaction with a running LibreSprite instance)
# ---------------------------------------------------------------------------


class LibrespriteProxy:
    """HTTP relay that bridges MCP tool calls to a running LibreSprite.

    A small Flask server exposes:
      GET  /       → returns the next script to execute (blocks until one is
                     submitted via :meth:`run_script`).
      POST /       → receives execution output from the LibreSprite remote
                     script.
      GET  /ping   → health-check endpoint.

    The ``remote/mcp.js`` script running inside LibreSprite polls these
    endpoints.
    """

    def __init__(self, host: str = "localhost", port: int = 64823):
        self._script: str | None = None
        self._output: str | None = None
        self._executing: bool = False
        self._script_event = threading.Event()
        self._output_event = threading.Event()

        self.host = host
        self.port = port

        # Lazy-import Flask so it is only required in relay mode.
        from flask import Flask, jsonify, request as flask_request  # noqa: F811

        self.app = Flask(__name__)
        self._flask_request = flask_request
        self._jsonify = jsonify
        self._setup_routes()
        self._server_thread: threading.Thread | None = None

    # -- Flask routes -------------------------------------------------------

    def _setup_routes(self):
        jsonify = self._jsonify
        flask_request = self._flask_request

        @self.app.get("/")
        def get_script():
            if self._script is None:
                self._script_event.wait()
                self._script_event.clear()
            script = self._script
            self._script = None
            return jsonify({"script": script})

        @self.app.post("/")
        def post_output():
            if not self._executing:
                return jsonify({"status": "ignored"})
            req = flask_request.get_json(force=True, silent=True)
            if req:
                self._output = req.get("output")
            else:
                return jsonify({"status": "invalid"})
            self._output_event.set()
            return jsonify({"status": "success"})

        @self.app.get("/ping")
        def ping():
            return jsonify({"status": "pong"})

    # -- Lifecycle ----------------------------------------------------------

    def _run_server(self):
        self.app.run(
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
        )

    def start(self):
        """Start the relay server in a background daemon thread."""
        if self._server_thread and self._server_thread.is_alive():
            return
        self._server_thread = threading.Thread(
            target=self._run_server, daemon=True
        )
        self._server_thread.start()

    # -- Script execution ---------------------------------------------------

    def run_script(self, script: str) -> str:
        """Send *script* to LibreSprite and block until output is received."""
        if self._executing:
            raise RuntimeError("Script execution is already in progress.")

        self._executing = True
        self._script = script
        self._script_event.set()

        # Wait for LibreSprite to post output back.  The first 15 s
        # covers normal latency; the extra 45 s grace period handles the
        # case where the user hasn't started the remote script yet (gives
        # them time to react to a warning from the MCP client).
        if not self._output_event.wait(timeout=15):
            self._output_event.wait(timeout=45)
        self._output_event.clear()

        output = self._output
        self._output = None
        self._executing = False

        if output is None:
            return (
                "Timed out waiting for LibreSprite to respond. "
                "Make sure LibreSprite is running with the remote/mcp.js "
                "script connected."
            )
        return output


# ---------------------------------------------------------------------------
# Docker-mode script execution helpers
# ---------------------------------------------------------------------------


def _run_script_docker(js_code: str) -> str:
    """Execute *js_code* inside LibreSprite running in headless Docker mode."""
    if not js_code or not js_code.strip():
        return "Error: script must not be empty."

    script_id = str(uuid.uuid4())
    script_path = f"/tmp/{script_id}.js"
    output_filename = f"{script_id}.png"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # Wrap user code with an auto-save footer.
    wrapped = (
        f"// === AUTO-GENERATED WRAPPER ===\n"
        f'var OUTPUT_PATH = "{output_path}";\n\n'
        f"// === USER CODE START ===\n"
        f"{js_code}\n"
        f"// === USER CODE END ===\n\n"
        f"// === AUTO-SAVE FOOTER ===\n"
        f"if (app.activeSprite) {{\n"
        f"    app.activeSprite.saveAs(OUTPUT_PATH, true);\n"
        f"}}\n"
    )

    try:
        with open(script_path, "w") as f:
            f.write(wrapped)

        result = subprocess.run(
            [LIBRESPRITE_BIN, "--batch", "--script", script_path],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
        )

        if result.returncode != 0:
            return (
                f"LibreSprite exited with code {result.returncode}.\n"
                f"stderr: {result.stderr}\nstdout: {result.stdout}"
            )

        if os.path.exists(output_path):
            return f"Sprite generated successfully: output/{output_filename}"

        return (
            "LibreSprite exited successfully but no output file was created. "
            "Make sure your script creates a Sprite and draws on it.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    except subprocess.TimeoutExpired:
        return f"Error: Script execution timed out after {SCRIPT_TIMEOUT}s."
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("LibreSprite Sprite Generator")

# Relay proxy – initialised lazily in main().
_proxy: LibrespriteProxy | None = None

# -- Resources --------------------------------------------------------------

RESOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")


@mcp.resource("docs://reference")
def read_reference() -> str:
    """Read the LibreSprite JavaScript scripting API reference."""
    doc_path = os.path.join(RESOURCES_DIR, "reference.txt")
    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading reference.txt: {e}"


@mcp.resource("docs://examples")
def read_examples() -> str:
    """Read example scripts using the LibreSprite JavaScript API."""
    doc_path = os.path.join(RESOURCES_DIR, "examples.txt")
    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading examples.txt: {e}"


# -- Prompts ----------------------------------------------------------------


@mcp.prompt()
def libresprite(prompt: str) -> str:
    """Prompt template that conditions the AI for LibreSprite scripting.

    Args:
        prompt: The user's request.
    """
    return (
        "LibreSprite is a program for creating and editing pixel art and "
        "animations.\n\n"
        "PREFERRED WORKFLOW — use the declarative tools to build pixel art "
        "directly.  You specify the pixels; the server draws them:\n"
        "1. `draw_image(width, height, pixel_colors)` — **primary tool**. "
        "Draw a complete sprite by providing every pixel colour as a flat "
        "JSON array of hex strings in row-major order.  A 64×64 image is "
        "only ~10 k tokens.\n"
        "2. `create_sprite(width, height)` — create a blank sprite for "
        "incremental editing.\n"
        "3. `set_pixels(pixels)` — touch up individual pixels by "
        "coordinate.\n"
        "4. `draw_rect(x, y, width, height, color)` — draw a filled "
        "rectangle.\n"
        "5. `fill_sprite(color)` — fill the entire image with a colour.\n"
        "6. `create_pixel_art(width, height, pixel_data, palette?)` — "
        "create sprites from a text-based pixel map.\n\n"
        "Only fall back to `run_script` for advanced operations that the "
        "declarative tools cannot handle (e.g. animation frames, layers, "
        "palette manipulation, or complex procedural generation).  If you "
        "do use `run_script`, read `docs://reference` and "
        "`docs://examples` first.\n\n"
        f"Here's what you need to do:\n\n{prompt}"
    )


# -- Tools ------------------------------------------------------------------


@mcp.tool()
def run_script(script: str) -> str:
    """Execute a JavaScript script inside LibreSprite.

    **Advanced tool** — prefer the declarative tools (``create_sprite``,
    ``set_pixels``, ``draw_rect``, ``fill_sprite``, ``create_pixel_art``)
    for standard pixel-art tasks.  Use ``run_script`` only when you need
    capabilities not covered by those tools (e.g. animation frames, layers,
    palette manipulation, or complex procedural generation).

    IMPORTANT: Read the resources `docs://reference` and `docs://examples`
    first to understand the available API.

    In **relay mode** the script runs inside a live LibreSprite instance
    (the user must have the remote/mcp.js script running).

    In **docker mode** the script runs via ``libresprite --batch --script``
    inside the container.

    Args:
        script: Valid JavaScript code using the LibreSprite scripting API.
                Example that fills the active image red:

                var col = app.pixelColor;
                var img = app.activeImage;
                img.clear(col.rgba(255, 0, 0, 255));
    """
    if not script or not script.strip():
        return "Error: script must not be empty."

    if MODE == "relay":
        if _proxy is None:
            return "Error: relay proxy is not initialised."
        return _proxy.run_script(script)

    return _run_script_docker(script)


@mcp.tool()
def list_sprites() -> str:
    """List all generated sprite files in the output directory.

    Only available in docker mode. Returns a newline-separated list of
    filenames, or a message indicating the directory is empty.
    """
    if MODE != "docker":
        return (
            "list_sprites is only available in docker mode. "
            "In relay mode, query the active sprite via run_script instead."
        )
    try:
        files = sorted(
            f
            for f in os.listdir(OUTPUT_DIR)
            if os.path.isfile(os.path.join(OUTPUT_DIR, f))
        )
    except FileNotFoundError:
        return "Output directory does not exist."

    if not files:
        return "No sprites have been generated yet."

    return "\n".join(files)


@mcp.tool()
def create_pixel_art(
    width: int,
    height: int,
    pixel_data: str,
    palette: str = "",
) -> str:
    """Create pixel art from a simple text-based pixel map.

    This is a convenience wrapper — the AI does not need to write raw
    JavaScript for simple sprites.

    Args:
        width:      Sprite width in pixels (1–256).
        height:     Sprite height in pixels (1–256).
        pixel_data: Characters representing pixels row by row.
                    Use '.' for transparent, digits 0-9 and letters a-z as
                    palette indices.  Rows are separated by newlines.
                    Example for a 3×3 cross: ``.1.\\n111\\n.1.``
        palette:    Comma-separated list of hex colours mapped to characters.
                    Index 0 → character '0', index 1 → '1', etc.
                    a=10, b=11 … z=35.
                    Example: ``#ff0000,#00ff00,#0000ff``
                    Defaults to a basic 16-colour palette if omitted.
    """
    if width < 1 or width > 256 or height < 1 or height > 256:
        return "Error: width and height must be between 1 and 256."

    rows = pixel_data.strip().split("\n")
    if len(rows) != height:
        return f"Error: expected {height} rows in pixel_data but got {len(rows)}."

    for i, row in enumerate(rows):
        if len(row) != width:
            return f"Error: row {i} has {len(row)} characters but width is {width}."

    # Build palette mapping
    default_palette = [
        "000000", "ffffff", "ff0000", "00ff00", "0000ff",
        "ffff00", "ff00ff", "00ffff", "808080", "c0c0c0",
        "800000", "008000", "000080", "808000", "800080", "008080",
    ]
    colors: list[str] = []
    if palette.strip():
        colors = [c.strip().lstrip("#") for c in palette.split(",")]
    else:
        colors = default_palette

    def char_to_index(ch: str) -> int | None:
        if ch == ".":
            return None
        if ch.isdigit():
            return int(ch)
        if ch.isalpha():
            return ord(ch.lower()) - ord("a") + 10
        return None

    # Build JavaScript pixel-setting code
    js_pixels: list[str] = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            idx = char_to_index(ch)
            if idx is None:
                continue
            if idx >= len(colors):
                return (
                    f"Error: character '{ch}' maps to palette index {idx} "
                    f"but only {len(colors)} colors defined."
                )
            hex_color = colors[idx]
            if len(hex_color) != 6 or not all(
                c in "0123456789abcdefABCDEF" for c in hex_color
            ):
                return (
                    f"Error: palette color must be exactly 6 hex digits "
                    f"(RRGGBB), got: '{hex_color}'."
                )
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            js_pixels.append(
                f"    img.putPixel({x}, {y}, col.rgba({r}, {g}, {b}, 255));"
            )

    pixel_lines = "\n".join(js_pixels)
    js_code = (
        f"var col = app.pixelColor;\n"
        f"var img = app.activeImage;\n"
        f"img.clear(col.rgba(0, 0, 0, 0));\n"
        f"{pixel_lines}\n"
        f'console.log("Pixel art drawn: {width}x{height}");\n'
    )

    return run_script(js_code)


@mcp.tool()
def get_sprite_info() -> str:
    """Get information about the currently active sprite in LibreSprite.

    Returns width, height, color mode, layer count, and filename.
    Only available in relay mode.
    """
    if MODE != "relay":
        return "get_sprite_info is only available in relay mode."
    script = (
        "var s = app.activeSprite;\n"
        "if (s) {\n"
        '    console.log("width:" + s.width);\n'
        '    console.log("height:" + s.height);\n'
        '    console.log("colorMode:" + s.colorMode);\n'
        '    console.log("layerCount:" + s.layerCount);\n'
        '    console.log("filename:" + s.filename);\n'
        "} else {\n"
        '    console.log("No active sprite.");\n'
        "}\n"
    )
    return run_script(script)


@mcp.tool()
def get_pixel_data(x: int, y: int, width: int = 1, height: int = 1) -> str:
    """Read pixel colour data from the active image.

    Args:
        x:      X coordinate of the top-left corner.
        y:      Y coordinate of the top-left corner.
        width:  Number of columns to read (default 1).
        height: Number of rows to read (default 1).

    Returns RGBA values for each pixel. Only available in relay mode.
    """
    if MODE != "relay":
        return "get_pixel_data is only available in relay mode."
    script = (
        "var col = app.pixelColor;\n"
        "var img = app.activeImage;\n"
        "if (!img) { console.log('No active image.'); }\n"
        "else {\n"
        f"    for (var py = {y}; py < {y + height}; py++) {{\n"
        f"        for (var px = {x}; px < {x + width}; px++) {{\n"
        "            var c = img.getPixel(px, py);\n"
        "            console.log('(' + px + ',' + py + '): rgba(' "
        "                + col.rgbaR(c) + ',' + col.rgbaG(c) + ',' "
        "                + col.rgbaB(c) + ',' + col.rgbaA(c) + ')');\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    return run_script(script)


# -- Declarative pixel-art tools -------------------------------------------


def _parse_hex_color(hex_str: str) -> tuple[int, int, int, int] | str:
    """Parse a hex colour string into (r, g, b, a).

    Accepts ``#RRGGBB``, ``RRGGBB``, ``#RRGGBBAA``, or ``RRGGBBAA``.
    Returns a tuple on success or an error string on failure.
    """
    h = hex_str.strip().lstrip("#")
    if len(h) not in (6, 8) or not all(c in "0123456789abcdefABCDEF" for c in h):
        return f"Invalid hex colour '{hex_str}'. Use RRGGBB or RRGGBBAA format."
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return (r, g, b, a)


@mcp.tool()
def create_sprite(width: int, height: int) -> str:
    """Create a new empty sprite with the given dimensions.

    Call this before ``set_pixels``, ``draw_rect``, ``fill_sprite``, or
    ``create_pixel_art`` when no sprite is open yet.

    Args:
        width:  Sprite width in pixels (1–256).
        height: Sprite height in pixels (1–256).
    """
    if width < 1 or width > 256 or height < 1 or height > 256:
        return "Error: width and height must be between 1 and 256."

    js_code = (
        f"app.command.NewFile();\n"
        f"var s = app.activeSprite;\n"
        f"if (s) {{\n"
        f"    s.width = {width};\n"
        f"    s.height = {height};\n"
        f'    console.log("Created sprite: {width}x{height}");\n'
        f"}} else {{\n"
        f'    console.log("Error: could not create sprite.");\n'
        f"}}\n"
    )
    return run_script(js_code)


@mcp.tool()
def set_pixels(pixels: str) -> str:
    """Set a sparse set of individual pixels on the active image.

    Best for touching up or editing a small number of specific pixels.
    For drawing a complete image, prefer ``draw_image`` instead.

    Args:
        pixels: A JSON array of pixel objects.  Each object must have:
                ``x`` (int), ``y`` (int), and ``color`` (hex string RRGGBB or
                RRGGBBAA, with or without '#').
                Example::

                    [
                      {"x": 0, "y": 0, "color": "#ff0000"},
                      {"x": 1, "y": 0, "color": "#00ff00"},
                      {"x": 2, "y": 0, "color": "0000ff"}
                    ]
    """
    try:
        data = json.loads(pixels)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"Error: pixels must be a valid JSON array. ({exc})"

    if not isinstance(data, list) or len(data) == 0:
        return "Error: pixels must be a non-empty JSON array."

    js_lines: list[str] = [
        "var col = app.pixelColor;",
        "var img = app.activeImage;",
        "if (!img) { console.log('Error: no active image. "
        "Use create_sprite first.'); }",
        "else {",
    ]

    for i, px in enumerate(data):
        if not isinstance(px, dict):
            return f"Error: pixel at index {i} is not an object."
        if "x" not in px or "y" not in px or "color" not in px:
            return f"Error: pixel at index {i} must have 'x', 'y', and 'color'."
        parsed = _parse_hex_color(str(px["color"]))
        if isinstance(parsed, str):
            return f"Error at pixel index {i}: {parsed}"
        r, g, b, a = parsed
        js_lines.append(
            f"    img.putPixel({int(px['x'])}, {int(px['y'])}, "
            f"col.rgba({r}, {g}, {b}, {a}));"
        )

    count = len(data)
    js_lines.append(f'    console.log("Set {count} pixel(s).");')
    js_lines.append("}")

    return run_script("\n".join(js_lines))


@mcp.tool()
def draw_rect(
    x: int, y: int, width: int, height: int, color: str
) -> str:
    """Draw a filled rectangle on the active image.

    Args:
        x:      X coordinate of the top-left corner.
        y:      Y coordinate of the top-left corner.
        width:  Rectangle width in pixels.
        height: Rectangle height in pixels.
        color:  Hex colour string (RRGGBB or RRGGBBAA, with or without '#').
    """
    if width < 1 or height < 1:
        return "Error: width and height must be at least 1."

    parsed = _parse_hex_color(color)
    if isinstance(parsed, str):
        return parsed
    r, g, b, a = parsed

    js_code = (
        "var col = app.pixelColor;\n"
        "var img = app.activeImage;\n"
        "if (!img) { console.log('Error: no active image. "
        "Use create_sprite first.'); }\n"
        "else {\n"
        f"    var c = col.rgba({r}, {g}, {b}, {a});\n"
        f"    for (var py = {y}; py < {y + height}; py++) {{\n"
        f"        for (var px = {x}; px < {x + width}; px++) {{\n"
        "            img.putPixel(px, py, c);\n"
        "        }\n"
        "    }\n"
        f'    console.log("Drew rectangle {width}x{height} at ({x},{y})");\n'
        "}\n"
    )
    return run_script(js_code)


@mcp.tool()
def fill_sprite(color: str) -> str:
    """Fill the entire active image with a single colour.

    Args:
        color: Hex colour string (RRGGBB or RRGGBBAA, with or without '#').
               Use ``00000000`` for fully transparent.
    """
    parsed = _parse_hex_color(color)
    if isinstance(parsed, str):
        return parsed
    r, g, b, a = parsed

    js_code = (
        "var col = app.pixelColor;\n"
        "var img = app.activeImage;\n"
        "if (!img) { console.log('Error: no active image. "
        "Use create_sprite first.'); }\n"
        "else {\n"
        f"    img.clear(col.rgba({r}, {g}, {b}, {a}));\n"
        f'    console.log("Filled sprite with #{color.strip().lstrip("#")}");\n'
        "}\n"
    )
    return run_script(js_code)


@mcp.tool()
def draw_image(width: int, height: int, pixel_colors: str) -> str:
    """Draw a complete sprite image by specifying every pixel colour.

    This is the **primary** tool for creating pixel art.  The agent provides
    the full pixel grid as a flat JSON array of hex colour strings in
    row-major order (left-to-right, top-to-bottom).  The tool creates a new
    sprite of the given size and fills it with the supplied colours.

    A 64×64 sprite is 4 096 entries — roughly 10 k tokens — well within a
    standard context window.

    Args:
        width:        Sprite width in pixels (1–256).
        height:       Sprite height in pixels (1–256).
        pixel_colors: A JSON array of hex colour strings, one per pixel, in
                      row-major order.  Length must equal ``width × height``.
                      Use ``"."`` for transparent pixels.
                      Example for a 3×2 image (3 wide, 2 tall)::

                          ["ff0000","00ff00","0000ff",
                           "ffff00","ff00ff","00ffff"]
    """
    if width < 1 or width > 256 or height < 1 or height > 256:
        return "Error: width and height must be between 1 and 256."

    try:
        colors = json.loads(pixel_colors)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"Error: pixel_colors must be a valid JSON array. ({exc})"

    if not isinstance(colors, list):
        return "Error: pixel_colors must be a JSON array."

    expected = width * height
    if len(colors) != expected:
        return (
            f"Error: expected {expected} colours ({width}×{height}) "
            f"but got {len(colors)}."
        )

    # Pre-parse every colour before generating JavaScript.
    parsed_colors: list[tuple[int, int, int, int] | None] = []
    for i, c in enumerate(colors):
        cs = str(c).strip()
        if cs == ".":
            parsed_colors.append(None)  # transparent
            continue
        parsed = _parse_hex_color(cs)
        if isinstance(parsed, str):
            return f"Error at pixel index {i}: {parsed}"
        parsed_colors.append(parsed)

    # Build JavaScript using putImageData for efficiency.  The image data is
    # a Uint8Array of RGBA bytes.
    rgba_values: list[str] = []
    for pc in parsed_colors:
        if pc is None:
            rgba_values.extend(("0", "0", "0", "0"))
        else:
            r, g, b, a = pc
            rgba_values.extend((str(r), str(g), str(b), str(a)))

    # Emit the array in chunks to keep individual lines manageable.
    chunk_size = 256  # values per line (64 pixels worth of RGBA)
    array_lines: list[str] = []
    for start in range(0, len(rgba_values), chunk_size):
        chunk = ",".join(rgba_values[start : start + chunk_size])
        array_lines.append(f"    {chunk},")

    array_body = "\n".join(array_lines)

    js_code = (
        "app.command.NewFile();\n"
        "var s = app.activeSprite;\n"
        "if (!s) { console.log('Error: could not create sprite.'); }\n"
        "else {\n"
        f"    s.width = {width};\n"
        f"    s.height = {height};\n"
        "    var img = app.activeImage;\n"
        "    var data = new Uint8Array([\n"
        f"{array_body}\n"
        "    ]);\n"
        "    img.putImageData(data);\n"
        f'    console.log("Drew image: {width}x{height} '
        f'({expected} pixels)");\n'
        "}\n"
    )
    return run_script(js_code)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Start the MCP server."""
    global _proxy

    if MODE == "relay":
        # Suppress noisy Flask/click logging that interferes with stdio.
        import logging
        logging.disable(logging.WARNING)
        try:
            import click
            click.echo = lambda *a, **k: None  # type: ignore[assignment]
            click.secho = lambda *a, **k: None  # type: ignore[assignment]
        except ImportError:
            pass

        _proxy = LibrespriteProxy(host=RELAY_HOST, port=RELAY_PORT)
        _proxy.start()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
