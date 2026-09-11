"""GitHub Contents API helper, adapted from Lily's github/api.py."""

from __future__ import annotations

import base64
import os
from urllib.parse import quote

import requests

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    token = os.getenv("MCP_GIT_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("Set MCP_GIT_PAT, GH_TOKEN, or GITHUB_TOKEN for GitHub access")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def validate_path(path: str) -> None:
    if not isinstance(path, str) or not path or any(
        part in ("", ".", "..") for part in path.split("/")
    ) or "\\" in path or any(ord(c) < 32 for c in path):
        raise ValueError("path must be repo-relative without empty, . or .. segments")


def _url(owner: str, repo: str, path: str | None = None) -> str:
    url = f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
    if path is not None:
        validate_path(path)
        url += f"/contents/{quote(path, safe='/')}"
    return url


def _request(method: str, url: str, **kwargs) -> requests.Response:
    try:
        return requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
    except requests.RequestException as exc:
        # A failed write may have reached GitHub. Do not retry automatically.
        raise ValueError(
            f"GitHub {method} failed ({type(exc).__name__}); check network/CA settings. "
            "If writing, inspect the branch before retrying."
        ) from None


def _error(response: requests.Response, operation: str) -> ValueError:
    # Avoid dumping arbitrary proxy responses or request credentials.
    return ValueError(
        f"GitHub {operation} failed (HTTP {response.status_code}). "
        "Check repository/branch access and token permissions; for 409/422, "
        "preview again and check branch rules before retrying."
    )


def get_repo(owner: str, repo: str) -> dict:
    response = _request("GET", _url(owner, repo))
    if response.status_code == 404:
        raise ValueError(f"repo {owner}/{repo} not found or not accessible to this token")
    if response.status_code != 200:
        raise _error(response, "get_repo")
    return response.json()


def get_file(owner: str, repo: str, path: str, ref: str) -> dict:
    response = _request("GET", _url(owner, repo, path), params={"ref": ref})
    if response.status_code == 404:
        return {"exists": False, "path": path, "sha": None, "content": None}
    if response.status_code != 200:
        raise _error(response, "get_file")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise ValueError(f"{path} is not a regular file")
    if payload.get("encoding") != "base64":
        raise ValueError(f"{path} cannot be read as inline text (may exceed the API size limit)")
    try:
        content = base64.b64decode("".join(payload["content"].split()), validate=True).decode("utf-8")
    except (KeyError, ValueError, UnicodeDecodeError):
        raise ValueError(f"{path} is not valid UTF-8 text") from None
    return {"exists": True, "path": path, "sha": payload["sha"], "content": content}


def put_file(owner: str, repo: str, path: str, content: str, message: str,
             branch: str, expected_sha: str | None) -> dict:
    """Write against the SHA read during planning, retaining conflict protection."""
    if not message.strip():
        raise ValueError("commit message must be non-empty")
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if expected_sha is not None:
        body["sha"] = expected_sha
    name, email = os.getenv("MCP_GIT_AUTHOR_NAME"), os.getenv("MCP_GIT_AUTHOR_EMAIL")
    if bool(name) != bool(email):
        raise ValueError("Set both MCP_GIT_AUTHOR_NAME and MCP_GIT_AUTHOR_EMAIL, or neither")
    if name and email:
        body["author"] = body["committer"] = {"name": name, "email": email}
    response = _request("PUT", _url(owner, repo, path), json=body)
    if response.status_code not in (200, 201):
        raise _error(response, "put_file")
    return response.json()
