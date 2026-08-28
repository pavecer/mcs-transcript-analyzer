#!/usr/bin/env python3
"""Validate the workspace policy that blocks external browser sessions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".github" / "hooks" / "block_external_browser.py"
HOOK_CONFIG = ROOT / ".github" / "hooks" / "browser-policy.json"
INSTRUCTIONS = ROOT / ".github" / "instructions" / "browser-use.instructions.md"
BROWSER_DEPENDENCY_NAMES = {"playwright", "@playwright/test", "puppeteer", "puppeteer-core", "selenium-webdriver"}


def hook_decision(payload: dict[str, Any]) -> str:
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def main() -> None:
    errors: list[str] = []
    config = json.loads(HOOK_CONFIG.read_text(encoding="utf-8"))
    command = config.get("hooks", {}).get("PreToolUse", [{}])[0].get("command")
    if command != "python .github/hooks/block_external_browser.py":
        errors.append("PreToolUse hook does not invoke the external-browser blocker")

    instructions = INSTRUCTIONS.read_text(encoding="utf-8")
    for required in ("mcp_playwright", "shared page ID", "run_playwright_code", "Do not launch Chrome"):
        if required not in instructions:
            errors.append(f"browser instructions are missing: {required}")

    denied = [
        {"tool_name": "mcp_playwright2_browser_resize", "tool_input": {"width": 1440, "height": 900}},
        {"tool_name": "mcp_playwright_browser_navigate", "tool_input": {"url": "https://example.com"}},
        {"tool_name": "mcp_puppeteer_browser_launch", "tool_input": {"url": "https://example.com"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "npx playwright test"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "npx playwright@latest test"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "npm exec -- @playwright/test test"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "pnpm dlx puppeteer browsers install chrome"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "python3 -m playwright open https://example.com"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "open https://example.com"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "google-chrome-stable https://example.com"}},
        {"tool_name": "functions.run_in_terminal", "tool_input": {"command": "open -a 'Google Chrome' https://example.com"}},
        {"tool_name": "functions.powershell", "tool_input": {"command": "npx playwright test"}},
        {"tool_name": "run_playwright_code", "tool_input": {"code": "return await page.title();"}},
        {"tool_name": "run_playwright_code", "tool_input": {"pageId": "shared-page", "code": "return await page.context().newPage();"}},
        {"tool_name": "run_playwright_code", "tool_input": {"pageId": "shared-page", "code": "return await chromium.launch();"}},
        {"tool_name": "run_playwright_code", "tool_input": {"pageId": "shared-page", "code": "return await launchPersistentContext('/tmp/profile');"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "env CI=1 npx playwright@latest test"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "command npx playwright test"}},
        {"tool_name": "run_in_terminal", "tool_input": {"command": "sudo -n pnpm exec playwright test"}},
    ]
    allowed = [
        {"tool_name": "open_browser_page", "tool_input": {"url": "file:///workspace/site/index.html"}},
        {"tool_name": "read_page", "tool_input": {"pageId": "shared-page"}},
        {"tool_name": "run_playwright_code", "tool_input": {"pageId": "shared-page", "code": "return await page.title();"}},
        {"tool_name": "functions.run_in_terminal", "tool_input": {"command": "npm test"}},
        {"tool_name": "functions.run_in_terminal", "tool_input": {"command": "rg playwright .github/hooks"}},
        {"tool_name": "functions.powershell", "tool_input": {"command": "git status --short"}},
    ]
    for payload in denied:
        if hook_decision(payload) != "deny":
            errors.append(f"external browser payload was not denied: {payload['tool_name']}")
    for payload in allowed:
        if hook_decision(payload) != "allow":
            errors.append(f"shared-browser-safe payload was not allowed: {payload['tool_name']}")

    for package_path in ROOT.glob("**/package.json"):
        if "node_modules" in package_path.parts:
            continue
        package = json.loads(package_path.read_text(encoding="utf-8"))
        dependencies = set(package.get("dependencies", {})) | set(package.get("devDependencies", {}))
        forbidden = sorted(dependencies & BROWSER_DEPENDENCY_NAMES)
        if forbidden:
            errors.append(f"external browser dependencies are not allowed in {package_path.relative_to(ROOT)}: {forbidden}")
        scripts = package.get("scripts", {})
        for name, command_text in scripts.items():
            payload = {"tool_name": "run_in_terminal", "tool_input": {"command": command_text}}
            if hook_decision(payload) == "deny":
                errors.append(f"package script launches an external browser: {package_path.relative_to(ROOT)}#{name}")

    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            payload = {"tool_name": "run_in_terminal", "tool_input": {"command": stripped}}
            if hook_decision(payload) == "deny":
                errors.append(f"workflow contains an external browser launch: {workflow.relative_to(ROOT)}: {stripped}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print("PASS: external Playwright/Chrome launches are blocked and shared VS Code browser tools remain allowed")


if __name__ == "__main__":
    main()