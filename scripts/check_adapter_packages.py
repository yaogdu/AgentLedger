#!/usr/bin/env python3
"""Check the v1.2 adapter package boundaries across supported languages."""
from __future__ import annotations

import importlib
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PythonAdapter:
    package: str
    module: str
    symbols: tuple[str, ...]
    required_dependency: str | None = None


PYTHON_ADAPTERS = [
    PythonAdapter("agentledger-postgres", "agentledger_postgres", ("PostgresStore", "PostgresStoreConfig"), "psycopg"),
    PythonAdapter("agentledger-s3", "agentledger_s3", ("S3BlobStore", "S3BlobStoreConfig"), "boto3"),
    PythonAdapter("agentledger-langgraph", "agentledger_langgraph", ("LangGraphCheckpointerAdapter", "LangGraphNodeAdapter")),
    PythonAdapter("agentledger-mcp", "agentledger_mcp", ("MCPToolAdapter", "MCPContextAdapter")),
    PythonAdapter("agentledger-otel", "agentledger_otel", ("OTLPTraceExporter", "OTLPResource")),
    PythonAdapter("agentledger-sandbox-docker", "agentledger_sandbox_docker", ("DockerSandboxExecutor", "SandboxPolicy")),
]

TYPESCRIPT_ADAPTERS = {
    "agentledger-postgres": "./postgres",
    "agentledger-s3": "./s3",
    "agentledger-mcp": "./mcp",
    "agentledger-otel": "./otel",
    "agentledger-sandbox-docker": "./sandbox/docker",
    "agentledger-langgraph": "./langgraph",
}

RUST_ADAPTERS = {
    "agentledger-postgres": "adapter-postgres",
    "agentledger-s3": "adapter-s3",
    "agentledger-mcp": "adapter-mcp",
    "agentledger-otel": "adapter-otel",
    "agentledger-sandbox-docker": "adapter-docker",
    "agentledger-framework": "adapter-framework",
}

GO_ADAPTER_DIRS = [
    "go/adapters/postgres/postgres.go",
    "go/adapters/s3/s3.go",
    "go/adapters/mcp/mcp.go",
    "go/adapters/otel/otel.go",
    "go/adapters/sandbox/docker/docker.go",
    "go/adapters/framework/framework.go",
]


def fail(message: str) -> None:
    raise SystemExit(message)


def load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing file: {path.relative_to(ROOT)}")


def python_version() -> str:
    return load_toml(ROOT / "pyproject.toml")["project"]["version"]


def check_python(version: str) -> None:
    root_pyproject = load_toml(ROOT / "pyproject.toml")
    extras = root_pyproject["project"]["optional-dependencies"]
    for adapter in PYTHON_ADAPTERS:
        package_dir = ROOT / "packages" / adapter.package
        metadata = load_toml(package_dir / "pyproject.toml")["project"]
        if metadata["name"] != adapter.package:
            fail(f"{adapter.package}: package name mismatch")
        if metadata["version"] != version:
            fail(f"{adapter.package}: expected version {version}, got {metadata['version']}")
        deps = metadata.get("dependencies", [])
        if not any(dep.startswith("agentledger-runtime>=1.2") for dep in deps):
            fail(f"{adapter.package}: missing dependency on agentledger-runtime>=1.2")
        if adapter.required_dependency and not any(adapter.required_dependency in dep for dep in deps):
            fail(f"{adapter.package}: missing dependency containing {adapter.required_dependency}")
        if adapter.package not in "\n".join(extras.get("all", [])):
            fail(f"root extra all does not include {adapter.package}")
        if not (package_dir / "README.md").exists():
            fail(f"{adapter.package}: README.md missing")
        if not (package_dir / "tests" / "test_import.py").exists():
            fail(f"{adapter.package}: import smoke test missing")

    sys.path.insert(0, str(ROOT / "src"))
    for adapter in PYTHON_ADAPTERS:
        sys.path.insert(0, str(ROOT / "packages" / adapter.package / "src"))
    for adapter in PYTHON_ADAPTERS:
        module = importlib.import_module(adapter.module)
        for symbol in adapter.symbols:
            if not hasattr(module, symbol):
                fail(f"{adapter.module}: missing symbol {symbol}")


def check_typescript(version: str) -> None:
    runtime_pkg = json.loads((ROOT / "typescript" / "package.json").read_text(encoding="utf-8"))
    if runtime_pkg["version"] != version:
        fail(f"typescript runtime version mismatch: {runtime_pkg['version']} != {version}")
    exports = runtime_pkg.get("exports", {})
    for package, subpath in TYPESCRIPT_ADAPTERS.items():
        if subpath not in exports:
            fail(f"typescript package exports missing {subpath}")
        if "src/adapters" not in "\n".join(runtime_pkg.get("files", [])):
            fail("typescript package files does not include src/adapters")
        package_dir = ROOT / "typescript" / "packages" / package
        metadata = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
        if metadata["name"] != package:
            fail(f"{package}: npm package name mismatch")
        if metadata["version"] != version:
            fail(f"{package}: npm package version mismatch")
        if metadata.get("dependencies", {}).get("agentledger-runtime") != "^1.2.0":
            fail(f"{package}: missing dependency on agentledger-runtime ^1.2.0")
        if not (package_dir / "src" / "index.js").exists() or not (package_dir / "src" / "index.d.ts").exists():
            fail(f"{package}: npm source exports missing")


def check_rust(version: str) -> None:
    root = load_toml(ROOT / "rust" / "Cargo.toml")
    if root["package"]["version"] != version:
        fail(f"rust runtime version mismatch: {root['package']['version']} != {version}")
    features = root.get("features", {})
    for package, feature in RUST_ADAPTERS.items():
        if feature not in features:
            fail(f"rust feature missing: {feature}")
        package_dir = ROOT / "rust" / "crates" / package
        metadata = load_toml(package_dir / "Cargo.toml")
        if metadata["package"]["name"] != package:
            fail(f"{package}: crate name mismatch")
        if metadata["package"]["version"] != version:
            fail(f"{package}: crate version mismatch")
        if not (package_dir / "src" / "lib.rs").exists():
            fail(f"{package}: crate lib.rs missing")


def check_go() -> None:
    for rel in GO_ADAPTER_DIRS:
        path = ROOT / rel
        if not path.exists():
            fail(f"go adapter boundary missing: {rel}")
        text = path.read_text(encoding="utf-8")
        if "github.com/yaogdu/AgentLedger/go" not in text:
            fail(f"go adapter boundary does not re-export runtime package: {rel}")


def main() -> None:
    version = python_version()
    check_python(version)
    check_typescript(version)
    check_rust(version)
    check_go()
    print(json.dumps({"passed": True, "version": version, "python_packages": [adapter.package for adapter in PYTHON_ADAPTERS], "typescript_packages": sorted(TYPESCRIPT_ADAPTERS), "rust_crates": sorted(RUST_ADAPTERS), "go_boundaries": GO_ADAPTER_DIRS}, indent=2))


if __name__ == "__main__":
    main()

