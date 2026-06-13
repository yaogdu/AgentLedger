#!/usr/bin/env python3
"""Check adapter and companion package boundaries across supported languages."""
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
    PythonAdapter("agentledger-mysql", "agentledger_mysql", ("MySQLStore", "MySQLStoreConfig"), "pymysql"),
    PythonAdapter("agentledger-s3", "agentledger_s3", ("S3BlobStore", "S3BlobStoreConfig"), "boto3"),
    PythonAdapter("agentledger-langgraph", "agentledger_langgraph", ("LangGraphCheckpointerAdapter", "LangGraphNodeAdapter")),
    PythonAdapter("agentledger-mcp", "agentledger_mcp", ("MCPToolAdapter", "MCPContextAdapter")),
    PythonAdapter("agentledger-otel", "agentledger_otel", ("OTLPTraceExporter", "OTLPResource")),
    PythonAdapter("agentledger-langfuse", "agentledger_langfuse", ("LangfuseTraceExporter", "LangfuseProject")),
    PythonAdapter("agentledger-sandbox-docker", "agentledger_sandbox_docker", ("DockerSandboxExecutor", "SandboxPolicy")),
]

PYTHON_COMPANION_PACKAGES = [
    PythonAdapter(
        "agentledger-inspector",
        "agentledger_inspector",
        (
            "INSPECTOR_SCHEMA_VERSION",
            "EvidenceBlobStoreProtocol",
            "EvidenceStateStoreProtocol",
            "InspectorDataSource",
            "InspectorRedactionPolicy",
            "InspectorReportBuilder",
            "ReadOnlyPostgresStore",
        ),
    ),
]

TYPESCRIPT_ADAPTERS = {
    "agentledger-postgres": "./postgres",
    "agentledger-mysql": "./mysql",
    "agentledger-s3": "./s3",
    "agentledger-mcp-adapter": "./mcp",
    "agentledger-otel": "./otel",
    "agentledger-langfuse": "./langfuse",
    "agentledger-sandbox-docker": "./sandbox/docker",
    "agentledger-langgraph": "./langgraph",
}

TYPESCRIPT_PACKAGE_DIRS = {
    "agentledger-mcp-adapter": "agentledger-mcp",
}

RUST_ADAPTERS = {
    "agentledger-postgres": "adapter-postgres",
    "agentledger-mysql": "adapter-mysql",
    "agentledger-s3": "adapter-s3",
    "agentledger-mcp": "adapter-mcp",
    "agentledger-otel": "adapter-otel",
    "agentledger-sandbox-docker": "adapter-docker",
    "agentledger-langfuse": "adapter-langfuse",
    "agentledger-framework": "adapter-framework",
}

GO_ADAPTER_DIRS = [
    "go/adapters/postgres/postgres.go",
    "go/adapters/mysql/mysql.go",
    "go/adapters/s3/s3.go",
    "go/adapters/mcp/mcp.go",
    "go/adapters/otel/otel.go",
    "go/adapters/langfuse/langfuse.go",
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


def check_python(root_version: str) -> None:
    root_pyproject = load_toml(ROOT / "pyproject.toml")
    extras = root_pyproject["project"]["optional-dependencies"]
    for adapter in PYTHON_ADAPTERS:
        check_python_package_metadata(adapter, extras, expected_version=None)
    for package in PYTHON_COMPANION_PACKAGES:
        check_python_package_metadata(package, extras, expected_version=root_version)

    sys.path.insert(0, str(ROOT / "src"))
    for adapter in [*PYTHON_ADAPTERS, *PYTHON_COMPANION_PACKAGES]:
        sys.path.insert(0, str(ROOT / "packages" / adapter.package / "src"))
    for adapter in [*PYTHON_ADAPTERS, *PYTHON_COMPANION_PACKAGES]:
        module = importlib.import_module(adapter.module)
        for symbol in adapter.symbols:
            if not hasattr(module, symbol):
                fail(f"{adapter.module}: missing symbol {symbol}")


def check_python_package_metadata(adapter: PythonAdapter, extras: dict, *, expected_version: str | None) -> None:
    package_dir = ROOT / "packages" / adapter.package
    metadata = load_toml(package_dir / "pyproject.toml")["project"]
    if metadata["name"] != adapter.package:
        fail(f"{adapter.package}: package name mismatch")
    if expected_version is not None and metadata["version"] != expected_version:
        fail(f"{adapter.package}: expected version {expected_version}, got {metadata['version']}")
    if not str(metadata["version"]).startswith("1.4."):
        fail(f"{adapter.package}: expected 1.4.x package boundary, got {metadata['version']}")
    deps = metadata.get("dependencies", [])
    if not any(dep.startswith("agentledger-runtime>=1.4") for dep in deps):
        fail(f"{adapter.package}: missing dependency on agentledger-runtime>=1.4")
    if adapter.required_dependency and not any(adapter.required_dependency in dep for dep in deps):
        fail(f"{adapter.package}: missing dependency containing {adapter.required_dependency}")
    if adapter.package not in "\n".join(extras.get("all", [])):
        fail(f"root extra all does not include {adapter.package}")
    if not (package_dir / "README.md").exists():
        fail(f"{adapter.package}: README.md missing")
    if not (package_dir / "tests" / "test_import.py").exists():
        fail(f"{adapter.package}: import smoke test missing")


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
        package_dir = ROOT / "typescript" / "packages" / TYPESCRIPT_PACKAGE_DIRS.get(package, package)
        metadata = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
        if metadata["name"] != package:
            fail(f"{package}: npm package name mismatch")
        if metadata["version"] != version:
            fail(f"{package}: npm package version mismatch")
        if metadata.get("dependencies", {}).get("agentledger-runtime") != f"^{version}":
            fail(f"{package}: missing dependency on agentledger-runtime ^{version}")
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
    root_version = python_version()
    typescript_version = json.loads((ROOT / "typescript" / "package.json").read_text(encoding="utf-8"))["version"]
    rust_version = load_toml(ROOT / "rust" / "Cargo.toml")["package"]["version"]
    check_python(root_version)
    check_typescript(typescript_version)
    check_rust(rust_version)
    check_go()
    print(json.dumps({"passed": True, "python_runtime_version": root_version, "typescript_runtime_version": typescript_version, "rust_runtime_version": rust_version, "python_packages": [adapter.package for adapter in PYTHON_ADAPTERS], "python_companion_packages": [package.package for package in PYTHON_COMPANION_PACKAGES], "typescript_packages": sorted(TYPESCRIPT_ADAPTERS), "rust_crates": sorted(RUST_ADAPTERS), "go_boundaries": GO_ADAPTER_DIRS}, indent=2))


if __name__ == "__main__":
    main()
