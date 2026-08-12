---
name: Shared VS Code Browser Only
description: "Use for every browser, UI validation, screenshot, navigation, and responsive-layout task in this repository."
applyTo: "**"
---

# Browser Policy

- Reuse an already shared VS Code built-in browser page whenever one exists. `open_browser_page`
  may open a VS Code built-in page only when no suitable shared page is available.
- Use `open_browser_page`, `read_page`, `click_element`, `type_in_page`, `screenshot_page`, or
  `run_playwright_code` with the shared page ID. `run_playwright_code` is allowed only when it
  targets that existing page ID.
- Do not call any tool whose name starts with `mcp_playwright`, `mcp_playwright2`, or
  `mcp_puppeteer`. Those tools
  control a separate browser session, even when the operation sounds harmless, such as resize.
- Do not launch Chrome, Chromium, or Playwright from the terminal.
- If the shared browser lacks a required capability, explain the missing capability and ask the
  user before changing this policy. Do not silently fall back to an external browser.

The workspace PreToolUse hook enforces this policy. Run
`python3 scripts/validate_browser_policy.py` after changing the hook or these instructions.