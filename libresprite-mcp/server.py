import os
import re
import subprocess
import uuid

from mcp.server.fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP("LibreSprite Sprite Generator")

# Path constants
OUTPUT_DIR = "/app/output"
LIBRESPRITE_BIN = "/usr/local/bin/libresprite"
SCRIPT_TIMEOUT = 30  # seconds

# Lua functions/modules that must be blocked in user-supplied code.
# os.execute, os.remove, io.open, io.popen, loadfile, dofile, require
# can all be used to escape the intended sandbox.
BLOCKED_LUA_PATTERNS = [
    r"\bos\s*\.\s*execute\b",
    r"\bos\s*\.\s*remove\b",
    r"\bos\s*\.\s*rename\b",
    r"\bos\s*\.\s*tmpname\b",
    r"\bio\s*\.\s*open\b",
    r"\bio\s*\.\s*popen\b",
    r"\bio\s*\.\s*lines\b",
    r"\bio\s*\.\s*input\b",
    r"\bio\s*\.\s*output\b",
    r"\bloadfile\b",
    r"\bdofile\b",
    r"\brequire\b",
    r"\bload\s*\(",
    r"\bpackage\b",
    r"\bdebug\b",
]


def _validate_lua_code(lua_code: str) -> str | None:
    """Return an error message if the Lua code contains blocked patterns."""
    for pattern in BLOCKED_LUA_PATTERNS:
        match = re.search(pattern, lua_code)
        if match:
            return (
                f"Blocked: Lua code contains disallowed pattern '{match.group()}'. "
                "Functions like os.execute, io.open, loadfile, dofile, require, "
                "and debug are not permitted for security reasons."
            )
    return None


def _build_sandboxed_script(lua_code: str, output_path: str) -> str:
    """Wrap user Lua code with a sandbox that disables dangerous globals."""
    return f"""\
-- === SANDBOX HEADER (auto-generated, do not modify) ===
-- Disable dangerous Lua standard library functions
os.execute = nil
os.remove = nil
os.rename = nil
os.tmpname = nil
os.exit = nil
io.popen = nil
io.open = nil
io.lines = nil
io.input = nil
io.output = nil
loadfile = nil
dofile = nil
rawset(_G, "require", nil)
rawset(_G, "package", nil)
rawset(_G, "debug", nil)

-- Predefined output path for this run
local OUTPUT_PATH = "{output_path}"
-- === END SANDBOX HEADER ===

-- === USER CODE START ===
{lua_code}
-- === USER CODE END ===

-- === AUTO-SAVE FOOTER ===
-- If the user script created a sprite but did not save it, save it now.
if app.activeSprite then
    app.activeSprite:saveCopyAs(OUTPUT_PATH)
end
"""


@mcp.tool()
def generate_sprite(lua_code: str) -> str:
    """
    Execute a Lua script inside LibreSprite to generate pixel-art sprites.

    The script runs in headless (batch) mode with a virtual display.
    The generated sprite is saved automatically and returned via the
    mounted output directory.

    Dangerous Lua functions (os.execute, io.open, require, etc.) are
    disabled inside the sandbox.

    Args:
        lua_code: A valid Lua script using the LibreSprite scripting API.
                  Example that creates a 32x32 red square:

                  local spr = Sprite(32, 32)
                  app.useTool{
                      tool="filled_rectangle",
                      color=Color(255, 0, 0),
                      points={Point(0,0), Point(31,31)}
                  }
    """
    if not lua_code or not lua_code.strip():
        return "Error: lua_code must not be empty."

    # Validate against blocked patterns (defense in depth)
    error = _validate_lua_code(lua_code)
    if error:
        return error

    script_id = str(uuid.uuid4())
    script_path = f"/tmp/{script_id}.lua"
    output_filename = f"{script_id}.png"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # Build sandboxed script and write to temp file
    sandboxed = _build_sandboxed_script(lua_code, output_path)

    try:
        with open(script_path, "w") as f:
            f.write(sandboxed)

        result = subprocess.run(
            [LIBRESPRITE_BIN, "--batch", "--script", script_path],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
        )

        if result.returncode != 0:
            return f"LibreSprite exited with code {result.returncode}.\nstderr: {result.stderr}\nstdout: {result.stdout}"

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


@mcp.tool()
def list_sprites() -> str:
    """
    List all generated sprite files in the output directory.

    Returns a newline-separated list of filenames, or a message
    indicating the output directory is empty.
    """
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
    """
    Create pixel art from a simple text-based pixel map.

    This is a convenience wrapper so the AI does not need to write raw
    Lua for simple sprites.

    Args:
        width:      Sprite width in pixels (1-256).
        height:     Sprite height in pixels (1-256).
        pixel_data: A string of characters representing pixels row by row.
                    Use '.' for transparent, and single characters (0-9, a-z)
                    as palette indices.  Rows are separated by newlines.
                    Example for a 3x3 cross:
                        ".1.\\n111\\n.1."
        palette:    Comma-separated list of hex colors mapped to characters.
                    Index 0 maps to character '0', index 1 to '1', etc.
                    a=10, b=11 ... z=35.
                    Example: "#ff0000,#00ff00,#0000ff"
                    Defaults to a basic 16-color palette if omitted.
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

    # Map characters to palette indices
    def char_to_index(ch: str) -> int | None:
        if ch == ".":
            return None
        if ch.isdigit():
            return int(ch)
        if ch.isalpha():
            return ord(ch.lower()) - ord("a") + 10
        return None

    # Build Lua pixel-setting code
    lua_pixels = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            idx = char_to_index(ch)
            if idx is None:
                continue
            if idx >= len(colors):
                return f"Error: character '{ch}' maps to palette index {idx} but only {len(colors)} colors defined."
            hex_color = colors[idx]
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            lua_pixels.append(
                f'    image:drawPixel({x}, {y}, Color({r}, {g}, {b}, 255))'
            )

    lua_code = f"""\
local spr = Sprite({width}, {height}, ColorMode.RGB)
local cel = spr.cels[1]
local image = cel.image
{chr(10).join(lua_pixels)}
"""

    return generate_sprite(lua_code)


if __name__ == "__main__":
    mcp.run(transport="stdio")
