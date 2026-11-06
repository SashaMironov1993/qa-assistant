"""Inspect Test IT MCP capabilities without calling business tools.

Only initialize, notifications/initialized and tools/list or prompts/list
are sent. No tools/call, resource creation or business writes are performed.
"""

import json
import sys

import requests

from testit_mcp_headers import connection_settings


def read_reply(response, request_id):
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "application/json" in content_type:
        reply = response.json()
    elif "text/event-stream" in content_type:
        response.encoding = response.encoding or "utf-8"
        data = []
        reply = None
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line and data:
                event = json.loads("\n".join(data))
                data = []
                if isinstance(event, dict) and event.get("id") == request_id:
                    reply = event
                    break
        if reply is None:
            raise ValueError("No matching MCP response was received.")
    else:
        raise ValueError("The endpoint did not return JSON or an MCP event stream.")
    if not isinstance(reply, dict) or reply.get("id") != request_id:
        raise ValueError("Unexpected MCP response identifier.")
    if "error" in reply:
        code = reply["error"].get("code")
        raise ValueError(f"MCP returned error code {code}; server message omitted.")
    return reply["result"]


def main():
    base_url, headers = connection_settings()
    headers.update({"Accept": "application/json, text/event-stream"})
    endpoint = base_url + "/mcp"
    with requests.Session() as session:
        session.headers.update(headers)

        def request(method, request_id, params=None):
            body = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params is not None:
                body["params"] = params
            with session.post(
                endpoint, json=body, timeout=(8, 20),
                allow_redirects=False, stream=True,
            ) as response:
                if 300 <= response.status_code < 400:
                    raise ValueError("MCP redirected the request; redirect not followed.")
                if response.headers.get("Mcp-Session-Id"):
                    session.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
                return read_reply(response, request_id)

        result = request("initialize", 1, {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "testit-readonly-check", "version": "1.0"},
        })
        version = result["protocolVersion"]
        session.headers["MCP-Protocol-Version"] = version
        print(json.dumps({"initialize": "ok", "protocol_version": version}))
        with session.post(
            endpoint,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=(8, 20), allow_redirects=False,
        ) as response:
            if not 200 <= response.status_code < 300:
                raise ValueError("MCP initialization notification was not accepted.")

        request_id = 2
        capabilities = result.get("capabilities", {})
        for method, key in [("tools/list", "tools"), ("prompts/list", "prompts")]:
            if key not in capabilities:
                continue
            cursor = None
            while True:
                page = request(method, request_id, {"cursor": cursor} if cursor else {})
                request_id += 1
                for item in page.get(key, []):
                    summary = {"kind": key, "name": item.get("name")}
                    if key == "tools":
                        summary["read_only_hint"] = item.get("annotations", {}).get("readOnlyHint")
                    print(json.dumps(summary, ensure_ascii=False))
                cursor = page.get("nextCursor")
                if not cursor:
                    break
        print("No business tools were called.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.RequestException as error:
        message = str(error).lower()
        if "name resolution" in message or "nodename nor servname" in message:
            reason = "DNS resolution failed in this execution environment."
        elif "operation not permitted" in message or "permission denied" in message:
            reason = "Network access was denied by this execution environment."
        elif "certificate_verify_failed" in message:
            reason = "TLS certificate verification failed."
        elif isinstance(error, requests.HTTPError):
            reason = f"HTTP {error.response.status_code}; response body omitted."
        else:
            reason = type(error).__name__ + "; connection details omitted."
        print(reason, file=sys.stderr)
        sys.exit(2)
    except (ValueError, KeyError) as error:
        print(str(error) if isinstance(error, ValueError) else "Incomplete MCP response.", file=sys.stderr)
        sys.exit(2)
