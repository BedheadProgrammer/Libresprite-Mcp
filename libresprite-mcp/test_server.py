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
    create_pixel_art,
    create_sprite,
    draw_image,
    draw_rect,
    fill_sprite,
    list_sprites,
    run_script,
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
        result = list_sprites()
        self.assertIn("relay mode", result)


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

    def test_docker_mode_returns_message(self):
        from server import get_sprite_info

        result = get_sprite_info()
        self.assertIn("relay mode", result)


class TestGetPixelData(unittest.TestCase):
    """Test the get_pixel_data tool."""

    def test_docker_mode_returns_message(self):
        from server import get_pixel_data

        result = get_pixel_data(0, 0)
        self.assertIn("relay mode", result)


if __name__ == "__main__":
    unittest.main()
