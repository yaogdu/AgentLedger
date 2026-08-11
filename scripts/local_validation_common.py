from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]


SENSITIVE_QUERY_KEYS = {
    "access_key",
    "access_key_id",
    "aws_access_key_id",
    "aws_secret_access_key",
    "client_secret",
    "password",
    "passwd",
    "pwd",
    "secret",
    "secret_access_key",
    "token",
}


@dataclass
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    duration_seconds: float
    stdout_path: str | None = None
    stderr_path: str | None = None
    parsed_stdout: Any | None = None

    @property
    def status(self) -> str:
        if self.returncode != 0:
            return "failed"
        if isinstance(self.parsed_stdout, dict) and self.parsed_stdout.get("passed") is False:
            return "failed"
        return "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 3),
            "command": redact_command(self.command),
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "parsed_stdout": self.parsed_stdout,
        }


def run_check(
    name: str,
    command: list[str],
    output_dir: Path,
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdin_path: Path | None = None,
    timeout: int | None = None,
    parse_json: bool = False,
    output_suffix: str | None = None,
) -> CommandResult:
    safe_name = safe_filename(name if output_suffix is None else f"{name}-{output_suffix}")
    stdout_path = output_dir / f"{safe_name}.out"
    stderr_path = output_dir / f"{safe_name}.err"
    start = time.monotonic()
    try:
        stdin = stdin_path.open("r", encoding="utf-8") if stdin_path is not None else None
        try:
            completed = subprocess.run(command, cwd=cwd, env=env, stdin=stdin, text=True, capture_output=True, timeout=timeout)
        finally:
            if stdin is not None:
                stdin.close()
        duration = time.monotonic() - start
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        parsed = parse_stdout_json(completed.stdout) if parse_json else None
        return CommandResult(name, command, completed.returncode, duration, str(stdout_path), str(stderr_path), parsed)
    except FileNotFoundError as exc:
        duration = time.monotonic() - start
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
        return CommandResult(name, command, 127, duration, str(stdout_path), str(stderr_path))
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + f"\nTimed out after {timeout} seconds\n", encoding="utf-8")
        return CommandResult(name, command, 124, duration, str(stdout_path), str(stderr_path))


def run_python_step(name: str, output_dir: Path, func: Callable[[], dict[str, Any]]) -> CommandResult:
    safe_name = safe_filename(name)
    stdout_path = output_dir / f"{safe_name}.out"
    stderr_path = output_dir / f"{safe_name}.err"
    start = time.monotonic()
    try:
        payload = func()
        duration = time.monotonic() - start
        stdout_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandResult(name, [], 0, duration, str(stdout_path), str(stderr_path), payload)
    except Exception as exc:
        duration = time.monotonic() - start
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(repr(exc), encoding="utf-8")
        return CommandResult(name, [], 1, duration, str(stdout_path), str(stderr_path))


def parse_stdout_json(value: str) -> Any | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "check"


def prepend_path(value: str, existing: str | None) -> str:
    return value if not existing else f"{value}{os.pathsep}{existing}"


def read_version(root: Path) -> str:
    if tomllib is None:
        return "unknown"
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", "unknown"))


def dsn_database(value: str) -> str:
    parts = urlsplit(value)
    database = unquote(parts.path.lstrip("/").split("/", 1)[0])
    return database or "agentledger"


def dsn_user(value: str) -> str | None:
    username = urlsplit(value).username
    return unquote(username) if username else None


def redact_dsn(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return re.sub(r"(://[^:/@]+:)([^@]+)(@)", r"\1***\3", value)

    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        if ":" in userinfo:
            netloc = f"{userinfo.split(':', 1)[0]}:***@{hostinfo}"

    query = parts.query
    if query:
        query_items = []
        changed = False
        for key, item_value in parse_qsl(query, keep_blank_values=True):
            if is_sensitive_query_key(key):
                query_items.append((key, "***"))
                changed = True
            else:
                query_items.append((key, item_value))
        if changed:
            query = urlencode(query_items, safe="*")

    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def is_sensitive_query_key(key: str) -> bool:
    lower = key.lower()
    return lower in SENSITIVE_QUERY_KEYS or lower.endswith(("_password", "_secret", "_token"))


def redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for arg in command:
        if hide_next:
            redacted.append(redact_dsn(arg))
            hide_next = False
            continue
        if arg.startswith(("--dsn=", "--postgres-dsn=")):
            key, value = arg.split("=", 1)
            redacted.append(f"{key}={redact_dsn(value)}")
            continue
        redacted.append(redact_dsn(arg))
        hide_next = arg in {"--dsn", "--postgres-dsn"}
    return redacted
