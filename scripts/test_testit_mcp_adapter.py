"""Offline regression tests; never contact Test IT."""
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import install_testit_mcp

from testit_mcp_adapter import Adapter, patch_tools, serve, validate_request


class AdapterTests(unittest.TestCase):
    def test_install_preserves_other_settings_and_creates_backup(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".codex").mkdir()
            config = root / ".codex/config.toml"
            original = '[mcp_servers.pycharm]\nurl = "http://localhost:1234"\n\n[mcp_servers.testit]\nurl = "https://example.invalid/mcp"\n\n[features]\nexample = true\n'
            config.write_text(original)
            with patch.object(install_testit_mcp, "__file__", str(root / "scripts/install_testit_mcp.py")), patch.object(
                install_testit_mcp, "connection_settings", return_value=("https://example.invalid", {})
            ), patch("sys.argv", ["install_testit_mcp.py", "--adapter", "--replace-testit"]), patch("sys.stdout", io.StringIO()):
                self.assertEqual(0, install_testit_mcp.main())
            parsed = install_testit_mcp.tomllib.loads(config.read_text())
            self.assertEqual({"url": "http://localhost:1234"}, parsed["mcp_servers"]["pycharm"])
            self.assertTrue(parsed["features"]["example"])
            self.assertIn("command", parsed["mcp_servers"]["testit"])
            self.assertNotIn("url", parsed["mcp_servers"]["testit"])
            self.assertEqual(original, next((root / ".codex").glob("config.toml.backup-*")).read_text())

    def test_schema_accepts_array_and_keeps_other_tools(self):
        original = {"tools": [{"name": name, "inputSchema": {"properties": {
            "request": {"properties": {"attributes": {"type": "string"}}}}}}
            for name in ("create_work_item", "edit_work_item", "get_projects")]}
        result = patch_tools(original)
        for tool in result["tools"][:2]:
            value = tool["inputSchema"]["properties"]["request"]["properties"]["attributes"]
            types = value["anyOf"][0]["additionalProperties"]["anyOf"]
            self.assertIn({"type": "array", "items": {"type": "string"}}, types)
        self.assertEqual(original["tools"][2], result["tools"][2])
        self.assertEqual("string", original["tools"][0]["inputSchema"]["properties"]["request"]["properties"]["attributes"]["type"])

    def test_multiple_and_scalar_values_are_preserved(self):
        body = {"attributes": {"multi": ["front-id", "dms-id"], "single": "option-id", "text": "Text", "empty": []}}
        self.assertIs(body, validate_request({"request": body}))
        for invalid in (42, ["id", 42], {"id": "value"}):
            with self.assertRaises(ValueError):
                validate_request({"request": {"attributes": {"multi": invalid}}})

    def test_create_and_edit_send_native_arrays_to_rest(self):
        adapter = Adapter.__new__(Adapter)
        adapter.base_url = "https://example.invalid"
        adapter.token = "secret-test-token"
        adapter.rest = MagicMock()
        response = adapter.rest.request.return_value.__enter__.return_value
        response.status_code = 200
        response.content = b"{}"
        response.json.return_value = {"id": "probe-id"}
        body = {"attributes": {"multi": ["front-id"]}}
        for name, method in (("create_work_item", "POST"), ("edit_work_item", "PUT")):
            result = adapter.handle({"method": "tools/call", "params": {"name": name, "arguments": {"request": body}}})
            self.assertNotIn("isError", result)
            call = adapter.rest.request.call_args
            self.assertEqual(method, call.args[0])
            self.assertEqual(body, call.kwargs["json"])
            self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(2, adapter.rest.request.call_count)

    def test_invalid_value_does_not_send_request(self):
        adapter = Adapter.__new__(Adapter)
        adapter.rest = MagicMock()
        result = adapter.handle({"method": "tools/call", "params": {"name": "create_work_item", "arguments": {"request": {"attributes": {"multi": 1}}}}})
        self.assertTrue(result["isError"])
        adapter.rest.request.assert_not_called()

    def test_stdio_replies_without_notification_output(self):
        adapter = MagicMock()
        adapter.handle.return_value = {}
        source = io.StringIO('\n'.join(json.dumps(x) for x in [
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"}]) + '\n')
        sink = io.StringIO()
        serve(source, sink, adapter)
        self.assertEqual({"jsonrpc": "2.0", "id": 7, "result": {}}, json.loads(sink.getvalue()))


if __name__ == "__main__":
    unittest.main()
