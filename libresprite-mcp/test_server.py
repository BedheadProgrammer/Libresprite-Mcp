"""Tests for LibreSprite MCP server logic.

These tests validate the tool functions, resource loading, and helpers
without requiring Docker, Flask, or LibreSprite to be installed.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Force docker mode for tests so we don't need Flask
os.environ["LIBRESPRITE_MODE"] = "docker"

# Add the project directory to the path so we can import server
sys.path.insert(0, os.path.dirname(__file__))

import server
from server import (
    _run_script_docker,
    _parse_hex_color,
    _create_blank_png,
    _rgba_to_png,
    _read_png_info,
    _read_png_pixels,
    _get_latest_sprite_path,
    create_pixel_art,
    create_sprite,
    draw_image,
    draw_rect,
    fill_sprite,
    get_pixel_data,
    get_sprite_info,
    list_sprites,
    run_script,
    screenshot,
    set_pixels,
    read_reference,
    read_examples,
    libresprite,
)


class TestRunScriptDockerValidation(unittest.TestCase):
    """Test input validation for docker-mode script execution."""

    def test_empty_script_returns_error(self):
        result = _run_script_docker("")
        self.assertIn("Error", result)

    def test_whitespace_only_returns_error(self):
        result = _run_script_docker("   \n  ")
        self.assertIn("Error", result)

    @patch("server.subprocess.run")
    def test_successful_execution(self, mock_run):
        """Test that a valid script is written and executed."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        # The output file won't actually exist, so expect the "no output" msg
        result = _run_script_docker("console.log('hello');")
        self.assertTrue(mock_run.called)
        # Check the script was passed to LibreSprite correctly
        args = mock_run.call_args
        cmd = args[0][0]
        self.assertIn("--batch", cmd)
        self.assertIn("--script", cmd)

    @patch("server.subprocess.run")
    def test_nonzero_exit_code(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="some error"
        )
        result = _run_script_docker("bad code")
        self.assertIn("exited with code 1", result)
        self.assertIn("some error", result)

    @patch("server.subprocess.run")
    def test_timeout_handling(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        result = _run_script_docker("while(true){}")
        self.assertIn("timed out", result)


class TestRunScriptWrapper(unittest.TestCase):
    """Test the run_script MCP tool wrapper."""

    def test_empty_script_error(self):
        result = run_script("")
        self.assertIn("Error", result)

    def test_whitespace_script_error(self):
        result = run_script("  ")
        self.assertIn("Error", result)


class TestListSprites(unittest.TestCase):
    """Test the list_sprites tool."""

    def test_docker_mode_works(self):
        # In docker mode, it tries to list /app/output which doesn't exist
        # in the test environment
        result = list_sprites()
        # Should return either the listing or error about directory
        self.assertIsInstance(result, str)

    @patch("server.MODE", "relay")
    def test_relay_mode_returns_message(self):
        # list_sprites is only registered in docker mode; calling it in relay
        # mode still runs the same docker-mode function which checks disk.
        result = list_sprites()
        self.assertIsInstance(result, str)


class TestCreatePixelArt(unittest.TestCase):
    """Test the create_pixel_art convenience tool."""

    def test_invalid_width_too_large(self):
        result = create_pixel_art(width=300, height=10, pixel_data="." * 10)
        self.assertIn("Error", result)

    def test_invalid_width_zero(self):
        result = create_pixel_art(width=0, height=10, pixel_data="")
        self.assertIn("Error", result)

    def test_invalid_height_zero(self):
        result = create_pixel_art(width=10, height=0, pixel_data="")
        self.assertIn("Error", result)

    def test_row_count_mismatch(self):
        result = create_pixel_art(width=3, height=2, pixel_data=".1.\n111\n.1.")
        self.assertIn("expected 2 rows", result)

    def test_column_count_mismatch(self):
        result = create_pixel_art(width=3, height=2, pixel_data=".1.\n11")
        self.assertIn("has 2 characters but width is 3", result)

    def test_palette_index_out_of_range(self):
        result = create_pixel_art(
            width=1, height=1, pixel_data="5", palette="#ff0000"
        )
        self.assertIn("palette index 5", result)

    def test_invalid_hex_color(self):
        result = create_pixel_art(
            width=1, height=1, pixel_data="0", palette="xyz123"
        )
        self.assertIn("Error", result)


class TestResources(unittest.TestCase):
    """Test that MCP resources load correctly."""

    def test_read_reference_returns_content(self):
        content = read_reference()
        self.assertIn("Sprite", content)
        self.assertIn("app", content)
        self.assertIn("putPixel", content)

    def test_read_examples_returns_content(self):
        content = read_examples()
        self.assertIn("putPixel", content)
        self.assertIn("pixelColor", content)

    def test_reference_is_javascript_not_lua(self):
        content = read_reference()
        self.assertIn("JavaScript", content)
        self.assertNotIn("Lua scripting", content)

    def test_reference_contains_key_api_elements(self):
        content = read_reference()
        self.assertIn("putPixel", content)
        self.assertIn("pixelColor", content)
        self.assertIn("rgba", content)
        self.assertIn("activeImage", content)
        self.assertIn("activeSprite", content)

    def test_examples_use_javascript_syntax(self):
        content = read_examples()
        self.assertIn("var ", content)
        # Should not contain Lua-specific syntax
        self.assertNotIn("local ", content)


class TestPrompt(unittest.TestCase):
    """Test the MCP prompt template."""

    def test_prompt_includes_user_request(self):
        result = libresprite("make a red square")
        self.assertIn("make a red square", result)

    def test_prompt_mentions_declarative_tools(self):
        result = libresprite("test")
        self.assertIn("draw_image", result)
        self.assertIn("create_sprite", result)
        self.assertIn("set_pixels", result)
        self.assertIn("draw_rect", result)
        self.assertIn("fill_sprite", result)

    def test_prompt_mentions_draw_image_as_primary(self):
        result = libresprite("test")
        # draw_image should appear before run_script in the prompt
        draw_idx = result.index("draw_image")
        run_idx = result.index("run_script")
        self.assertLess(draw_idx, run_idx)

    def test_prompt_mentions_resources(self):
        result = libresprite("test")
        self.assertIn("docs://reference", result)
        self.assertIn("docs://examples", result)

    def test_prompt_mentions_run_script_as_fallback(self):
        result = libresprite("test")
        self.assertIn("run_script", result)
        self.assertIn("fall back", result)


class TestDockerScriptWrapping(unittest.TestCase):
    """Test that docker mode wraps scripts correctly."""

    @patch("server.subprocess.run")
    def test_wrapper_includes_user_code(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        user_code = "var img = app.activeImage;"
        _run_script_docker(user_code)

        # Find the script file that was written
        args = mock_run.call_args[0][0]
        script_path = args[-1]  # last argument is the script path

        # The script path pattern is /tmp/<uuid>.js
        self.assertTrue(script_path.endswith(".js"))

    @patch("server.subprocess.run")
    def test_wrapper_includes_auto_save(self, mock_run):
        """Verify the auto-save footer is present in docker mode scripts."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # We need to intercept the file write to check contents
        written_content = None
        original_open = open

        def mock_open(path, mode="r", *a, **kw):
            nonlocal written_content
            f = original_open(path, mode, *a, **kw)
            if "w" in mode and path.endswith(".js"):

                class CapturingFile:
                    def __init__(self, f):
                        self._f = f

                    def write(self, data):
                        nonlocal written_content
                        written_content = data
                        return self._f.write(data)

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return self._f.__exit__(*args)

                return CapturingFile(f)
            return f

        with patch("builtins.open", side_effect=mock_open):
            _run_script_docker("console.log('test');")

        self.assertIsNotNone(written_content)
        self.assertIn("AUTO-SAVE FOOTER", written_content)
        self.assertIn("saveAs", written_content)
        self.assertIn("OUTPUT_PATH", written_content)


class TestParseHexColor(unittest.TestCase):
    """Test the _parse_hex_color helper."""

    def test_six_digit_hex(self):
        self.assertEqual(_parse_hex_color("#ff0000"), (255, 0, 0, 255))

    def test_six_digit_no_hash(self):
        self.assertEqual(_parse_hex_color("00ff00"), (0, 255, 0, 255))

    def test_eight_digit_with_alpha(self):
        self.assertEqual(_parse_hex_color("#0000ff80"), (0, 0, 255, 128))

    def test_invalid_hex(self):
        result = _parse_hex_color("xyz")
        self.assertIn("Invalid", result)

    def test_empty_string(self):
        result = _parse_hex_color("")
        self.assertIn("Invalid", result)


class TestCreateSprite(unittest.TestCase):
    """Test the create_sprite tool."""

    def test_invalid_width(self):
        result = create_sprite(0, 10)
        self.assertIn("Error", result)

    def test_invalid_height(self):
        result = create_sprite(10, 300)
        self.assertIn("Error", result)

    @patch("server._run_script_docker")
    def test_valid_dimensions_calls_run_script(self, mock_docker):
        mock_docker.return_value = "Created sprite: 16x16"
        result = create_sprite(16, 16)
        self.assertTrue(mock_docker.called)
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("NewFile", script_arg)
        self.assertIn("16", script_arg)


class TestSetPixels(unittest.TestCase):
    """Test the set_pixels tool."""

    def test_invalid_json(self):
        result = set_pixels("not json")
        self.assertIn("Error", result)

    def test_empty_array(self):
        result = set_pixels("[]")
        self.assertIn("Error", result)

    def test_missing_fields(self):
        result = set_pixels('[{"x": 0, "y": 0}]')
        self.assertIn("Error", result)
        self.assertIn("color", result)

    def test_invalid_color(self):
        result = set_pixels('[{"x": 0, "y": 0, "color": "xyz"}]')
        self.assertIn("Error", result)

    @patch("server._run_script_docker")
    def test_valid_pixels_calls_run_script(self, mock_docker):
        mock_docker.return_value = 'Set 2 pixel(s).'
        result = set_pixels(
            '[{"x": 0, "y": 0, "color": "#ff0000"},'
            ' {"x": 1, "y": 0, "color": "#00ff00"}]'
        )
        self.assertTrue(mock_docker.called)
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("putPixel", script_arg)
        self.assertIn("255, 0, 0", script_arg)
        self.assertIn("0, 255, 0", script_arg)

    def test_non_array_json(self):
        result = set_pixels('{"x": 0}')
        self.assertIn("Error", result)

    def test_non_object_element(self):
        result = set_pixels('[42]')
        self.assertIn("Error", result)


class TestDrawRect(unittest.TestCase):
    """Test the draw_rect tool."""

    def test_zero_width(self):
        result = draw_rect(0, 0, 0, 5, "#ff0000")
        self.assertIn("Error", result)

    def test_zero_height(self):
        result = draw_rect(0, 0, 5, 0, "#ff0000")
        self.assertIn("Error", result)

    def test_invalid_color(self):
        result = draw_rect(0, 0, 5, 5, "bad")
        self.assertIn("Invalid", result)

    @patch("server._run_script_docker")
    def test_valid_rect_calls_run_script(self, mock_docker):
        mock_docker.return_value = "Drew rectangle 5x5 at (0,0)"
        result = draw_rect(0, 0, 5, 5, "#ff0000")
        self.assertTrue(mock_docker.called)
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("putPixel", script_arg)
        self.assertIn("255, 0, 0", script_arg)


class TestFillSprite(unittest.TestCase):
    """Test the fill_sprite tool."""

    def test_invalid_color(self):
        result = fill_sprite("bad")
        self.assertIn("Invalid", result)

    @patch("server._run_script_docker")
    def test_valid_fill_calls_run_script(self, mock_docker):
        mock_docker.return_value = "Filled sprite with #0000ff"
        result = fill_sprite("#0000ff")
        self.assertTrue(mock_docker.called)
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("clear", script_arg)
        self.assertIn("0, 0, 255", script_arg)


class TestDrawImage(unittest.TestCase):
    """Test the draw_image tool."""

    def test_invalid_width(self):
        result = draw_image(0, 2, '["ff0000","00ff00"]')
        self.assertIn("Error", result)

    def test_invalid_height(self):
        result = draw_image(2, 0, '["ff0000","00ff00"]')
        self.assertIn("Error", result)

    def test_invalid_json(self):
        result = draw_image(2, 2, "not json")
        self.assertIn("Error", result)

    def test_wrong_pixel_count(self):
        result = draw_image(2, 2, '["ff0000","00ff00","0000ff"]')
        self.assertIn("expected 4", result)

    def test_invalid_color_in_array(self):
        result = draw_image(2, 1, '["ff0000","xyz"]')
        self.assertIn("Error", result)

    def test_non_array_json(self):
        result = draw_image(1, 1, '{"color":"ff0000"}')
        self.assertIn("Error", result)

    @patch("server._run_script_docker")
    def test_transparent_pixel(self, mock_docker):
        """The '.' sentinel should be treated as transparent."""
        mock_docker.return_value = "ok"
        # Validation should pass — '.' is a valid transparent pixel.
        result = draw_image(1, 1, '["."]')
        # Should not raise a colour-validation error.
        self.assertNotIn("Invalid", result)
        # Should have called through to run_script successfully.
        self.assertTrue(mock_docker.called)

    @patch("server._run_script_docker")
    def test_transparent_pixel_generates_zeros(self, mock_docker):
        """Transparent '.' pixels should produce 0,0,0,0 RGBA values."""
        mock_docker.return_value = "ok"
        draw_image(1, 1, '["."]')
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("0,0,0,0", script_arg)

    @patch("server._run_script_docker")
    def test_valid_image_calls_run_script(self, mock_docker):
        mock_docker.return_value = "Drew image: 2x2 (4 pixels)"
        result = draw_image(
            2, 2, '["ff0000","00ff00","0000ff","ffff00"]'
        )
        self.assertTrue(mock_docker.called)
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("putImageData", script_arg)
        self.assertIn("NewFile", script_arg)
        self.assertIn("Uint8Array", script_arg)
        # Check that RGBA values appear (ff0000 → 255,0,0,255)
        self.assertIn("255,0,0,255", script_arg)

    @patch("server._run_script_docker")
    def test_uses_put_image_data_not_put_pixel(self, mock_docker):
        """draw_image must use putImageData for efficiency, not putPixel."""
        mock_docker.return_value = "ok"
        draw_image(2, 1, '["ff0000","00ff00"]')
        script_arg = mock_docker.call_args[0][0]
        self.assertIn("putImageData", script_arg)
        self.assertNotIn("putPixel", script_arg)


class TestGetSpriteInfo(unittest.TestCase):
    """Test the get_sprite_info tool."""

    def test_docker_mode_no_sprites(self):
        """When no sprites exist, should say so."""
        with patch("server.OUTPUT_DIR", "/nonexistent/path"):
            result = get_sprite_info()
        self.assertIn("No sprites", result)

    def test_docker_mode_reads_png_info(self):
        """Should return width/height/colorMode from a generated PNG."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "test.png")
            _create_blank_png(png_path, 32, 16)
            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_sprite_info()
        self.assertIn("width:32", result)
        self.assertIn("height:16", result)
        self.assertIn("colorMode:RGBA", result)
        self.assertIn("layerCount:1", result)
        self.assertIn("filename:test.png", result)


class TestGetPixelData(unittest.TestCase):
    """Test the get_pixel_data tool."""

    def test_docker_mode_no_sprites(self):
        """When no sprites exist, should say so."""
        with patch("server.OUTPUT_DIR", "/nonexistent/path"):
            result = get_pixel_data(0, 0)
        self.assertIn("No sprites", result)

    def test_docker_mode_reads_transparent_pixel(self):
        """A blank PNG should return transparent pixels."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "blank.png")
            _create_blank_png(png_path, 4, 4)
            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_pixel_data(0, 0)
        self.assertIn("(0,0):rgba(0,0,0,0)", result)

    def test_docker_mode_area_limit(self):
        """Large read areas should be rejected."""
        result = get_pixel_data(0, 0, width=100, height=100)
        self.assertIn("exceeds", result)

    def test_docker_mode_out_of_bounds(self):
        """Pixels outside the image should be labeled out-of-bounds."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "small.png")
            _create_blank_png(png_path, 2, 2)
            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_pixel_data(5, 5)
        self.assertIn("out-of-bounds", result)


class TestScreenshot(unittest.TestCase):
    """Test the screenshot tool."""

    def test_docker_mode_no_output_dir(self):
        """When the output directory doesn't exist, return an error string."""
        with patch("server.OUTPUT_DIR", "/nonexistent/path"):
            result = screenshot()
        self.assertIsInstance(result, str)
        self.assertIn("No output directory", result)

    def test_docker_mode_empty_output_dir(self):
        """When the output directory is empty, return an informative message."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("server.OUTPUT_DIR", tmpdir):
                result = screenshot()
        self.assertIsInstance(result, str)
        self.assertIn("No sprites generated", result)

    def test_docker_mode_returns_image_for_existing_png(self):
        """When a PNG exists in output, return a list with TextContent and ImageContent."""
        import tempfile
        from mcp.types import TextContent, ImageContent

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal PNG file
            png_path = os.path.join(tmpdir, "test-sprite.png")
            server._create_blank_png(png_path, 4, 4)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = screenshot()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], TextContent)
        self.assertIn("test-sprite.png", result[0].text)
        self.assertIsInstance(result[1], ImageContent)
        self.assertEqual(result[1].mimeType, "image/png")

    def test_docker_mode_returns_most_recent_png(self):
        """Should return the most recently modified PNG."""
        import tempfile
        import time
        from mcp.types import TextContent

        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old.png")
            server._create_blank_png(old_path, 4, 4)
            time.sleep(0.05)
            new_path = os.path.join(tmpdir, "new.png")
            server._create_blank_png(new_path, 4, 4)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = screenshot()

        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], TextContent)
        self.assertIn("new.png", result[0].text)

    @patch("server.MODE", "relay")
    def test_relay_mode_no_proxy(self):
        """In relay mode with no proxy, return an error string."""
        with patch("server._proxy", None):
            result = screenshot()
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)

    @patch("server.MODE", "relay")
    def test_relay_mode_no_active_image(self):
        """Relay mode with no active sprite returns the fallback message."""
        mock_proxy = MagicMock()
        mock_proxy.run_script.return_value = "No active sprite. Create one first."
        with patch("server._proxy", mock_proxy):
            result = screenshot()
        self.assertIsInstance(result, str)
        self.assertIn("No active sprite", result)

    @patch("server.MODE", "relay")
    def test_relay_mode_returns_image_from_raw_imgdata(self):
        """Relay mode should decode hex RGBA data and return an ImageContent."""
        from mcp.types import TextContent, ImageContent

        # 2x2 red pixels: RGBA = ff000000ff for each (but fully opaque)
        # Each pixel: R=ff G=00 B=00 A=ff => "ff0000ff"
        hex_data = "ff0000ff" * 4  # 2x2 = 4 pixels
        mock_proxy = MagicMock()
        mock_proxy.run_script.return_value = (
            f"__MCP_IMGDATA__:2:2:{hex_data}\n"
        )
        with patch("server._proxy", mock_proxy):
            result = screenshot()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], TextContent)
        self.assertEqual(result[0].text, "Current sprite preview:")
        self.assertIsInstance(result[1], ImageContent)
        self.assertEqual(result[1].mimeType, "image/png")

    @patch("server.MODE", "relay")
    def test_relay_mode_legacy_png_fallback(self):
        """Relay mode should still handle __MCP_PNG__ base64 as fallback."""
        import base64
        from mcp.types import TextContent, ImageContent

        # Build a tiny valid PNG in memory using the server helper
        rgba_data = b"\x00\x00\x00\x00" * 4  # 2x2 transparent
        png_bytes = server._rgba_to_png(rgba_data, 2, 2)
        png_b64 = base64.b64encode(png_bytes).decode()

        mock_proxy = MagicMock()
        mock_proxy.run_script.return_value = f"__MCP_PNG__:{png_b64}"
        with patch("server._proxy", mock_proxy):
            result = screenshot()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], TextContent)
        self.assertEqual(result[0].text, "Current sprite preview:")
        self.assertIsInstance(result[1], ImageContent)
        self.assertEqual(result[1].mimeType, "image/png")

    @patch("server.MODE", "relay")
    def test_relay_mode_script_uses_get_image_data(self):
        """The relay script should call getImageData on the active image."""
        mock_proxy = MagicMock()
        mock_proxy.run_script.return_value = "No active sprite."
        with patch("server._proxy", mock_proxy):
            screenshot()
        script_arg = mock_proxy.run_script.call_args[0][0]
        self.assertIn("getImageData", script_arg)
        self.assertIn("app.activeImage", script_arg)


class TestPromptMentionsScreenshot(unittest.TestCase):
    """Test that the prompt mentions the screenshot tool."""

    def test_prompt_mentions_screenshot(self):
        result = libresprite("test")
        self.assertIn("screenshot", result)

    def test_prompt_mentions_visual_feedback(self):
        result = libresprite("test")
        self.assertIn("VISUAL FEEDBACK", result)


class TestRelayProxyInit(unittest.TestCase):
    """Test that the relay proxy can be configured for container use."""

    def test_proxy_accepts_all_interfaces_host(self):
        """Relay mode in a container binds to 0.0.0.0 to accept connections."""
        from server import LibrespriteProxy

        proxy = LibrespriteProxy(host="0.0.0.0", port=64823)
        self.assertEqual(proxy.host, "0.0.0.0")
        self.assertEqual(proxy.port, 64823)

    def test_proxy_default_host_is_localhost(self):
        from server import LibrespriteProxy

        proxy = LibrespriteProxy()
        self.assertEqual(proxy.host, "localhost")
        self.assertEqual(proxy.port, 64823)

    def test_proxy_custom_port(self):
        from server import LibrespriteProxy

        proxy = LibrespriteProxy(host="0.0.0.0", port=9999)
        self.assertEqual(proxy.port, 9999)

    def test_proxy_has_flask_app(self):
        from server import LibrespriteProxy

        proxy = LibrespriteProxy(host="0.0.0.0", port=64823)
        self.assertIsNotNone(proxy.app)

    def test_proxy_ping_endpoint(self):
        """The /ping endpoint should return a pong status."""
        from server import LibrespriteProxy

        proxy = LibrespriteProxy(host="0.0.0.0", port=64823)
        with proxy.app.test_client() as client:
            resp = client.get("/ping")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json(), {"status": "pong"})


# ---------------------------------------------------------------------------
# PNG reader helpers
# ---------------------------------------------------------------------------


class TestReadPngInfo(unittest.TestCase):
    """Test the _read_png_info helper."""

    def test_reads_dimensions(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            _create_blank_png(f.name, 48, 24)
            info = _read_png_info(f.name)
        os.unlink(f.name)
        self.assertEqual(info["width"], 48)
        self.assertEqual(info["height"], 24)
        self.assertEqual(info["color_mode"], "RGBA")

    def test_invalid_file_raises(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("not a png")
        with self.assertRaises(ValueError):
            _read_png_info(f.name)
        os.unlink(f.name)


class TestReadPngPixels(unittest.TestCase):
    """Test the _read_png_pixels helper."""

    def test_blank_png_all_transparent(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            _create_blank_png(f.name, 4, 4)
            rgba, w, h = _read_png_pixels(f.name)
        os.unlink(f.name)
        self.assertEqual(w, 4)
        self.assertEqual(h, 4)
        self.assertEqual(len(rgba), 4 * 4 * 4)
        # Every byte should be 0 (transparent black)
        self.assertTrue(all(b == 0 for b in rgba))

    def test_colored_png_roundtrip(self):
        """Build a PNG from known RGBA data and verify decode matches."""
        import tempfile

        w, h = 3, 2
        # 6 pixels: red, green, blue, yellow, magenta, cyan — all opaque
        raw = (
            b"\xff\x00\x00\xff"  # red
            b"\x00\xff\x00\xff"  # green
            b"\x00\x00\xff\xff"  # blue
            b"\xff\xff\x00\xff"  # yellow
            b"\xff\x00\xff\xff"  # magenta
            b"\x00\xff\xff\xff"  # cyan
        )
        png_bytes = _rgba_to_png(raw, w, h)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            path = f.name
        decoded, dw, dh = _read_png_pixels(path)
        os.unlink(path)
        self.assertEqual(dw, w)
        self.assertEqual(dh, h)
        self.assertEqual(decoded, raw)


class TestGetLatestSpritePath(unittest.TestCase):
    """Test the _get_latest_sprite_path helper."""

    def test_nonexistent_dir_returns_none(self):
        with patch("server.OUTPUT_DIR", "/no/such/dir"):
            result = _get_latest_sprite_path()
        self.assertIsNone(result)

    def test_empty_dir_returns_none(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("server.OUTPUT_DIR", tmpdir):
                result = _get_latest_sprite_path()
        self.assertIsNone(result)

    def test_returns_most_recent(self):
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.path.join(tmpdir, "old.png")
            _create_blank_png(old, 4, 4)
            time.sleep(0.05)
            new = os.path.join(tmpdir, "new.png")
            _create_blank_png(new, 8, 8)
            with patch("server.OUTPUT_DIR", tmpdir):
                result = _get_latest_sprite_path()
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("new.png"))


# ---------------------------------------------------------------------------
# Docker-mode integration: create sprite → query with tools
# ---------------------------------------------------------------------------


class TestDockerModeCreateThenGetInfo(unittest.TestCase):
    """Create a sprite in Docker mode and then use get_sprite_info to read it."""

    def test_create_blank_then_get_info(self):
        """create_sprite → get_sprite_info should return correct dimensions."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate what _run_script_docker does: save a PNG in OUTPUT_DIR
            png_path = os.path.join(tmpdir, "sprite.png")
            _create_blank_png(png_path, 32, 32)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_sprite_info()

        self.assertIn("width:32", result)
        self.assertIn("height:32", result)
        self.assertIn("colorMode:RGBA", result)
        self.assertIn("layerCount:1", result)

    def test_create_small_sprite_then_get_info(self):
        """Create a 8x8 sprite and verify info."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "tiny.png")
            _create_blank_png(png_path, 8, 8)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_sprite_info()

        self.assertIn("width:8", result)
        self.assertIn("height:8", result)
        self.assertIn("filename:tiny.png", result)


class TestDockerModeCreateThenGetPixels(unittest.TestCase):
    """Create a sprite in Docker mode and use get_pixel_data to read pixels."""

    def test_blank_sprite_pixels_are_transparent(self):
        """A blank sprite should have all transparent pixels."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "blank.png")
            _create_blank_png(png_path, 8, 8)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_pixel_data(0, 0, width=2, height=2)

        self.assertIn("(0,0):rgba(0,0,0,0)", result)
        self.assertIn("(1,0):rgba(0,0,0,0)", result)
        self.assertIn("(0,1):rgba(0,0,0,0)", result)
        self.assertIn("(1,1):rgba(0,0,0,0)", result)

    def test_colored_sprite_pixels(self):
        """Build a sprite with known colors and verify get_pixel_data."""
        import tempfile

        w, h = 4, 4
        # Fill with solid red
        raw = b"\xff\x00\x00\xff" * (w * h)
        png_bytes = _rgba_to_png(raw, w, h)

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "red.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_pixel_data(0, 0, width=2, height=2)

        self.assertIn("(0,0):rgba(255,0,0,255)", result)
        self.assertIn("(1,0):rgba(255,0,0,255)", result)
        self.assertIn("(0,1):rgba(255,0,0,255)", result)
        self.assertIn("(1,1):rgba(255,0,0,255)", result)

    def test_mixed_colors(self):
        """Create a 2x2 sprite with distinct colors and read each pixel."""
        import tempfile

        raw = (
            b"\xff\x00\x00\xff"  # (0,0) red
            b"\x00\xff\x00\xff"  # (1,0) green
            b"\x00\x00\xff\xff"  # (0,1) blue
            b"\xff\xff\x00\xff"  # (1,1) yellow
        )
        png_bytes = _rgba_to_png(raw, 2, 2)

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "mixed.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_pixel_data(0, 0, width=2, height=2)

        self.assertIn("(0,0):rgba(255,0,0,255)", result)
        self.assertIn("(1,0):rgba(0,255,0,255)", result)
        self.assertIn("(0,1):rgba(0,0,255,255)", result)
        self.assertIn("(1,1):rgba(255,255,0,255)", result)

    def test_read_subregion(self):
        """Reading a subregion of a larger sprite returns correct pixels."""
        import tempfile

        # 4x4 sprite, all green
        raw = b"\x00\xff\x00\xff" * 16
        png_bytes = _rgba_to_png(raw, 4, 4)

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "green.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)

            with patch("server.OUTPUT_DIR", tmpdir):
                # Read 2x2 region starting at (1,1)
                result = get_pixel_data(1, 1, width=2, height=2)

        self.assertIn("(1,1):rgba(0,255,0,255)", result)
        self.assertIn("(2,1):rgba(0,255,0,255)", result)
        self.assertIn("(1,2):rgba(0,255,0,255)", result)
        self.assertIn("(2,2):rgba(0,255,0,255)", result)
        # Should NOT contain (0,0)
        self.assertNotIn("(0,0)", result)

    def test_partial_alpha(self):
        """Pixels with partial transparency should be read correctly."""
        import tempfile

        # Single pixel with 50% alpha
        raw = b"\x80\x40\x20\x80"  # rgba(128, 64, 32, 128)
        png_bytes = _rgba_to_png(raw, 1, 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "alpha.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)

            with patch("server.OUTPUT_DIR", tmpdir):
                result = get_pixel_data(0, 0)

        self.assertIn("(0,0):rgba(128,64,32,128)", result)


class TestDockerModeEndToEndWorkflow(unittest.TestCase):
    """Simulate a complete Docker-mode workflow: create → draw → query."""

    def test_draw_image_then_read_info_and_pixels(self):
        """draw_image creates a sprite; get_sprite_info and get_pixel_data
        should both work on pngs generated by _rgba_to_png."""
        import tempfile

        # 3x3 sprite — red center, transparent border
        raw = (
            b"\x00\x00\x00\x00" b"\x00\x00\x00\x00" b"\x00\x00\x00\x00"
            b"\x00\x00\x00\x00" b"\xff\x00\x00\xff" b"\x00\x00\x00\x00"
            b"\x00\x00\x00\x00" b"\x00\x00\x00\x00" b"\x00\x00\x00\x00"
        )
        png_bytes = _rgba_to_png(raw, 3, 3)

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "cross.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)

            with patch("server.OUTPUT_DIR", tmpdir):
                info = get_sprite_info()
                center = get_pixel_data(1, 1)
                corner = get_pixel_data(0, 0)

        # Info
        self.assertIn("width:3", info)
        self.assertIn("height:3", info)
        # Center pixel is red
        self.assertIn("(1,1):rgba(255,0,0,255)", center)
        # Corner pixel is transparent
        self.assertIn("(0,0):rgba(0,0,0,0)", corner)

    def test_multiple_sprites_reads_latest(self):
        """When multiple sprites exist, tools read the most recent one."""
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            # Older sprite: 4x4 red
            old_path = os.path.join(tmpdir, "old.png")
            old_raw = b"\xff\x00\x00\xff" * 16
            with open(old_path, "wb") as f:
                f.write(_rgba_to_png(old_raw, 4, 4))
            time.sleep(0.05)

            # Newer sprite: 8x8 blue
            new_path = os.path.join(tmpdir, "new.png")
            new_raw = b"\x00\x00\xff\xff" * 64
            with open(new_path, "wb") as f:
                f.write(_rgba_to_png(new_raw, 8, 8))

            with patch("server.OUTPUT_DIR", tmpdir):
                info = get_sprite_info()
                pixel = get_pixel_data(0, 0)

        # Should reflect the newer 8x8 blue sprite
        self.assertIn("width:8", info)
        self.assertIn("height:8", info)
        self.assertIn("filename:new.png", info)
        self.assertIn("(0,0):rgba(0,0,255,255)", pixel)


if __name__ == "__main__":
    unittest.main()
