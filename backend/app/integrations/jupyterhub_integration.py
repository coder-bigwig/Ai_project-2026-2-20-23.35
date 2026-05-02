from typing import Optional, Dict
import posixpath
import time
from urllib.parse import quote

import requests

from ..config import (
    JUPYTERHUB_INTERNAL_URL,
    JUPYTERHUB_PUBLIC_URL,
    JUPYTERHUB_API_TOKEN,
    JUPYTERHUB_REQUEST_TIMEOUT_SECONDS,
    JUPYTERHUB_START_TIMEOUT_SECONDS,
    JUPYTERHUB_USER_TOKEN_EXPIRES_SECONDS,
    JUPYTER_WORKSPACE_UI,
    ENABLE_CODE_SERVER,
)


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()

def _empty_notebook_json() -> dict:
    return {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def _jupyterhub_enabled() -> bool:
    return bool(JUPYTERHUB_INTERNAL_URL and JUPYTERHUB_API_TOKEN)


def _hub_api_url(path: str) -> str:
    normalized = (path or "").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return f"{JUPYTERHUB_INTERNAL_URL}{normalized}"


def _hub_headers(extra: Optional[dict] = None) -> dict:
    headers = {"Authorization": f"token {JUPYTERHUB_API_TOKEN}"} if JUPYTERHUB_API_TOKEN else {}
    if extra:
        headers.update(extra)
    return headers


def _hub_request(method: str, path: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", None)
    timeout = kwargs.pop("timeout", JUPYTERHUB_REQUEST_TIMEOUT_SECONDS)
    allow_redirects = kwargs.pop("allow_redirects", False)
    return requests.request(
        method,
        _hub_api_url(path),
        headers=_hub_headers(headers),
        timeout=timeout,
        allow_redirects=allow_redirects,
        **kwargs,
    )


def _ensure_hub_user_exists(username: str) -> bool:
    user = _normalize_text(username)
    if not user or not _jupyterhub_enabled():
        return False

    try:
        resp = _hub_request("GET", f"/hub/api/users/{quote(user)}")
        if resp.status_code == 200:
            return True
        if resp.status_code != 404:
            print(f"JupyterHub user lookup failed ({resp.status_code}): {resp.text[:200]}")
            return False
    except requests.RequestException as exc:
        print(f"JupyterHub user lookup error: {exc}")
        return False

    try:
        create_resp = _hub_request("POST", f"/hub/api/users/{quote(user)}")
        if create_resp.status_code in {201, 200}:
            return True
        if create_resp.status_code == 409:
            return True
        print(f"JupyterHub user create failed ({create_resp.status_code}): {create_resp.text[:200]}")
    except requests.RequestException as exc:
        print(f"JupyterHub user create error: {exc}")

    return False


def _ensure_user_server_running(username: str) -> bool:
    user = _normalize_text(username)
    if not user or not _jupyterhub_enabled():
        return False

    if not _ensure_hub_user_exists(user):
        return False

    try:
        current = _hub_request("GET", f"/hub/api/users/{quote(user)}")
        if current.status_code == 200:
            state = _extract_server_state(current.json() or {})
            if state.get("server_running") or state.get("server_pending"):
                return True
    except requests.RequestException:
        pass

    spawn_resp = None
    for attempt in range(3):
        try:
            resp = _hub_request("POST", f"/hub/api/users/{quote(user)}/server")
            spawn_resp = resp
            # 201/202: started, 409: already running
            if resp.status_code in {201, 202, 409}:
                break

            # Some JupyterHub versions return 400 with a message when the server is already running.
            if resp.status_code == 400:
                try:
                    payload = resp.json() or {}
                except ValueError:
                    payload = {}
                message = str(payload.get("message") or payload.get("detail") or resp.text or "")
                normalized_message = message.lower()
                if (
                    "already running" in normalized_message
                    or "is pending" in normalized_message
                    or "server pending" in normalized_message
                    or "spawn pending" in normalized_message
                ):
                    spawn_resp = None
                    break
                print(f"JupyterHub spawn failed ({resp.status_code}): {message[:200]}")
                return False

            body = str(resp.text or "")
            lowered = body.lower()
            # DockerSpawner can transiently return 500 if the previous single-user container
            # name has not been fully released yet. Briefly retry the spawn.
            is_name_conflict = (
                resp.status_code >= 500
                and ("already in use" in lowered or "conflict" in lowered)
                and "jupyter-" in lowered
            )
            if is_name_conflict and attempt < 2:
                time.sleep(1.5)
                continue

            print(f"JupyterHub spawn failed ({resp.status_code}): {body[:200]}")
            return False
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(1.0)
                continue
            print(f"JupyterHub spawn error: {exc}")
            return False

    deadline = time.time() + max(5.0, JUPYTERHUB_START_TIMEOUT_SECONDS)
    while time.time() < deadline:
        try:
            status = _hub_request("GET", f"/hub/api/users/{quote(user)}")
            if status.status_code != 200:
                time.sleep(1)
                continue
            payload = status.json()
            pending = payload.get("pending")
            if pending:
                time.sleep(1)
                continue

            server_field = payload.get("server")
            if server_field:
                return True

            servers = payload.get("servers")
            if isinstance(servers, dict):
                for srv in servers.values():
                    if srv:
                        if isinstance(srv, dict) and srv.get("pending"):
                            continue
                        return True
        except Exception:
            pass
        time.sleep(1)

    return False


def _wait_user_server_state(username: str, expect_running: bool, timeout_seconds: Optional[float] = None) -> bool:
    user = _normalize_text(username)
    if not user:
        return False

    deadline = time.time() + max(5.0, float(timeout_seconds or JUPYTERHUB_START_TIMEOUT_SECONDS))
    while time.time() < deadline:
        try:
            status = _hub_request("GET", f"/hub/api/users/{quote(user)}")
            if status.status_code == 404:
                return not expect_running
            if status.status_code != 200:
                time.sleep(1)
                continue

            payload = status.json() or {}
            state = _extract_server_state(payload)
            is_running = bool(state.get("server_running"))
            is_pending = bool(state.get("server_pending"))

            if expect_running and is_running:
                return True
            if not expect_running and (not is_running and not is_pending):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _stop_user_server(username: str) -> bool:
    user = _normalize_text(username)
    if not user or not _jupyterhub_enabled():
        return False

    try:
        user_resp = _hub_request("GET", f"/hub/api/users/{quote(user)}")
        if user_resp.status_code == 404:
            return True
        if user_resp.status_code != 200:
            print(f"JupyterHub user lookup failed ({user_resp.status_code}): {user_resp.text[:200]}")
            return False
    except requests.RequestException as exc:
        print(f"JupyterHub user lookup error: {exc}")
        return False

    try:
        stop_resp = _hub_request("DELETE", f"/hub/api/users/{quote(user)}/server")
        if stop_resp.status_code not in {202, 204, 404}:
            if stop_resp.status_code == 400:
                try:
                    payload = stop_resp.json() or {}
                except ValueError:
                    payload = {}
                message = str(payload.get("message") or payload.get("detail") or stop_resp.text or "")
                normalized_message = message.lower()
                if "not running" not in normalized_message and "no such server" not in normalized_message:
                    print(f"JupyterHub stop failed ({stop_resp.status_code}): {message[:200]}")
                    return False
            else:
                print(f"JupyterHub stop failed ({stop_resp.status_code}): {stop_resp.text[:200]}")
                return False
    except requests.RequestException as exc:
        print(f"JupyterHub stop error: {exc}")
        return False

    return _wait_user_server_state(user, expect_running=False)


def _create_short_lived_user_token(
    username: str,
    expires_in: int = JUPYTERHUB_USER_TOKEN_EXPIRES_SECONDS,
) -> Optional[str]:
    user = _normalize_text(username)
    if not user or not _jupyterhub_enabled():
        return None
    if not _ensure_hub_user_exists(user):
        return None

    try:
        resp = _hub_request(
            "POST",
            f"/hub/api/users/{quote(user)}/tokens",
            json={
                "note": "training-platform",
                "expires_in": int(expires_in),
            },
        )
        if resp.status_code not in {200, 201}:
            print(f"JupyterHub create token failed ({resp.status_code}): {resp.text[:200]}")
            return None
        return (resp.json() or {}).get("token")
    except requests.RequestException as exc:
        print(f"JupyterHub create token error: {exc}")
        return None


def _user_contents_url(username: str, path: str) -> str:
    user = _normalize_text(username)
    normalized_path = (path or "").lstrip("/")
    encoded_path = quote(normalized_path, safe="/")
    return f"{JUPYTERHUB_INTERNAL_URL}/user/{quote(user)}/api/contents/{encoded_path}"


def _user_contents_request(username: str, token: str, method: str, path: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", None) or {}
    headers = {**headers, "Authorization": f"token {token}"}
    timeout = kwargs.pop("timeout", JUPYTERHUB_REQUEST_TIMEOUT_SECONDS)
    allow_redirects = kwargs.pop("allow_redirects", False)
    return requests.request(
        method,
        _user_contents_url(username, path),
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        **kwargs,
    )


def _append_token(url: str, token: Optional[str]) -> str:
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}token={quote(token)}"


def _normalize_workspace_ui(value: Optional[str], *, default: str = "lab") -> str:
    normalized = _normalize_text(value).lower()
    if normalized in {"lab", "notebook", "code"}:
        return normalized
    return default


def _code_server_enabled() -> bool:
    return bool(ENABLE_CODE_SERVER and _jupyterhub_enabled())


def _build_user_jupyter_url(
    username: str,
    path: Optional[str] = None,
    token: Optional[str] = None,
    workspace_ui: str = "lab",
) -> str:
    user = _normalize_text(username)
    if not user:
        return ""

    normalized_ui = _normalize_workspace_ui(workspace_ui, default="lab")

    if normalized_ui == "notebook":
        if path:
            encoded_path = quote(path, safe="/")
            base = f"{JUPYTERHUB_PUBLIC_URL}/user/{quote(user)}/notebooks/{encoded_path}"
        else:
            base = f"{JUPYTERHUB_PUBLIC_URL}/user/{quote(user)}/tree"
    else:
        if path:
            encoded_path = quote(path, safe="/")
            base = f"{JUPYTERHUB_PUBLIC_URL}/user/{quote(user)}/lab/tree/{encoded_path}"
        else:
            base = f"{JUPYTERHUB_PUBLIC_URL}/user/{quote(user)}/lab"

    return _append_token(base, token)


def _build_user_lab_url(username: str, path: Optional[str] = None, token: Optional[str] = None) -> str:
    workspace_ui = JUPYTER_WORKSPACE_UI if JUPYTER_WORKSPACE_UI in {"notebook", "lab"} else "lab"
    return _build_user_jupyter_url(username, path=path, token=token, workspace_ui=workspace_ui)


def _build_code_server_folder(path: Optional[str] = None) -> str:
    base_folder = "/home/jovyan/work"
    normalized_path = _normalize_text(path).replace("\\", "/").lstrip("/")
    if not normalized_path:
        return base_folder

    relative_folder = normalized_path
    if posixpath.splitext(posixpath.basename(relative_folder))[1]:
        relative_folder = posixpath.dirname(relative_folder)
    relative_folder = posixpath.normpath(relative_folder).strip("/")

    if not relative_folder or relative_folder in {".", "work"}:
        return base_folder

    if relative_folder.startswith("work/"):
        relative_folder = relative_folder[len("work/"):]

    relative_folder = relative_folder.strip("/")
    if not relative_folder or relative_folder == ".":
        return base_folder

    return f"{base_folder}/{quote(relative_folder, safe='/')}"


def _build_user_code_url(username: str, path: Optional[str] = None, token: Optional[str] = None) -> str:
    user = _normalize_text(username)
    if not user:
        return ""
    folder = _build_code_server_folder(path)
    base = f"{JUPYTERHUB_PUBLIC_URL}/user/{quote(user)}/code-server/?folder={quote(folder, safe='/')}"
    return _append_token(base, token)


def _build_user_workspace_urls(username: str, path: Optional[str] = None, token: Optional[str] = None) -> Dict[str, str]:
    urls: Dict[str, str] = {
        "lab": _build_user_jupyter_url(username, path=path, token=token, workspace_ui="lab"),
    }

    if _normalize_workspace_ui(JUPYTER_WORKSPACE_UI) == "notebook":
        urls["notebook"] = _build_user_jupyter_url(username, path=path, token=token, workspace_ui="notebook")

    if _code_server_enabled():
        urls["code"] = _build_user_code_url(username, path=path, token=token)

    return {key: value for key, value in urls.items() if value}


def _default_workspace_ui() -> str:
    preferred = _normalize_workspace_ui(JUPYTER_WORKSPACE_UI, default="lab")
    if preferred == "code" and not _code_server_enabled():
        return "lab"
    return preferred


def _build_workspace_launch_payload(username: str, path: Optional[str] = None, token: Optional[str] = None) -> dict:
    workspace_urls = _build_user_workspace_urls(username, path=path, token=token)
    ordered_keys = ["lab", "notebook", "code"]
    available_workspaces = [key for key in ordered_keys if workspace_urls.get(key)]
    default_workspace_ui = _default_workspace_ui()
    if default_workspace_ui not in workspace_urls:
        default_workspace_ui = "lab" if workspace_urls.get("lab") else (available_workspaces[0] if available_workspaces else "lab")

    payload = {
        "jupyter_url": workspace_urls.get("lab", ""),
        "workspace_urls": workspace_urls,
        "available_workspaces": available_workspaces,
        "default_workspace_ui": default_workspace_ui,
    }
    if workspace_urls.get("notebook"):
        payload["notebook_url"] = workspace_urls["notebook"]
    if workspace_urls.get("code"):
        payload["code_server_url"] = workspace_urls["code"]
    return payload


def _hub_user_state_map() -> Dict[str, dict]:
    if not _jupyterhub_enabled():
        return {}
    try:
        resp = _hub_request("GET", "/hub/api/users")
        if resp.status_code != 200:
            return {}
        payload = resp.json()
        if not isinstance(payload, list):
            return {}
    except Exception:
        return {}

    result = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name"))
        if not name:
            continue
        result[name] = item
    return result


def _extract_server_state(hub_user: Optional[dict]) -> dict:
    payload = hub_user or {}
    pending = bool(payload.get("pending"))
    last_activity = payload.get("last_activity")
    server_started = ""
    running = False
    server_url = ""

    servers = payload.get("servers")
    if isinstance(servers, dict):
        for _, item in servers.items():
            if not item:
                continue
            if isinstance(item, dict):
                if item.get("pending"):
                    pending = True
                item_last_activity = item.get("last_activity")
                if item_last_activity and not last_activity:
                    last_activity = item_last_activity
                item_started = _normalize_text(item.get("started"))
                if item_started and not server_started:
                    server_started = item_started
                item_url = _normalize_text(item.get("url"))
                if item_url:
                    running = True
                    server_url = server_url or item_url
                elif item.get("ready"):
                    running = True
            else:
                running = True

    server_field = payload.get("server")
    if server_field:
        running = True
        if isinstance(server_field, str):
            server_url = server_url or server_field

    return {
        "server_running": running,
        "server_pending": pending,
        "server_url": server_url,
        "last_activity": last_activity,
        "server_started": server_started,
        "hub_admin": bool(payload.get("admin")),
    }
