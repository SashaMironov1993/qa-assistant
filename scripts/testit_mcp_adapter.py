"""STDIO bridge for Test IT MCP with native MultipleOptions attributes.

Only create_work_item/edit_work_item use REST. Other calls retain the upstream
MCP implementation. Credentials are read from .env and never logged.
"""

from copy import deepcopy
import json
import sys

import requests

from check_testit_mcp import read_reply
from testit_mcp_headers import connection_settings


REST_TOOLS = {"create_work_item": "POST", "edit_work_item": "PUT"}


def patch_tools(result):
    result = deepcopy(result)
    for tool in result.get("tools", []):
        if tool["name"] not in REST_TOOLS:
            continue
        schema = tool["inputSchema"]
        request = schema["properties"]["request"]
        # Resolve a local reference, if the upstream switches to $defs.
        if "$ref" in request:
            for part in request["$ref"].removeprefix("#/").split("/"):
                schema = schema[part]
            request = schema
        request["properties"]["attributes"] = {
            "description": "Attribute UUID to value. MultipleOptions: array of option UUIDs; options/text: string.",
            "anyOf": [
                {"type": "object", "additionalProperties": {"anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "null"},
                ]}},
                {"type": "null"},
            ],
        }
        # REST returns the entity, not the upstream wrapper's structured output.
        tool.pop("outputSchema", None)
    return result


def validate_request(arguments):
    body = arguments.get("request")
    if not isinstance(body, dict):
        raise ValueError("request must be an object")
    attributes = body.get("attributes")
    if attributes is not None:
        if not isinstance(attributes, dict):
            raise ValueError("attributes must be an object or null")
        for value in attributes.values():
            if value is None or isinstance(value, str):
                continue
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                continue
            raise ValueError("Attribute values must be strings, arrays of strings, or null")
    return body


class Adapter:
    def __init__(self):
        self.base_url, headers = connection_settings()
        self.token = headers["X-token"]
        self.mcp = requests.Session()
        self.mcp.headers.update(headers)
        self.mcp.headers["Accept"] = "application/json, text/event-stream"
        self.rest = requests.Session()
        self.rest.headers["Authorization"] = "PrivateToken " + self.token

    def close(self):
        self.mcp.close()
        self.rest.close()

    def upstream(self, message):
        with self.mcp.post(self.base_url + "/mcp", json=message,
                           timeout=(8, 55), allow_redirects=False, stream=True) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("MCP redirect refused")
            if response.headers.get("Mcp-Session-Id"):
                self.mcp.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
            if "id" not in message:
                response.raise_for_status()
                return None
            result = read_reply(response, message["id"])
        if message["method"] == "initialize":
            self.mcp.headers["MCP-Protocol-Version"] = result["protocolVersion"]
        return result

    def work_item(self, name, arguments):
        body = validate_request(arguments)
        # No automatic retries: an ambiguous timeout must not create duplicates.
        with self.rest.request(REST_TOOLS[name], self.base_url + "/api/v2/workItems",
                               json=body, timeout=(8, 55), allow_redirects=False) as response:
            if not 200 <= response.status_code < 300:
                detail = ""
                try:
                    error = response.json().get("error", {})
                    detail = str(error.get("key", "")).replace(self.token, "[redacted]")
                except (ValueError, AttributeError):
                    pass
                return {"isError": True, "content": [{"type": "text", "text":
                    f"Test IT REST HTTP {response.status_code}: {detail}"}]}
            value = response.json() if response.content else {"status": "ok"}
            return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}

    def handle(self, message):
        method = message["method"]
        params = message.get("params", {})
        if method == "ping":
            return {}
        if method == "tools/call" and params.get("name") in REST_TOOLS:
            try:
                return self.work_item(params["name"], params.get("arguments", {}))
            except (ValueError, requests.RequestException) as error:
                # Do not include requests' exception text, URLs, or headers.
                detail = str(error) if isinstance(error, ValueError) else type(error).__name__
                return {"isError": True, "content": [{"type": "text", "text":
                    "Work item request failed: " + detail}]}
        result = self.upstream(message)
        return patch_tools(result) if method == "tools/list" else result


def serve(source, sink, adapter):
    for line in source:
        message = None
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or not isinstance(message.get("method"), str):
                raise ValueError("Invalid JSON-RPC request")
            result = adapter.handle(message)
            reply = {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        except Exception:
            # Protocol errors must never expose tokens or an upstream traceback.
            reply = {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                     "error": {"code": -32603, "message": "Test IT adapter request failed"}}
        if isinstance(message, dict) and "id" not in message:
            continue
        sink.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sink.flush()


def main():
    try:
        adapter = Adapter()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        serve(sys.stdin, sys.stdout, adapter)
    finally:
        adapter.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
