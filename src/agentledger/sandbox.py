from __future__ import annotations

import asyncio
import inspect
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxPolicy:
    tool_name: str
    run_id: str
    step_id: str
    executor: str = "default"
    isolation_level: str = "none"
    network: str = "deny"
    filesystem: str = "read-only"
    timeout_seconds: int = 30
    env: dict[str, str] = field(default_factory=dict)
    resource_limits: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def with_overrides(self, **overrides: Any) -> "SandboxPolicy":
        data = {
            "tool_name": self.tool_name,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "executor": self.executor,
            "isolation_level": self.isolation_level,
            "network": self.network,
            "filesystem": self.filesystem,
            "timeout_seconds": self.timeout_seconds,
            "env": dict(self.env),
            "resource_limits": dict(self.resource_limits),
            "extra": dict(self.extra),
        }
        data.update({key: value for key, value in overrides.items() if value is not None})
        return SandboxPolicy(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "executor": self.executor,
            "isolation_level": self.isolation_level,
            "network": self.network,
            "filesystem": self.filesystem,
            "timeout_seconds": self.timeout_seconds,
            "env_keys": sorted(self.env.keys()),
            "resource_limits": self.resource_limits,
            "extra": self.extra,
        }


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    output: Any = None
    error_type: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_type": self.error_type,
            "error": self.error,
            "metadata": self.metadata,
        }


class SandboxExecutor(Protocol):
    async def run_tool(self, func: Callable[[dict[str, Any]], Any], args: dict[str, Any], policy: SandboxPolicy) -> SandboxResult:
        ...


@dataclass(frozen=True)
class SandboxToolRule:
    required: bool | None = None
    executor: str | None = None
    network: str | None = None
    filesystem: str | None = None
    timeout_seconds: int | None = None
    resource_limits: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SandboxToolRule":
        data = data or {}
        return cls(
            required=data.get("required"),
            executor=data.get("executor"),
            network=data.get("network"),
            filesystem=data.get("filesystem"),
            timeout_seconds=data.get("timeout_seconds"),
            resource_limits=dict(data.get("resource_limits") or {}),
            extra={key: value for key, value in data.items() if key not in {"required", "executor", "network", "filesystem", "timeout_seconds", "resource_limits"}},
        )


@dataclass(frozen=True)
class SandboxConfig:
    default_executor: str = "local"
    fail_closed: bool = True
    executors: dict[str, dict[str, Any]] = field(default_factory=dict)
    tools: dict[str, SandboxToolRule] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SandboxConfig":
        data = data or {}
        return cls(
            default_executor=str(data.get("default_executor", "local")),
            fail_closed=bool(data.get("fail_closed", True)),
            executors={name: dict(value or {}) for name, value in (data.get("executors") or {}).items()},
            tools={name: SandboxToolRule.from_dict(value) for name, value in (data.get("tools") or {}).items()},
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "SandboxConfig":
        source = Path(path).read_text(encoding="utf-8")
        stripped = source.lstrip()
        if stripped.startswith("{"):
            return cls.from_dict(json.loads(source))
        return cls.from_dict(parse_sandbox_yaml(source))

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_executor": self.default_executor,
            "fail_closed": self.fail_closed,
            "executors": self.executors,
            "tools": {
                name: {
                    "required": rule.required,
                    "executor": rule.executor,
                    "network": rule.network,
                    "filesystem": rule.filesystem,
                    "timeout_seconds": rule.timeout_seconds,
                    "resource_limits": rule.resource_limits,
                    **rule.extra,
                }
                for name, rule in self.tools.items()
            },
        }


def parse_sandbox_yaml(source: str) -> dict[str, Any]:
    """Parse a small dependency-free YAML subset for sandbox config examples."""
    data: dict[str, Any] = {}
    section: str | None = None
    current_name: str | None = None
    current_map: str | None = None
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        if indent == 0:
            current_name = None
            current_map = None
            if content.endswith(":"):
                section = content[:-1]
                data.setdefault(section, {})
            else:
                key, value = _split_scalar(content)
                data[key] = value
                section = None
            continue
        if section in {"executors", "tools"} and indent == 2:
            current_name = content[:-1] if content.endswith(":") else content
            data.setdefault(section, {}).setdefault(current_name, {})
            current_map = None
            continue
        if section in {"executors", "tools"} and current_name and indent == 4:
            key, value = _split_scalar(content)
            if value == {}:
                current_map = key
                data[section][current_name].setdefault(key, {})
            else:
                data[section][current_name][key] = value
            continue
        if section in {"executors", "tools"} and current_name and current_map and indent == 6:
            key, value = _split_scalar(content)
            data[section][current_name].setdefault(current_map, {})[key] = value
            continue
        raise ValueError(f"unsupported sandbox YAML line: {raw}")
    return data


def _split_scalar(content: str) -> tuple[str, Any]:
    if ":" not in content:
        raise ValueError(f"expected key: value, got {content!r}")
    key, raw = content.split(":", 1)
    value = raw.strip()
    if value == "":
        parsed: Any = {}
    elif value in {"true", "false"}:
        parsed = value == "true"
    elif value.isdigit():
        parsed = int(value)
    else:
        parsed = value.strip("\"'")
    return key.strip(), parsed


class DisabledSandboxExecutor:
    def __init__(self, *, name: str = "none", fail_closed: bool = True):
        self.name = name
        self.fail_closed = fail_closed

    async def run_tool(self, func: Callable[[dict[str, Any]], Any], args: dict[str, Any], policy: SandboxPolicy) -> SandboxResult:
        return SandboxResult(
            ok=False,
            error_type="SandboxDisabled",
            error=f"sandbox executor {self.name!r} is disabled",
            metadata={"executor": self.name, "isolation_level": "none", "fail_closed": self.fail_closed, "policy": policy.to_dict()},
        )


class LocalSandboxExecutor:
    """Dependency-free sandbox boundary for local development.

    This executor does not isolate the OS process. It exists so the runtime
    contract, events, and tests are stable before real isolation adapters are
    plugged in.
    """

    name = "local"
    isolation_level = "none"

    async def run_tool(self, func: Callable[[dict[str, Any]], Any], args: dict[str, Any], policy: SandboxPolicy) -> SandboxResult:
        try:
            result = func(args)
            if inspect.isawaitable(result):
                result = await result
            return SandboxResult(ok=True, output=result, metadata={"executor": self.name, "isolation_level": self.isolation_level, "policy": policy.to_dict()})
        except Exception as exc:
            return SandboxResult(ok=False, error_type=type(exc).__name__, error=repr(exc), metadata={"executor": self.name, "isolation_level": self.isolation_level, "policy": policy.to_dict()})


class ExternalSandboxExecutor:
    """Dependency-free contract adapter for isolation backends.

    External executors can run command-style tools when explicitly enabled via
    config. They never attempt to serialize and execute an arbitrary Python
    callable in a remote/container sandbox.
    """

    backend_type = "external"
    isolation_level = "external"

    def __init__(self, *, name: str, config: dict[str, Any] | None = None):
        self.name = name
        self.config = config or {}

    def build_manifest(self, policy: SandboxPolicy, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "backend": self.backend_type,
            "executor": self.name,
            "isolation_level": self.isolation_level,
            "tool_name": policy.tool_name,
            "run_id": policy.run_id,
            "step_id": policy.step_id,
            "network": policy.network,
            "filesystem": policy.filesystem,
            "timeout_seconds": policy.timeout_seconds,
            "resource_limits": policy.resource_limits,
            "config": self._safe_config(),
            "arg_keys": sorted(args.keys()),
            "command_style": self._extract_command(args) is not None if self._command_is_valid(args) else False,
        }

    async def run_tool(self, func: Callable[[dict[str, Any]], Any], args: dict[str, Any], policy: SandboxPolicy) -> SandboxResult:
        manifest = self.build_manifest(policy, args)
        command_result = self._command_or_error(args, manifest)
        if isinstance(command_result, SandboxResult):
            return command_result
        if not self._allow_command_execution():
            return self._adapter_not_installed(manifest, reason="command execution is not enabled for this executor")
        return await self._run_external_command(command_result, policy, manifest)

    async def _run_external_command(self, command: list[str], policy: SandboxPolicy, manifest: dict[str, Any]) -> SandboxResult:
        return self._adapter_not_installed(manifest, reason="no command runner is implemented for this executor")

    def _adapter_not_installed(self, manifest: dict[str, Any], *, reason: str | None = None) -> SandboxResult:
        return SandboxResult(
            ok=False,
            error_type="SandboxAdapterNotInstalled",
            error=reason or f"sandbox executor {self.name!r} requires an installed adapter package or injected executor",
            metadata={"executor": self.name, "isolation_level": self.isolation_level, "manifest": manifest},
        )

    def _allow_command_execution(self) -> bool:
        return bool(self.config.get("allow_command_execution", False))

    def _command_or_error(self, args: dict[str, Any], manifest: dict[str, Any]) -> list[str] | SandboxResult:
        try:
            command = self._extract_command(args)
        except ValueError as exc:
            return SandboxResult(ok=False, error_type="InvalidSandboxCommand", error=str(exc), metadata={"executor": self.name, "manifest": manifest})
        if command is None:
            return self._adapter_not_installed(manifest, reason="external sandbox tools require a command-style `_sandbox_command` arg")
        return command

    def _command_is_valid(self, args: dict[str, Any]) -> bool:
        try:
            self._extract_command(args)
            return True
        except ValueError:
            return False

    def _extract_command(self, args: dict[str, Any]) -> list[str] | None:
        raw = args.get("_sandbox_command", args.get("command"))
        if raw is None:
            return None
        if isinstance(raw, str):
            if not self.config.get("allow_shell", False):
                raise ValueError("string commands require allow_shell=true; pass argv list in `_sandbox_command` instead")
            shell = str(self.config.get("shell", "/bin/sh"))
            return [shell, "-lc", raw]
        if not isinstance(raw, list) or not raw or not all(isinstance(part, str) and part for part in raw):
            raise ValueError("_sandbox_command must be a non-empty list[str]")
        return list(raw)

    async def _run_subprocess(self, argv: list[str], policy: SandboxPolicy, manifest: dict[str, Any], *, fallback_isolation: str | None = None) -> SandboxResult:
        env = {"PATH": os.environ.get("PATH", "")}
        env.update(policy.env)
        cwd = policy.extra.get("cwd") if isinstance(policy.extra.get("cwd"), str) else None
        try:
            proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, cwd=cwd)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=policy.timeout_seconds)
        except asyncio.TimeoutError:
            try:
                proc.kill()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            return SandboxResult(ok=False, error_type="SandboxTimeout", error=f"sandbox command timed out after {policy.timeout_seconds}s", metadata={"executor": self.name, "manifest": manifest})
        except FileNotFoundError as exc:
            return SandboxResult(ok=False, error_type="SandboxBinaryMissing", error=str(exc), metadata={"executor": self.name, "manifest": manifest})
        except Exception as exc:
            return SandboxResult(ok=False, error_type=type(exc).__name__, error=repr(exc), metadata={"executor": self.name, "manifest": manifest})

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        output = {"stdout": out, "stderr": err, "returncode": proc.returncode}
        metadata = {"executor": self.name, "isolation_level": fallback_isolation or self.isolation_level, "manifest": manifest, "executed": True}
        if fallback_isolation:
            metadata["fallback_isolation"] = fallback_isolation
        if proc.returncode != 0:
            return SandboxResult(ok=False, output=output, error_type="SandboxCommandFailed", error=f"sandbox command exited with {proc.returncode}", metadata=metadata)
        return SandboxResult(ok=True, output=output, metadata=metadata)

    def _safe_config(self) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, value in self.config.items():
            if any(token in key.lower() for token in ["secret", "token", "key", "password"]):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = value
        return redacted


class BubblewrapSandboxExecutor(ExternalSandboxExecutor):
    backend_type = "bubblewrap"
    isolation_level = "process"

    def build_manifest(self, policy: SandboxPolicy, args: dict[str, Any]) -> dict[str, Any]:
        manifest = super().build_manifest(policy, args)
        command = self._extract_command(args) if self._command_is_valid(args) else None
        manifest["command"] = self._bubblewrap_argv(policy, command or ["<tool-command>"])
        return manifest

    async def _run_external_command(self, command: list[str], policy: SandboxPolicy, manifest: dict[str, Any]) -> SandboxResult:
        binary = str(self.config.get("binary", "bwrap"))
        resolved = shutil.which(binary) if "/" not in binary else (binary if Path(binary).exists() else None)
        if resolved is None:
            if self.config.get("fallback_without_bwrap", False):
                manifest = {**manifest, "fallback_reason": "bubblewrap binary not found", "fallback_command": command}
                return await self._run_subprocess(command, policy, manifest, fallback_isolation="none")
            return SandboxResult(ok=False, error_type="SandboxBinaryMissing", error=f"bubblewrap binary not found: {binary}", metadata={"executor": self.name, "manifest": manifest})
        argv = self._bubblewrap_argv(policy, command, binary=resolved)
        return await self._run_subprocess(argv, policy, manifest)

    def _bubblewrap_argv(self, policy: SandboxPolicy, command: list[str], *, binary: str | None = None) -> list[str]:
        argv = [binary or str(self.config.get("binary", "bwrap")), "--unshare-all", "--die-with-parent"]
        if policy.network == "deny":
            argv.append("--unshare-net")
        for path in self.config.get("ro_bind", ["/usr", "/bin", "/lib", "/lib64"]):
            if isinstance(path, str):
                argv.extend(["--ro-bind", path, path])
        argv.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--"])
        argv.extend(command)
        return argv


class DockerSandboxExecutor(ExternalSandboxExecutor):
    backend_type = "docker"
    isolation_level = "container"

    def build_manifest(self, policy: SandboxPolicy, args: dict[str, Any]) -> dict[str, Any]:
        manifest = super().build_manifest(policy, args)
        command = self._extract_command(args) if self._command_is_valid(args) else None
        command = command or ["<tool-command>"]
        manifest["command"] = self._docker_argv(policy, command)
        return manifest

    async def _run_external_command(self, command: list[str], policy: SandboxPolicy, manifest: dict[str, Any]) -> SandboxResult:
        binary = str(self.config.get("binary", "docker"))
        resolved = shutil.which(binary) if "/" not in binary else (binary if Path(binary).exists() else None)
        if resolved is None:
            return SandboxResult(ok=False, error_type="SandboxBinaryMissing", error=f"docker binary not found: {binary}", metadata={"executor": self.name, "manifest": manifest})
        argv = self._docker_argv(policy, command, binary=resolved)
        return await self._run_subprocess(argv, policy, manifest)

    def _docker_argv(self, policy: SandboxPolicy, command: list[str], *, binary: str | None = None) -> list[str]:
        image = str(self.config.get("image", "python:3.11-slim"))
        network = "none" if policy.network == "deny" else str(policy.network)
        argv = [binary or str(self.config.get("binary", "docker")), "run", "--rm", "--network", network, "--read-only"]
        memory = policy.resource_limits.get("memory") or self.config.get("memory")
        cpus = policy.resource_limits.get("cpus") or self.config.get("cpus")
        if memory:
            argv.extend(["--memory", str(memory)])
        if cpus:
            argv.extend(["--cpus", str(cpus)])
        argv.append(image)
        argv.extend(command)
        return argv


class KubernetesSandboxExecutor(ExternalSandboxExecutor):
    backend_type = "kubernetes"
    isolation_level = "pod"

    async def run_tool(self, func: Callable[[dict[str, Any]], Any], args: dict[str, Any], policy: SandboxPolicy) -> SandboxResult:
        manifest = self.build_manifest(policy, args)
        command_result = self._command_or_error(args, manifest)
        if isinstance(command_result, SandboxResult):
            return command_result
        if self._dry_run():
            return SandboxResult(
                ok=True,
                output={"dry_run": True, "kubernetes_job": manifest["kubernetes_job"]},
                metadata={"executor": self.name, "isolation_level": self.isolation_level, "manifest": manifest, "dry_run": True, "executed": False},
            )
        if not self._allow_command_execution():
            return self._adapter_not_installed(manifest, reason="kubernetes command execution is not enabled for this executor")
        return await self._run_external_command(command_result, policy, manifest)

    def build_manifest(self, policy: SandboxPolicy, args: dict[str, Any]) -> dict[str, Any]:
        manifest = super().build_manifest(policy, args)
        command = self._extract_command(args) if self._command_is_valid(args) else None
        command = command or ["<tool-command>"]
        labels = self._labels(policy)
        annotations = {
            "agentledger.dev/run-id": policy.run_id,
            "agentledger.dev/step-id": policy.step_id,
            "agentledger.dev/tool-name": policy.tool_name,
            "agentledger.dev/network": policy.network,
            "agentledger.dev/filesystem": policy.filesystem,
        }
        pod_spec: dict[str, Any] = {
            "serviceAccountName": str(self.config.get("service_account", "agentledger-sandbox")),
            "automountServiceAccountToken": bool(self.config.get("automount_service_account_token", False)),
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": str(self.config.get("container_name", "tool")),
                    "image": str(self.config.get("image", "agentledger/sandbox:latest")),
                    "command": command[:1],
                    "args": command[1:],
                    "resources": self._resources(policy),
                    "securityContext": self._container_security_context(),
                }
            ],
            "securityContext": self._pod_security_context(),
        }
        runtime_class = self.config.get("runtime_class")
        if runtime_class:
            pod_spec["runtimeClassName"] = runtime_class
        manifest["kubernetes_job"] = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "generateName": f"agentledger-{self._dns_part(policy.tool_name)}-",
                "namespace": str(self.config.get("namespace", "agentledger-sandbox")),
                "labels": labels,
                "annotations": annotations,
            },
            "spec": {
                "backoffLimit": int(self.config.get("backoff_limit", 0)),
                "activeDeadlineSeconds": int(self.config.get("active_deadline_seconds", policy.timeout_seconds)),
                "template": {
                    "metadata": {"labels": labels, "annotations": annotations},
                    "spec": pod_spec,
                }
            },
        }
        ttl = self.config.get("ttl_seconds_after_finished")
        if ttl is not None:
            manifest["kubernetes_job"]["spec"]["ttlSecondsAfterFinished"] = int(ttl)
        manifest["kubectl"] = self._kubectl_preview(manifest["kubernetes_job"])
        return manifest

    async def _run_external_command(self, command: list[str], policy: SandboxPolicy, manifest: dict[str, Any]) -> SandboxResult:
        binary = str(self.config.get("kubectl", self.config.get("binary", "kubectl")))
        resolved = shutil.which(binary) if "/" not in binary else (binary if Path(binary).exists() else None)
        if resolved is None:
            return SandboxResult(ok=False, error_type="SandboxBinaryMissing", error=f"kubectl binary not found: {binary}", metadata={"executor": self.name, "manifest": manifest})

        job = manifest["kubernetes_job"]
        namespace = job["metadata"].get("namespace")
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
                json.dump(job, handle, sort_keys=True)
                manifest_path = handle.name
            create_argv = self._kubectl_base(resolved, namespace) + ["create", "-f", manifest_path, "-o", "json"]
            create = await self._run_kubectl(create_argv, policy)
            if create["returncode"] != 0:
                return self._kubectl_failed("KubernetesJobCreateFailed", create, manifest)

            created_job = json.loads(create["stdout"] or "{}")
            job_name = created_job.get("metadata", {}).get("name")
            if not job_name:
                return SandboxResult(ok=False, output=create, error_type="KubernetesJobNameMissing", error="kubectl create did not return a job name", metadata={"executor": self.name, "manifest": manifest})

            wait_result: dict[str, Any] | None = None
            if self.config.get("wait", True):
                wait_timeout = int(self.config.get("wait_timeout_seconds", policy.timeout_seconds))
                wait_argv = self._kubectl_base(resolved, namespace) + ["wait", "--for=condition=complete", f"--timeout={wait_timeout}s", f"job/{job_name}"]
                wait_result = await self._run_kubectl(wait_argv, policy, timeout_seconds=wait_timeout + 5)

            logs_result: dict[str, Any] | None = None
            if self.config.get("capture_logs", True):
                logs_argv = self._kubectl_base(resolved, namespace) + ["logs", f"job/{job_name}"]
                logs_result = await self._run_kubectl(logs_argv, policy)

            cleanup_result: dict[str, Any] | None = None
            if self.config.get("cleanup", True):
                cleanup_argv = self._kubectl_base(resolved, namespace) + ["delete", f"job/{job_name}", "--ignore-not-found=true"]
                cleanup_result = await self._run_kubectl(cleanup_argv, policy)

            output = {"job_name": job_name, "created": create, "wait": wait_result, "logs": logs_result, "cleanup": cleanup_result, "stdout": (logs_result or {}).get("stdout", ""), "stderr": (logs_result or wait_result or create).get("stderr", "")}
            if wait_result is not None and wait_result["returncode"] != 0:
                return self._kubectl_failed("KubernetesJobFailed", output, manifest)
            if logs_result is not None and logs_result["returncode"] != 0:
                return self._kubectl_failed("KubernetesLogsFailed", output, manifest)
            return SandboxResult(ok=True, output=output, metadata={"executor": self.name, "isolation_level": self.isolation_level, "manifest": manifest, "executed": True, "job_name": job_name})
        except asyncio.TimeoutError as exc:
            return SandboxResult(ok=False, error_type="SandboxTimeout", error=repr(exc), metadata={"executor": self.name, "manifest": manifest})
        except Exception as exc:
            return SandboxResult(ok=False, error_type=type(exc).__name__, error=repr(exc), metadata={"executor": self.name, "manifest": manifest})
        finally:
            try:
                Path(manifest_path).unlink()  # type: ignore[possibly-undefined]
            except Exception:
                pass

    async def _run_kubectl(self, argv: list[str], policy: SandboxPolicy, *, timeout_seconds: int | None = None) -> dict[str, Any]:
        env = {"PATH": os.environ.get("PATH", "")}
        try:
            proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds or policy.timeout_seconds)
        except asyncio.TimeoutError:
            try:
                proc.kill()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            return {"argv": argv, "stdout": "", "stderr": f"kubectl command timed out after {timeout_seconds or policy.timeout_seconds}s", "returncode": -1, "timeout": True}
        return {"argv": argv, "stdout": stdout.decode("utf-8", errors="replace"), "stderr": stderr.decode("utf-8", errors="replace"), "returncode": proc.returncode}

    def _kubectl_failed(self, error_type: str, output: dict[str, Any], manifest: dict[str, Any]) -> SandboxResult:
        return SandboxResult(ok=False, output=output, error_type=error_type, error=output.get("stderr") or error_type, metadata={"executor": self.name, "manifest": manifest})

    def _kubectl_base(self, binary: str, namespace: str | None) -> list[str]:
        argv = [binary]
        context = self.config.get("context")
        kubeconfig = self.config.get("kubeconfig")
        if context:
            argv.extend(["--context", str(context)])
        if kubeconfig:
            argv.extend(["--kubeconfig", str(kubeconfig)])
        if namespace:
            argv.extend(["--namespace", str(namespace)])
        return argv

    def _kubectl_preview(self, job: dict[str, Any]) -> list[str]:
        namespace = job["metadata"].get("namespace")
        return self._kubectl_base(str(self.config.get("kubectl", self.config.get("binary", "kubectl"))), namespace) + ["create", "-f", "<job.json>", "-o", "json"]

    def _dry_run(self) -> bool:
        return bool(self.config.get("dry_run", False))

    def _labels(self, policy: SandboxPolicy) -> dict[str, str]:
        return {
            "app.kubernetes.io/name": "agentledger",
            "app.kubernetes.io/component": "sandbox",
            "agentledger.dev/run-id": self._label_value(policy.run_id),
            "agentledger.dev/step-id": self._label_value(policy.step_id),
            "agentledger.dev/tool-name": self._label_value(policy.tool_name),
            "agentledger.dev/network": self._label_value(policy.network),
        }

    def _resources(self, policy: SandboxPolicy) -> dict[str, Any]:
        configured = self.config.get("resources")
        if isinstance(configured, dict):
            return configured
        configured_limits = self.config.get("resource_limits") if isinstance(self.config.get("resource_limits"), dict) else {}
        limits: dict[str, str] = {}
        memory = policy.resource_limits.get("memory") or configured_limits.get("memory") or self.config.get("memory")
        cpu = policy.resource_limits.get("cpu") or policy.resource_limits.get("cpus") or configured_limits.get("cpu") or configured_limits.get("cpus") or self.config.get("cpu") or self.config.get("cpus")
        if memory:
            limits["memory"] = str(memory)
        if cpu:
            limits["cpu"] = str(cpu)
        return {"limits": limits} if limits else {}

    def _pod_security_context(self) -> dict[str, Any]:
        return {"runAsNonRoot": True, "seccompProfile": {"type": str(self.config.get("seccomp_profile", "RuntimeDefault"))}}

    def _container_security_context(self) -> dict[str, Any]:
        return {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        }

    def _dns_part(self, value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
        safe = "-".join(part for part in safe.split("-") if part)
        return (safe or "tool")[:40].strip("-") or "tool"

    def _label_value(self, value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(value))
        safe = safe.strip("-_.") or "value"
        return safe[:63].strip("-_.") or "value"


class E2BSandboxExecutor(ExternalSandboxExecutor):
    backend_type = "e2b"
    isolation_level = "remote-vm"


class FirecrackerSandboxExecutor(ExternalSandboxExecutor):
    backend_type = "firecracker"
    isolation_level = "microvm"


class RemoteSandboxExecutor(ExternalSandboxExecutor):
    backend_type = "custom"
    isolation_level = "remote"

    def build_manifest(self, policy: SandboxPolicy, args: dict[str, Any]) -> dict[str, Any]:
        manifest = super().build_manifest(policy, args)
        manifest["endpoint"] = self.config.get("endpoint")
        return manifest


class SandboxRouter:
    def __init__(self, config: SandboxConfig | None = None, executors: dict[str, SandboxExecutor] | None = None):
        self.config = config or SandboxConfig()
        self.executors = dict(executors or {})
        self._install_configured_executors()

    def _install_configured_executors(self) -> None:
        self.executors.setdefault("local", LocalSandboxExecutor())
        self.executors.setdefault("none", DisabledSandboxExecutor(name="none", fail_closed=self.config.fail_closed))
        self.executors.setdefault("disabled", DisabledSandboxExecutor(name="disabled", fail_closed=self.config.fail_closed))
        for name, raw in self.config.executors.items():
            if name in self.executors:
                continue
            kind = str(raw.get("type", name)).lower()
            if kind == "local":
                self.executors[name] = LocalSandboxExecutor()
            elif kind in {"none", "disabled"}:
                self.executors[name] = DisabledSandboxExecutor(name=name, fail_closed=self.config.fail_closed)
            elif kind in {"bubblewrap", "bwrap"}:
                self.executors[name] = BubblewrapSandboxExecutor(name=name, config=raw)
            elif kind == "docker":
                self.executors[name] = DockerSandboxExecutor(name=name, config=raw)
            elif kind in {"kubernetes", "k8s"}:
                self.executors[name] = KubernetesSandboxExecutor(name=name, config=raw)
            elif kind == "e2b":
                self.executors[name] = E2BSandboxExecutor(name=name, config=raw)
            elif kind == "firecracker":
                self.executors[name] = FirecrackerSandboxExecutor(name=name, config=raw)
            else:
                self.executors[name] = RemoteSandboxExecutor(name=name, config=raw)

    def policy_for(self, base: SandboxPolicy) -> SandboxPolicy:
        rule = self.config.tools.get(base.tool_name)
        executor = self.config.default_executor if base.executor in {"", "default"} else base.executor
        overrides: dict[str, Any] = {"executor": executor}
        if rule is not None:
            overrides.update(
                executor=rule.executor or executor,
                network=rule.network,
                filesystem=rule.filesystem,
                timeout_seconds=rule.timeout_seconds,
                resource_limits=rule.resource_limits or None,
                extra={**base.extra, **rule.extra},
            )
        executor_obj = self.executors.get(overrides["executor"])
        if executor_obj is None and not self.config.fail_closed:
            overrides["executor"] = "local"
            executor_obj = self.executors["local"]
        isolation = getattr(executor_obj, "isolation_level", "unknown") if executor_obj is not None else "unavailable"
        overrides["isolation_level"] = isolation
        return base.with_overrides(**overrides)

    async def run_tool(self, func: Callable[[dict[str, Any]], Any], args: dict[str, Any], policy: SandboxPolicy) -> SandboxResult:
        executor = self.executors.get(policy.executor)
        if executor is None:
            if self.config.fail_closed:
                return SandboxResult(
                    ok=False,
                    error_type="SandboxExecutorMissing",
                    error=f"sandbox executor {policy.executor!r} is not configured",
                    metadata={"executor": policy.executor, "policy": policy.to_dict()},
                )
            executor = self.executors["local"]
        return await executor.run_tool(func, args, policy)

    def describe(self) -> dict[str, Any]:
        return {
            "default_executor": self.config.default_executor,
            "fail_closed": self.config.fail_closed,
            "executors": sorted(self.executors.keys()),
            "tools": {name: rule.executor for name, rule in self.config.tools.items()},
        }


def create_sandbox_executor(config: SandboxConfig | dict[str, Any] | str | Path | None = None, *, executors: dict[str, SandboxExecutor] | None = None) -> SandboxExecutor:
    if isinstance(config, SandboxConfig):
        sandbox_config = config
    elif isinstance(config, (str, Path)):
        sandbox_config = SandboxConfig.from_file(config)
    else:
        sandbox_config = SandboxConfig.from_dict(config)
    return SandboxRouter(sandbox_config, executors=executors)
