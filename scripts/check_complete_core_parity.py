#!/usr/bin/env python3
"""Strict cross-language core parity audit beyond semantic conformance."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def release_family(version: str) -> str:
    parts = version.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else version


def run(cmd: list[str], *, cwd: Path = ROOT) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.setdefault("GOCACHE", "/tmp/agentledger-go-cache")
    env.setdefault("GOMODCACHE", "/tmp/agentledger-go-mod-cache")
    env.setdefault("npm_config_cache", "/tmp/agentledger-npm-cache")
    env.setdefault("CARGO_TARGET_DIR", "/tmp/agentledger-cargo-target")
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    return {"cmd": cmd, "cwd": str(cwd.relative_to(ROOT) if cwd != ROOT else "."), "returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}


def require(result: dict[str, object], checks: list[dict[str, object]], name: str) -> None:
    ok = result["returncode"] == 0
    checks.append({"name": name, "ok": ok, **result})


def main() -> None:
    checks: list[dict[str, object]] = []

    cli_commands = [
        ("python-help", [PY, "-m", "agentledger", "--help"], ROOT),
        ("python-doctor", [PY, "-m", "agentledger", "--root", "/tmp/agentledger-complete-core-doctor", "doctor"], ROOT),
        ("go-help", ["go", "run", "./cmd/agentledger-go", "--help"], ROOT / "go"),
        ("go-doctor", ["go", "run", "./cmd/agentledger-go", "doctor"], ROOT / "go"),
        ("go-quickstart", ["go", "run", "./cmd/agentledger-go", "quickstart"], ROOT / "go"),
        ("typescript-help", ["node", "src/cli.js", "--help"], ROOT / "typescript"),
        ("typescript-doctor", ["node", "src/cli.js", "doctor"], ROOT / "typescript"),
        ("typescript-quickstart", ["node", "src/cli.js", "quickstart"], ROOT / "typescript"),
        ("rust-help", ["cargo", "run", "--quiet", "--", "--help"], ROOT / "rust"),
        ("rust-doctor", ["cargo", "run", "--quiet", "--", "doctor"], ROOT / "rust"),
        ("rust-quickstart", ["cargo", "run", "--quiet", "--", "quickstart"], ROOT / "rust"),
    ]
    for name, cmd, cwd in cli_commands:
        require(run(cmd, cwd=cwd), checks, name)

    example_commands = [
        ("go-example", ["go", "run", "./examples/quickstart"], ROOT / "go"),
        ("typescript-example", ["node", "examples/quickstart/quickstart.js"], ROOT / "typescript"),
        ("rust-example", ["cargo", "run", "--quiet", "--example", "quickstart"], ROOT / "rust"),
    ]
    for name, cmd, cwd in example_commands:
        require(run(cmd, cwd=cwd), checks, name)

    package_checks = [
        ("typescript-pack-dry-run", ["npm", "pack", "--dry-run"], ROOT / "typescript"),
        ("rust-package-dry-run", ["cargo", "package", "--allow-dirty", "--no-verify"], ROOT / "rust"),
    ]
    for name, cmd, cwd in package_checks:
        require(run(cmd, cwd=cwd), checks, name)

    metadata = {
        "typescript_version": json.loads((ROOT / "typescript" / "package.json").read_text())["version"],
        "rust_version": next(line.split("=", 1)[1].strip().strip('"') for line in (ROOT / "rust" / "Cargo.toml").read_text().splitlines() if line.startswith("version")),
        "python_version": next(line.split("=", 1)[1].strip().strip('"') for line in (ROOT / "pyproject.toml").read_text().splitlines() if line.startswith("version")),
    }
    families = {language: release_family(version) for language, version in metadata.items()}
    expected_family = families["python_version"]
    version_ok = all(value == expected_family for value in families.values())
    checks.append({"name": "package-release-family-alignment", "ok": version_ok, "metadata": metadata, "release_families": families, "expected_family": expected_family})

    docs = [
        ROOT / "docs" / "COMPLETE_CORE_PARITY_CHECKLIST.md",
        ROOT / "docs" / "LANGUAGE_QUICKSTART.md",
        ROOT / "docs" / "COMPARISONS.md",
        ROOT / "go" / "README.md",
        ROOT / "typescript" / "README.md",
        ROOT / "rust" / "README.md",
    ]
    for path in docs:
        checks.append({"name": f"doc-present:{path.relative_to(ROOT)}", "ok": path.exists() and path.stat().st_size > 0})

    failed = [check for check in checks if not check.get("ok")]
    report = {"passed": not failed, "failed_count": len(failed), "checks": checks}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
