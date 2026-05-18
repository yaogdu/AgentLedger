#!/usr/bin/env python3
"""Run the local AgentLedger cross-language runtime parity checks.

This is intentionally a thin orchestration script. The language runtimes own
actual assertions in their native test suites; this runner keeps the contract,
fixtures, and command set in one reproducible gate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_MANIFEST_PATH = ROOT / "contracts/conformance/runtime_semantics.v1.json"
CHECKS: list["CheckRecord"] = []
LANGUAGE_CONFORMANCE: dict[str, dict[str, object]] = {}
SEMANTIC_MANIFEST: dict[str, object] = {}
REQUIRED_SEMANTIC_CHECKS: list[str] = []


@dataclass
class CheckRecord:
    name: str
    command: list[str]
    cwd: str
    status: str
    duration_seconds: float
    exit_code: int | None = None
    detail: str | None = None


def _relative_cwd(cwd: Path) -> str:
    return str(cwd.relative_to(ROOT) if cwd != ROOT else ".")


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None, name: str | None = None, stdout=None) -> None:
    print(f"==> ({cwd.relative_to(ROOT) if cwd != ROOT else '.'}) {' '.join(cmd)}")
    started = time.monotonic()
    try:
        subprocess.run(cmd, cwd=cwd, env=env, stdout=stdout, check=True)
    except subprocess.CalledProcessError as exc:
        CHECKS.append(
            CheckRecord(
                name=name or " ".join(cmd),
                command=cmd,
                cwd=_relative_cwd(cwd),
                status="failed",
                duration_seconds=round(time.monotonic() - started, 3),
                exit_code=exc.returncode,
            )
        )
        raise
    CHECKS.append(
        CheckRecord(
            name=name or " ".join(cmd),
            command=cmd,
            cwd=_relative_cwd(cwd),
            status="passed",
            duration_seconds=round(time.monotonic() - started, 3),
            exit_code=0,
        )
    )



def load_semantic_manifest(path: Path = SEMANTIC_MANIFEST_PATH) -> tuple[dict[str, object], list[str]]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"semantic conformance manifest missing: {path.relative_to(ROOT)}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("semantic conformance manifest must be a JSON object")
    entries = manifest.get("required_semantic_checks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("semantic conformance manifest requires a non-empty required_semantic_checks array")
    ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise ValueError("each semantic conformance check must be an object with a non-empty id")
        check_id = entry["id"]
        if check_id in ids:
            raise ValueError(f"duplicate semantic conformance check id: {check_id}")
        fixture = entry.get("fixture")
        if not isinstance(fixture, str) or not (ROOT / fixture).exists():
            raise ValueError(f"semantic conformance check {check_id} references missing fixture: {fixture}")
        ids.append(check_id)
    return manifest, ids


def extract_json_object(output: str) -> dict[str, object]:
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < start:
        raise ValueError("command output did not contain a JSON object")
    value = json.loads(output[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("command JSON output was not an object")
    return value


def run_json(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None, name: str, language: str) -> dict[str, object]:
    print(f"==> ({cwd.relative_to(ROOT) if cwd != ROOT else '.'}) {' '.join(cmd)}")
    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, cwd=cwd, env=env, check=True, text=True, capture_output=True)
        output = (completed.stdout or "") + (completed.stderr or "")
        if output.strip():
            print(output, end="" if output.endswith("\n") else "\n")
        report = extract_json_object(output)
        checks = report.get("checks")
        if report.get("language") != language:
            raise ValueError(f"expected language {language}, got {report.get('language')}")
        if report.get("passed") is not True:
            raise ValueError(f"{language} conformance did not report passed=true")
        if not isinstance(checks, list):
            raise ValueError(f"{language} conformance report missing checks list")
        missing = [check for check in REQUIRED_SEMANTIC_CHECKS if check not in checks]
        if missing:
            raise ValueError(f"{language} conformance missing semantic checks: {', '.join(missing)}")
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
        CHECKS.append(
            CheckRecord(
                name=name,
                command=cmd,
                cwd=_relative_cwd(cwd),
                status="failed",
                duration_seconds=round(time.monotonic() - started, 3),
                exit_code=getattr(exc, "returncode", 1),
                detail=str(exc),
            )
        )
        if isinstance(exc, subprocess.CalledProcessError):
            raise
        raise SystemExit(1) from exc
    CHECKS.append(
        CheckRecord(
            name=name,
            command=cmd,
            cwd=_relative_cwd(cwd),
            status="passed",
            duration_seconds=round(time.monotonic() - started, 3),
            exit_code=0,
            detail=f"{len(checks)} reported checks",
        )
    )
    LANGUAGE_CONFORMANCE[language] = report
    return report

def python_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def check_contract() -> None:
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "agentledger-contract-check.json"
    env = python_env()
    with out.open("w", encoding="utf-8") as handle:
        run(
            [sys.executable, "-m", "agentledger", "contract", "export"],
            cwd=ROOT,
            env=env,
            name="contract_export",
            stdout=handle,
        )
    run(["diff", "-u", "contracts/agentledger.runtime.v1.json", str(out)], name="contract_diff")


def check_markdown_links() -> None:
    started = time.monotonic()
    candidates = (
        list(ROOT.glob("README*.md"))
        + [p for p in [ROOT / "CHANGELOG.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", ROOT / "CODE_OF_CONDUCT.md"] if p.exists()]
        + list(ROOT.glob("docs/**/*.md"))
        + list(ROOT.glob("examples/**/*.md"))
        + list(ROOT.glob("go/**/*.md"))
        + list(ROOT.glob("typescript/**/*.md"))
        + list(ROOT.glob("rust/**/*.md"))
    )
    missing: list[tuple[str, str]] = []
    for path in candidates:
        if "target" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
            target = match.group(1).split("#", 1)[0]
            if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            resolved = (path.parent / urllib.parse.unquote(target)).resolve()
            if not resolved.exists():
                missing.append((str(path.relative_to(ROOT)), target))
    if missing:
        for source, target in missing:
            print(f"missing markdown link: {source} -> {target}", file=sys.stderr)
        CHECKS.append(
            CheckRecord(
                name="markdown_local_links",
                command=["internal", "markdown-link-check"],
                cwd=".",
                status="failed",
                duration_seconds=round(time.monotonic() - started, 3),
                exit_code=1,
                detail=f"{len(missing)} missing local links",
            )
        )
        raise SystemExit(1)
    CHECKS.append(
        CheckRecord(
            name="markdown_local_links",
            command=["internal", "markdown-link-check"],
            cwd=".",
            status="passed",
            duration_seconds=round(time.monotonic() - started, 3),
            exit_code=0,
        )
    )
    print("==> markdown local links ok")


def write_report(path: str | Path, *, passed: bool, started_at: float) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    failed = [check for check in CHECKS if check.status != "passed"]
    report = {
        "project": "agentledger",
        "suite": "language_parity",
        "passed": passed and not failed,
        "summary": {
            "check_count": len(CHECKS),
            "passed_count": len(CHECKS) - len(failed),
            "failed_count": len(failed),
            "duration_seconds": round(time.monotonic() - started_at, 3),
        },
        "contract": "contracts/agentledger.runtime.v1.json",
        "semantic_manifest": str(SEMANTIC_MANIFEST_PATH.relative_to(ROOT)),
        "conformance_fixtures": [
            "contracts/conformance/runtime_baseline.v1.json",
            "contracts/conformance/policy_approval_sandbox.v1.json",
            "contracts/conformance/cost_failure_attribution.v1.json",
            "contracts/conformance/media_stream_artifacts.v1.json",
        ],
        "required_semantic_checks": REQUIRED_SEMANTIC_CHECKS,
        "semantic_manifest_payload": SEMANTIC_MANIFEST,
        "language_conformance": LANGUAGE_CONFORMANCE,
        "checks": [asdict(check) for check in CHECKS],
    }
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"==> wrote parity report to {target}")


def main(argv: list[str] | None = None) -> int:
    started_at = time.monotonic()
    parser = argparse.ArgumentParser(description="Run AgentLedger cross-language runtime parity checks.")
    parser.add_argument("--skip-python", action="store_true", help="Skip Python reference tests.")
    parser.add_argument("--skip-docs", action="store_true", help="Skip markdown link and diff whitespace checks.")
    parser.add_argument("--json-report", help="Write a machine-readable parity report to this path.")
    args = parser.parse_args(argv)

    global REQUIRED_SEMANTIC_CHECKS, SEMANTIC_MANIFEST
    passed = False
    exit_code = 0
    try:
        SEMANTIC_MANIFEST, REQUIRED_SEMANTIC_CHECKS = load_semantic_manifest()
        check_contract()
        if not args.skip_python:
            run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], env=python_env(), name="python_unittest")
        go_env = os.environ.copy()
        go_env.setdefault("GOCACHE", "/tmp/agentledger-go-cache")
        go_env.setdefault("GOMODCACHE", "/tmp/agentledger-go-mod-cache")
        # Keep the release gate focused on versioned runtime packages. Local
        # scratch demos under go/examples can be incomplete while users iterate.
        run(["go", "test", ".", "./cmd/agentledger-go"], cwd=ROOT / "go", env=go_env, name="go_tests")
        run_json(["go", "run", "./cmd/agentledger-go", "conformance"], cwd=ROOT / "go", env=go_env, name="go_conformance_cli", language="go")
        run(["npm", "test"], cwd=ROOT / "typescript", name="typescript_tests")
        run(["npm", "run", "check"], cwd=ROOT / "typescript", name="typescript_syntax_check")
        run_json(["npm", "run", "conformance"], cwd=ROOT / "typescript", name="typescript_conformance_cli", language="typescript")
        # Keep the release gate focused on the Rust runtime crate and CLI bin.
        # Local scratch demos under rust/examples can be incomplete while users iterate.
        run(["cargo", "test", "--lib", "--bins"], cwd=ROOT / "rust", name="rust_tests")
        run_json(["cargo", "run", "--quiet", "--", "conformance"], cwd=ROOT / "rust", name="rust_conformance_cli", language="rust")
        if not args.skip_docs:
            check_markdown_links()
            run(["git", "diff", "--check"], name="git_diff_check")
        passed = True
        print("==> AgentLedger language parity checks passed")
    except subprocess.CalledProcessError as exc:
        exit_code = exc.returncode or 1
    except SystemExit as exc:
        exit_code = int(exc.code or 1)
    finally:
        if args.json_report:
            write_report(args.json_report, passed=passed, started_at=started_at)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
