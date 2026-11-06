"""Check the adapter over STDIO. Writes only with explicit --create-probe.

The probe is reused by exact name on subsequent runs, never duplicated or archived.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


PROJECT = "xxxx-xxxx-xxxx-xxxx-xxxx"
ATTRIBUTE = "xxxx-xxxx-xxxx-xxxx-xxxx"
FRONT = "xxxx-xxxx-xxxx-xxxx-xxxx"
NAME = "[Проверка MCP] Создание тест-кейса — 30.10.2026"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-probe", action="store_true")
    args = parser.parse_args()
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("testit_mcp_adapter.py"))],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    sequence = 0

    def send(method, params=None, notification=False):
        nonlocal sequence
        sequence += 1
        message = {"jsonrpc": "2.0", "method": method}
        if not notification:
            message["id"] = sequence
        if params is not None:
            message["params"] = params
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        if notification:
            return None
        reply = json.loads(process.stdout.readline())
        if reply.get("id") != sequence or "error" in reply:
            raise ValueError("Adapter protocol error")
        result = reply["result"]
        if isinstance(result, dict) and result.get("isError"):
            raise ValueError(json.dumps(result, ensure_ascii=False))
        return result

    def call(name, arguments):
        result = send("tools/call", {"name": name, "arguments": arguments})
        return json.loads(next(block["text"] for block in result["content"] if block["type"] == "text"))

    try:
        send("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                            "clientInfo": {"name": "testit-adapter-check", "version": "1.0"}})
        send("notifications/initialized", notification=True)
        tools = send("tools/list")["tools"]
        for name in ("create_work_item", "edit_work_item"):
            tool = next(tool for tool in tools if tool["name"] == name)
            schema = tool["inputSchema"]["properties"]["request"]["properties"]["attributes"]
            assert {"type": "array", "items": {"type": "string"}} in schema["anyOf"][0]["additionalProperties"]["anyOf"]
        project = call("get_project_by_id", {"id": PROJECT})
        print(json.dumps({"initialize": "ok", "tools": len(tools), "array_schema": "ok", "project": project["name"]}))
        if not args.create_probe:
            return 0
        items = call("search_project_work_items", {"request": {"projectId": PROJECT,
            "filter": {"name": NAME, "isDeleted": False}, "take": 100}})
        matches = [item for item in items if item["name"] == NAME]
        if len(matches) > 1:
            raise ValueError("Multiple probes found; no new case created")
        if matches:
            item = matches[0]
        else:
            item = call("create_work_item", {"request": {
                "projectId": PROJECT, "sectionId": "94f20238-ca4b-4572-a2a1-71dbcae7774b",
                "name": NAME, "entityTypeName": "TestCases", "state": "NeedsWork", "priority": "Lowest",
                "description": "Служебный тест-кейс для проверки создания через MCP по запросу пользователя. Не относится к требованиям продукта. Плановая длительность: 1 минута.",
                "duration": 60000, "attributes": {ATTRIBUTE: [FRONT]},
                "steps": [{"action": "Вызвать инструмент Test IT MCP get_projects с текущим подключением.",
                           "expected": "Запрос выполнен без ошибки авторизации; получен список доступных проектов."}],
            }})
        print(json.dumps({"probe_id": item["id"], "global_id": item.get("globalId"), "reused": bool(matches)}))
        saved = call("get_work_item", {"request": {"id": item["id"]}})
        assert saved["attributes"][ATTRIBUTE] == [FRONT], "Saved MultipleOptions mismatch"
        assert saved["duration"] == 60000 and len(saved["steps"]) == 1
        assert saved["name"] == NAME and saved["state"] == "NeedsWork"
        print("Read-back verification: front array, duration, step, name and state OK")
        return 0
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
