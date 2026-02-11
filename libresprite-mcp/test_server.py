"""Tests for LibreSprite MCP server logic.

These tests validate the Lua sandboxing, input validation, and helper
functions without requiring Docker or LibreSprite to be installed.
"""

import os
import sys
import unittest

# Add the project directory to the path so we can import server
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from server import _validate_lua_code, _build_sandboxed_script


class TestLuaValidation(unittest.TestCase):
    """Test that blocked Lua patterns are correctly detected."""

    def test_blocks_os_execute(self):
        self.assertIsNotNone(_validate_lua_code('os.execute("rm -rf /")'))

    def test_blocks_os_remove(self):
        self.assertIsNotNone(_validate_lua_code('os.remove("/etc/passwd")'))

    def test_blocks_io_open(self):
        self.assertIsNotNone(_validate_lua_code('io.open("/etc/passwd", "r")'))

    def test_blocks_io_popen(self):
        self.assertIsNotNone(_validate_lua_code('io.popen("ls")'))

    def test_blocks_loadfile(self):
        self.assertIsNotNone(_validate_lua_code('loadfile("evil.lua")'))

    def test_blocks_dofile(self):
        self.assertIsNotNone(_validate_lua_code('dofile("evil.lua")'))

    def test_blocks_require(self):
        self.assertIsNotNone(_validate_lua_code('require("os")'))

    def test_blocks_debug(self):
        self.assertIsNotNone(_validate_lua_code("debug.getinfo(1)"))

    def test_blocks_load_function(self):
        self.assertIsNotNone(_validate_lua_code('load("return 1")()'))

    def test_blocks_package(self):
        self.assertIsNotNone(_validate_lua_code("package.path"))

    def test_allows_safe_sprite_code(self):
        safe_code = """
local spr = Sprite(32, 32)
app.useTool{
    tool="filled_rectangle",
    color=Color(255, 0, 0),
    points={Point(0,0), Point(31,31)}
}
"""
        self.assertIsNone(_validate_lua_code(safe_code))

    def test_allows_app_commands(self):
        self.assertIsNone(_validate_lua_code("app.command.Clear()"))

    def test_allows_sprite_operations(self):
        code = 'local s = Sprite(16, 16)\ns:saveCopyAs("/app/output/test.png")'
        self.assertIsNone(_validate_lua_code(code))

    def test_blocks_os_execute_with_spaces(self):
        self.assertIsNotNone(_validate_lua_code('os . execute("bad")'))

    def test_blocks_io_open_with_spaces(self):
        self.assertIsNotNone(_validate_lua_code('io . open("bad")'))


class TestSandboxedScript(unittest.TestCase):
    """Test that the sandbox wrapper is generated correctly."""

    def test_contains_user_code(self):
        user_code = "local spr = Sprite(32, 32)"
        script = _build_sandboxed_script(user_code, "/app/output/test.png")
        self.assertIn(user_code, script)

    def test_disables_os_execute(self):
        script = _build_sandboxed_script("print('hi')", "/app/output/test.png")
        self.assertIn("os.execute = nil", script)

    def test_disables_io_popen(self):
        script = _build_sandboxed_script("print('hi')", "/app/output/test.png")
        self.assertIn("io.popen = nil", script)

    def test_disables_require(self):
        script = _build_sandboxed_script("print('hi')", "/app/output/test.png")
        self.assertIn('rawset(_G, "require", nil)', script)

    def test_disables_debug(self):
        script = _build_sandboxed_script("print('hi')", "/app/output/test.png")
        self.assertIn('rawset(_G, "debug", nil)', script)

    def test_sets_output_path(self):
        script = _build_sandboxed_script("print('hi')", "/app/output/abc.png")
        self.assertIn('OUTPUT_PATH = "/app/output/abc.png"', script)

    def test_auto_save_footer(self):
        script = _build_sandboxed_script("print('hi')", "/app/output/test.png")
        self.assertIn("app.activeSprite:saveCopyAs(OUTPUT_PATH)", script)

    def test_sandbox_header_before_user_code(self):
        user_code = "-- MY USER CODE"
        script = _build_sandboxed_script(user_code, "/app/output/test.png")
        header_pos = script.index("os.execute = nil")
        user_pos = script.index("-- MY USER CODE")
        self.assertLess(header_pos, user_pos)


if __name__ == "__main__":
    unittest.main()
