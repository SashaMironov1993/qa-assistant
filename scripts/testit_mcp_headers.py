"""Supply Test IT MCP headers from the project's .env to Codex.

stdout contains credentials and must only be consumed by the MCP client.
Do not run this file directly in a shared terminal or copy its output.
"""

import json
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urlsplit


def read_settings(env_path):
    """Read the two single-line settings without expanding $ or ${...}."""
    values = {}
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        raise ValueError("The project's .env file is missing.") from None
    for number, line in enumerate(lines, 1):
        match = re.match(
            r"\s*(?:export\s+)?(URL_TESTIT_ADDRESS|TOKEN_TEST_ID)\s*=\s*(.*)$",
            line,
        )
        if not match:
            continue
        name, value = match.groups()
        if value.startswith(("'", '"')):
            try:
                parts = shlex.split(value, comments=True, posix=True)
            except ValueError:
                raise ValueError(f"Invalid quoting for {name} on .env line {number}.") from None
            if len(parts) != 1:
                raise ValueError(f"Expected a single-line value for {name} on .env line {number}.")
            value = parts[0]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[name] = value
    return values


def connection_settings():
    project_root = Path(__file__).resolve().parent.parent
    values = read_settings(project_root / ".env")
    base_url = (values.get("URL_TESTIT_ADDRESS") or "").strip().rstrip("/")
    token = (values.get("TOKEN_TEST_ID") or "").strip()
    address = urlsplit(base_url)
    if (
        address.scheme != "https"
        or not address.hostname
        or address.username
        or address.password
        or address.query
        or address.fragment
        or any(char in base_url + token for char in "\r\n")
    ):
        raise ValueError("Check URL_TESTIT_ADDRESS: an HTTPS base URL is required.")
    if not token:
        raise ValueError("TOKEN_TEST_ID is missing or empty.")
    if token.lower().startswith("privatetoken "):
        token = token.split(None, 1)[1]
    return base_url, {"X-baseurl": base_url, "X-token": token}


def main():
    try:
        _, headers = connection_settings()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(headers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
