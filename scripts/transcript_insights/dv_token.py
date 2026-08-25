"""Silent-first Dataverse/Power Platform token helper.

Resolution order (no browser popup unless everything else fails):
  1. Azure CLI (`az account get-access-token`) - silent if `az login` was done once
  2. MSAL on-disk cache (silent refresh)
  3. Device code flow - prints a code instead of stealing focus with a browser
"""

from __future__ import annotations

import atexit
import json
import shutil
import subprocess
from pathlib import Path

import msal

CACHE_FILE = Path(__file__).resolve().parents[2] / ".msal_token_cache.json"


def _az_command(resource: str, tenant_id: str | None = None) -> list[str]:
    executable = shutil.which("az") or "az"
    arguments = [
        "account",
        "get-access-token",
        "--resource",
        resource,
        "-o",
        "json",
    ]
    if tenant_id:
        arguments.extend(["--tenant", tenant_id])
    if Path(executable).suffix.lower() in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", executable, *arguments]
    return [executable, *arguments]


def _az_token(resource: str, tenant_id: str | None = None) -> str | None:
    try:
        proc = subprocess.run(
            _az_command(resource, tenant_id),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)["accessToken"]
    except (ValueError, KeyError):
        return None


def _cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text(encoding="utf-8"))

    def _persist() -> None:
        if cache.has_state_changed:
            CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")
            CACHE_FILE.chmod(0o600)

    atexit.register(_persist)
    return cache


def get_token(tenant_id: str, client_id: str, scope: str, allow_interactive: bool = True) -> str:
    resource = scope[: -len("/.default")] if scope.endswith("/.default") else scope

    token = _az_token(resource, tenant_id)
    if token:
        return token

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=_cache(),
    )
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent([scope], account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

    if not allow_interactive:
        raise RuntimeError(f"No silent token available for {scope}. Run: az login --tenant {tenant_id}")

    flow = app.initiate_device_flow(scopes=[scope])
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed for {scope}: {flow}")
    print(f"\n[auth] {flow['message']}\n", flush=True)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Token acquisition failed for {scope}: {result.get('error_description', result)}")
    return result["access_token"]


def get_token_from_config(config_path: str | Path, which: str = "dataverse") -> tuple[str, str]:
    """Returns (token, dataverse_url) for the given config file."""
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    dv_url = cfg["dataverseUrl"].rstrip("/")
    scope = (
        cfg["oauth"].get("dataverseScope", f"{dv_url}/.default")
        if which == "dataverse"
        else cfg["oauth"]["scope"]
    )
    return get_token(cfg["tenantId"], cfg["oauth"]["clientId"], scope), dv_url
