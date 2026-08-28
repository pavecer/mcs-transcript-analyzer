#!/usr/bin/env python3
"""Deny tools and terminal commands that launch a browser outside VS Code."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


EXTERNAL_TOOL_PREFIXES = ("mcp_playwright", "mcp_playwright2", "mcp_puppeteer")
TERMINAL_TOOL_NAMES = {
    "bash",
    "functions.bash",
    "functions.powershell",
    "functions.run_in_terminal",
    "powershell",
    "run_in_terminal",
}
COMMAND_START = r"(?:^|[;&|]\s*)"
COMMAND_WRAPPER = r"(?:(?:env(?:\s+[A-Za-z_][A-Za-z0-9_]*=\S+)*|command|sudo(?:\s+-\S+)*)\s+)?"
EXTERNAL_COMMAND_PATTERNS = (
    re.compile(
        COMMAND_START + COMMAND_WRAPPER
        + r"(?:npx|bunx|pnpm\s+(?:exec|dlx)|yarn(?:\s+dlx)?|npm\s+(?:exec|x)(?:\s+--)?)\s+"
        r"(?:playwright|@playwright/test|puppeteer)(?:@[^\s;&|]+)?(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        COMMAND_START + COMMAND_WRAPPER
        + r"(?:\./)?(?:node_modules/\.bin/)?playwright(?:@[^\s;&|]+)?(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(COMMAND_START + COMMAND_WRAPPER + r"python(?:3)?\s+-m\s+(?:playwright|webbrowser)(?:\s|$)", re.IGNORECASE),
    re.compile(COMMAND_START + COMMAND_WRAPPER + r"(?:google-chrome(?:-stable)?|chrome|chromium(?:-browser)?)(?:\s|$)", re.IGNORECASE),
    re.compile(r"open\s+-a\s+[\"']?(?:Google Chrome|Chromium|Chrome)[\"']?", re.IGNORECASE),
    re.compile(r"(?:^|[;&|]\s*)open\s+(?:-[^\s]+\s+)*(?:https?://|file://|[^;&|]*\.html(?:\s|$))", re.IGNORECASE),
    re.compile(r"/Applications/(?:Google Chrome|Chromium|Chrome)\.app", re.IGNORECASE),
    re.compile(r"osascript\b[^\n]*(?:Google Chrome|Chromium|Chrome)", re.IGNORECASE),
)
PAGE_CREATION_PATTERNS = (
    re.compile(r"\bnewPage\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:chromium|firefox|webkit|browserType)\.launch", re.IGNORECASE),
    re.compile(r"\blaunchPersistentContext\s*\(", re.IGNORECASE),
)


def first_mapping(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def tool_name(payload: dict[str, Any]) -> str:
    value = payload.get("tool_name") or payload.get("toolName")
    if isinstance(value, str):
        return value
    tool = payload.get("tool")
    if isinstance(tool, dict) and isinstance(tool.get("name"), str):
        return tool["name"]
    return ""


def decision(permission: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": permission,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        decision("allow", "Browser policy received no readable tool payload.")
        return

    name = tool_name(payload)
    normalized = name.split(".")[-1].lower()
    if normalized.startswith(EXTERNAL_TOOL_PREFIXES):
        decision(
            "deny",
            "External Playwright/Chrome tools are blocked. Reuse the shared VS Code browser page ID.",
        )
        return

    inputs = first_mapping(payload, "tool_input", "toolInput", "input", "arguments")
    if normalized == "run_playwright_code" and not inputs.get("pageId"):
        decision(
            "deny",
            "run_playwright_code requires an existing shared VS Code browser pageId.",
        )
        return
    code = inputs.get("code") if normalized == "run_playwright_code" else None
    if isinstance(code, str) and any(pattern.search(code) for pattern in PAGE_CREATION_PATTERNS):
        decision(
            "deny",
            "Shared-page browser code may not create a new page or launch another browser.",
        )
        return
    command = inputs.get("command") if normalized in TERMINAL_TOOL_NAMES or name in TERMINAL_TOOL_NAMES else None
    if isinstance(command, str) and any(pattern.search(command) for pattern in EXTERNAL_COMMAND_PATTERNS):
        decision(
            "deny",
            "Terminal browser launch is blocked. Reuse the shared VS Code built-in browser.",
        )
        return

    decision("allow", "Tool does not launch an external browser.")


if __name__ == "__main__":
    main()