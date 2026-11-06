"""Install the prepared MCP configuration in this project's Codex settings.

Run in the user's local terminal when the agent cannot write .codex/config.toml.
Existing configuration is preserved. The API token is never written to TOML.
"""

import json
import argparse
from datetime import datetime
from pathlib import Path
import re
import shlex
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from testit_mcp_headers import connection_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", action="store_true", help="Use the local MultipleOptions adapter")
    parser.add_argument("--replace-testit", action="store_true", help="Back up config and replace only the testit table")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    base_url, _ = connection_settings()
    helper = shlex.join([sys.executable, str(root / "scripts/testit_mcp_headers.py")])
    transport = [
        "command = " + json.dumps(sys.executable),
        "args = " + json.dumps([str(root / "scripts/testit_mcp_adapter.py")]),
    ] if args.adapter else [
        "url = " + json.dumps(base_url + "/mcp"),
        "http_headers_helper = " + json.dumps(helper),
    ]
    entry = "\n".join([
        "[mcp_servers.testit]",
        *transport,
        "enabled = true",
        "startup_timeout_sec = 30",
        "tool_timeout_sec = 60",
        'default_tools_approval_mode = "prompt"',
        "",
    ])
    target = root / ".codex/config.toml"
    current = target.read_text() if target.exists() else ""
    existing = tomllib.loads(current).get("mcp_servers", {}).get("testit")
    expected = tomllib.loads(entry)["mcp_servers"]["testit"]
    if existing is not None:
        if existing == expected:
            print("Test IT MCP is already configured for this project.")
            return 0
        if not args.replace_testit:
            raise ValueError("A different testit entry exists; use --replace-testit to back up and replace it.")
        pattern = r"(?m)^\s*\[mcp_servers\.testit\][^\n]*\n.*?(?=^\s*\[|\Z)"
        updated, count = re.subn(pattern, lambda match: entry + "\n", current, flags=re.DOTALL)
        if count != 1 or tomllib.loads(updated).get("mcp_servers", {}).get("testit") != expected:
            raise ValueError("Cannot safely replace the testit table.")
        before = tomllib.loads(current)
        after = tomllib.loads(updated)
        before.get("mcp_servers", {}).pop("testit", None)
        after.get("mcp_servers", {}).pop("testit", None)
        if before != after:
            raise ValueError("Other settings would change; configuration was not written.")
        backup = target.with_name("config.toml.backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        with backup.open("x") as output:
            output.write(current)
        target.write_text(updated)
        print("Updated testit MCP; previous configuration backed up to " + str(backup))
        print("Restart the Codex client to load the connection.")
        return 0
    updated = current.rstrip() + ("\n\n" if current.strip() else "") + entry
    tomllib.loads(updated)
    target.parent.mkdir(exist_ok=True)
    with target.open("a" if target.exists() else "x") as output:
        output.write(("\n\n" if current.strip() else "") + entry)
    print("Installed project MCP configuration: .codex/config.toml")
    print("Restart the Codex client to load the connection.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PermissionError:
        print("Cannot write .codex/config.toml from this environment. Run from your local terminal.", file=sys.stderr)
        sys.exit(2)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
