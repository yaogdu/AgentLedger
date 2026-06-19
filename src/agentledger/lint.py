from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


IGNORE_SAME_LINE = "agentledger: ignore-boundary"
IGNORE_NEXT_LINE = "agentledger: ignore-next-line"


@dataclass(frozen=True)
class BoundaryLintRule:
    rule_id: str
    pattern: str
    category: str
    message: str
    suggestion: str
    prefix: bool = False

    def matches(self, callee: str) -> bool:
        return callee.startswith(self.pattern) if self.prefix else callee == self.pattern

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundaryLintRule":
        missing = [key for key in ("rule_id", "pattern", "category", "message", "suggestion") if key not in data]
        if missing:
            raise ValueError(f"boundary lint rule missing required fields: {', '.join(missing)}")
        return cls(
            rule_id=str(data["rule_id"]),
            pattern=str(data["pattern"]),
            category=str(data["category"]),
            message=str(data["message"]),
            suggestion=str(data["suggestion"]),
            prefix=bool(data.get("prefix", False)),
        )


@dataclass(frozen=True)
class BoundaryLintFinding:
    path: str
    line: int
    column: int
    rule_id: str
    severity: str
    callee: str
    category: str
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "callee": self.callee,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class BoundaryLintReport:
    passed: bool
    scanned_files: list[str]
    findings: list[BoundaryLintFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "scanned_files": self.scanned_files,
            "finding_count": len(self.findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


DEFAULT_BOUNDARY_RULES = [
    BoundaryLintRule(
        "direct-shell-os-system",
        "os.system",
        "shell",
        "direct shell execution bypasses ToolGateway, policy, ledger, sandbox, and audit",
        "wrap shell execution as a runtime-managed tool and call await ctx.call_tool('shell.exec', args)",
    ),
    BoundaryLintRule(
        "direct-shell-subprocess",
        "subprocess.",
        "shell",
        "direct subprocess execution bypasses ToolGateway, policy, ledger, sandbox, and audit",
        "wrap command execution as a runtime-managed tool and call await ctx.call_tool('shell.exec', args)",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-shell-asyncio-subprocess",
        "asyncio.create_subprocess_",
        "shell",
        "direct asyncio subprocess execution bypasses ToolGateway, policy, ledger, sandbox, and audit",
        "wrap command execution as a runtime-managed tool and call await ctx.call_tool('shell.exec', args)",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-http-requests",
        "requests.",
        "network",
        "direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit",
        "register the HTTP/API call as a runtime-managed tool and call await ctx.call_tool(...)",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-http-httpx",
        "httpx.",
        "network",
        "direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit",
        "register the HTTP/API call as a runtime-managed tool and call await ctx.call_tool(...)",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-http-urllib",
        "urllib.request.urlopen",
        "network",
        "direct urllib calls bypass ToolGateway, policy, ledger, budget, replay, and audit",
        "register the HTTP/API call as a runtime-managed tool and call await ctx.call_tool(...)",
    ),
    BoundaryLintRule(
        "direct-email-smtp",
        "smtplib.SMTP",
        "external-side-effect",
        "direct SMTP usage bypasses ToolGateway, policy, ledger, replay, and audit",
        "register email sending as a runtime-managed tool and call await ctx.call_tool('email.send', args)",
    ),
    BoundaryLintRule(
        "direct-cloud-boto3",
        "boto3.",
        "external-side-effect",
        "direct cloud SDK usage bypasses ToolGateway, policy, ledger, replay, and audit",
        "wrap cloud operations as runtime-managed tools and call await ctx.call_tool(...)",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-github-sdk",
        "github.Github",
        "external-side-effect",
        "direct GitHub SDK usage bypasses ToolGateway, policy, ledger, replay, and audit",
        "wrap GitHub actions as runtime-managed tools and call await ctx.call_tool('github.*', args)",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-db-sqlite",
        "sqlite3.connect",
        "database",
        "direct SQLite writes can bypass AgentLedger tool governance, policy, replay, and audit",
        "wrap database mutation as a runtime-managed tool or use an AgentLedger storage adapter for runtime metadata",
    ),
    BoundaryLintRule(
        "direct-db-psycopg",
        "psycopg.connect",
        "database",
        "direct Postgres writes can bypass AgentLedger tool governance, policy, replay, and audit",
        "wrap database mutation as a runtime-managed tool or keep it outside agent side-effect code",
    ),
    BoundaryLintRule(
        "direct-db-psycopg2",
        "psycopg2.connect",
        "database",
        "direct Postgres writes can bypass AgentLedger tool governance, policy, replay, and audit",
        "wrap database mutation as a runtime-managed tool or keep it outside agent side-effect code",
    ),
    BoundaryLintRule(
        "direct-db-pymysql",
        "pymysql.connect",
        "database",
        "direct MySQL writes can bypass AgentLedger tool governance, policy, replay, and audit",
        "wrap database mutation as a runtime-managed tool or keep it outside agent side-effect code",
    ),
    BoundaryLintRule(
        "direct-db-mysql-connector",
        "mysql.connector.connect",
        "database",
        "direct MySQL writes can bypass AgentLedger tool governance, policy, replay, and audit",
        "wrap database mutation as a runtime-managed tool or keep it outside agent side-effect code",
    ),
    BoundaryLintRule(
        "direct-db-sqlalchemy",
        "sqlalchemy.create_engine",
        "database",
        "direct SQLAlchemy engine creation in agent code can bypass AgentLedger side-effect governance",
        "wrap database mutation as a runtime-managed tool and record idempotency/approval metadata",
    ),
    BoundaryLintRule(
        "direct-openai-sdk",
        "openai.",
        "model",
        "direct model SDK usage bypasses model provider archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-anthropic-sdk",
        "anthropic.",
        "model",
        "direct model SDK usage bypasses model provider archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-litellm-sdk",
        "litellm.",
        "model",
        "direct LiteLLM usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-google-genai-sdk",
        "google.genai.",
        "model",
        "direct Google GenAI usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-google-generativeai-sdk",
        "google.generativeai.",
        "model",
        "direct Google Generative AI usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-mistral-sdk",
        "mistralai.",
        "model",
        "direct Mistral SDK usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-cohere-sdk",
        "cohere.",
        "model",
        "direct Cohere SDK usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-groq-sdk",
        "groq.",
        "model",
        "direct Groq SDK usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-ollama-sdk",
        "ollama.",
        "model",
        "direct Ollama SDK usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
    BoundaryLintRule(
        "direct-vertexai-sdk",
        "vertexai.",
        "model",
        "direct Vertex AI usage bypasses model archives, replay, budget, and attribution",
        "call models through the runtime model boundary so requests and responses are archived",
        prefix=True,
    ),
]


def load_boundary_rules(path: str | Path, *, include_defaults: bool = True) -> list[BoundaryLintRule]:
    """Load custom boundary lint rules from a dependency-free JSON rule pack."""
    source = Path(path).read_text(encoding="utf-8")
    data = json.loads(source)
    if isinstance(data, list):
        rule_items = data
    elif isinstance(data, dict):
        rule_items = data.get("rules", [])
    else:
        raise ValueError("boundary lint rule pack must be a JSON object or list")
    if not isinstance(rule_items, list):
        raise ValueError("boundary lint rule pack field 'rules' must be a list")
    rules = list(DEFAULT_BOUNDARY_RULES) if include_defaults else []
    for item in rule_items:
        if not isinstance(item, dict):
            raise ValueError("boundary lint rule entries must be objects")
        rules.append(BoundaryLintRule.from_dict(item))
    return rules


class RuntimeBoundaryLinter:
    """Static best-effort linter for calls that bypass AgentLedger runtime seams."""

    def __init__(self, rules: Iterable[BoundaryLintRule] | None = None) -> None:
        self.rules = list(DEFAULT_BOUNDARY_RULES if rules is None else rules)

    def scan(self, paths: Iterable[str | Path], *, exclude: Iterable[str] = ()) -> BoundaryLintReport:
        files = list(self._iter_python_files(paths, exclude=exclude))
        findings: list[BoundaryLintFinding] = []
        for path in files:
            findings.extend(self._scan_file(path))
        scanned = [str(path) for path in files]
        return BoundaryLintReport(passed=not findings, scanned_files=scanned, findings=findings)

    def _iter_python_files(self, paths: Iterable[str | Path], *, exclude: Iterable[str]) -> Iterable[Path]:
        exclude_parts = tuple(part for part in exclude if part)
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                for candidate in sorted(path.rglob("*.py")):
                    if self._should_skip(candidate, exclude_parts):
                        continue
                    yield candidate
            elif path.suffix == ".py" and not self._should_skip(path, exclude_parts):
                yield path

    def _should_skip(self, path: Path, exclude_parts: tuple[str, ...]) -> bool:
        parts = set(path.parts)
        if parts & {"__pycache__", ".git", ".venv", "venv", "node_modules"}:
            return True
        text = str(path)
        return any(part in text for part in exclude_parts)

    def _scan_file(self, path: Path) -> list[BoundaryLintFinding]:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return [
                BoundaryLintFinding(
                    path=str(path),
                    line=exc.lineno or 1,
                    column=exc.offset or 1,
                    rule_id="python-syntax-error",
                    severity="error",
                    callee="<parse>",
                    category="syntax",
                    message=exc.msg,
                    suggestion="fix Python syntax before runtime boundary lint can inspect this file",
                )
            ]
        visitor = _BoundaryVisitor(path=path, lines=lines, rules=self.rules)
        visitor.visit(tree)
        return visitor.findings


class _BoundaryVisitor(ast.NodeVisitor):
    def __init__(self, *, path: Path, lines: list[str], rules: list[BoundaryLintRule]) -> None:
        self.path = path
        self.lines = lines
        self.rules = rules
        self.import_aliases: dict[str, str] = {}
        self.object_aliases: dict[str, str] = {}
        self.findings: list[BoundaryLintFinding] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.import_aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.module:
            return
        for alias in node.names:
            self.import_aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        callee = self._resolved_callee(node.value.func) if isinstance(node.value, ast.Call) else None
        if callee and self._is_external_client_factory(callee):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.object_aliases[target.id] = callee

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
            callee = self._resolved_callee(node.value.func) if isinstance(node.value, ast.Call) else None
            if callee and self._is_external_client_factory(callee) and isinstance(node.target, ast.Name):
                self.object_aliases[node.target.id] = callee

    def visit_Call(self, node: ast.Call) -> None:
        callee = self._resolved_callee(node.func)
        if callee is None and isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        if callee and not self._is_ignored(node.lineno):
            if self._scan_special_call(node, callee):
                self.generic_visit(node)
                return
            for rule in self.rules:
                if rule.matches(callee):
                    self._add_finding(node, rule_id=rule.rule_id, callee=callee, category=rule.category, message=rule.message, suggestion=rule.suggestion)
                    break
        self.generic_visit(node)

    def _scan_special_call(self, node: ast.Call, callee: str) -> bool:
        emitted = False
        if callee in {"open", "io.open"} and self._open_writes(node):
            self._add_finding(
                node,
                rule_id="direct-file-write-open",
                callee=callee,
                category="filesystem",
                message="direct file writes bypass ToolGateway, policy, ledger, sandbox, and audit",
                suggestion="wrap file mutation as a runtime-managed tool and call await ctx.call_tool(...)",
            )
            emitted = True
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if attr in {"write_text", "write_bytes", "unlink"}:
            self._add_finding(
                node,
                rule_id=f"direct-file-{attr.replace('_', '-')}",
                callee=callee,
                category="filesystem",
                message="direct filesystem mutation bypasses ToolGateway, policy, ledger, sandbox, and audit",
                suggestion="wrap filesystem mutation as a runtime-managed tool and call await ctx.call_tool(...)",
            )
            emitted = True
        if callee.endswith("ToolSpec") or callee == "tool" or callee.endswith(".tool"):
            emitted = self._scan_tool_metadata(node, callee) or emitted
        return emitted

    def _scan_tool_metadata(self, node: ast.Call, callee: str) -> bool:
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        side_effect = self._literal_string(keywords.get("side_effect")) or "none"
        risk_level = self._literal_string(keywords.get("risk_level")) or "low"
        idempotency_required = self._literal_bool(keywords.get("idempotency_required"))
        if idempotency_required is None:
            idempotency_required = self._literal_bool(keywords.get("idempotency"))
        approval_required = self._literal_bool(keywords.get("approval_required"))
        sandbox_required = self._literal_bool(keywords.get("sandbox_required"))
        emitted = False
        if side_effect not in {"", "none", "read", "read_only"} and idempotency_required is not True:
            self._add_finding(
                node,
                rule_id="tool-side-effect-missing-idempotency",
                callee=callee,
                category="tool-metadata",
                message="side-effecting tools should declare idempotency_required so retries and replay can be governed",
                suggestion="set idempotency_required=True on ToolSpec or idempotency=True on the @tool decorator",
            )
            emitted = True
        if risk_level in {"high", "critical"} and approval_required is not True:
            self._add_finding(
                node,
                rule_id="tool-high-risk-missing-approval",
                callee=callee,
                category="tool-metadata",
                message="high-risk tools should require approval before side effects",
                suggestion="set approval_required=True or document a project-specific lint exception",
            )
            emitted = True
        if risk_level in {"high", "critical"} and sandbox_required is not True and side_effect in {"shell", "code", "filesystem", "external_write"}:
            self._add_finding(
                node,
                rule_id="tool-high-risk-missing-sandbox",
                callee=callee,
                category="tool-metadata",
                message="high-risk execution or filesystem tools should declare a sandbox boundary",
                suggestion="set sandbox_required=True and configure a sandbox adapter when executing untrusted commands or code",
            )
            emitted = True
        return emitted

    def _open_writes(self, node: ast.Call) -> bool:
        mode_node = node.args[1] if len(node.args) >= 2 else None
        for keyword in node.keywords:
            if keyword.arg == "mode":
                mode_node = keyword.value
                break
        if mode_node is None:
            return False
        mode = self._literal_string(mode_node)
        return bool(mode and any(flag in mode for flag in ("w", "a", "x", "+")))

    def _literal_string(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _literal_bool(self, node: ast.AST | None) -> bool | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return node.value
        return None

    def _add_finding(self, node: ast.Call, *, rule_id: str, callee: str, category: str, message: str, suggestion: str) -> None:
        self.findings.append(
            BoundaryLintFinding(
                path=str(self.path),
                line=node.lineno,
                column=node.col_offset + 1,
                rule_id=rule_id,
                severity="error",
                callee=callee,
                category=category,
                message=message,
                suggestion=suggestion,
            )
        )

    def _resolved_callee(self, node: ast.AST) -> str | None:
        raw = self._dotted_name(node)
        if not raw:
            return None
        first, _, rest = raw.partition(".")
        if first in self.object_aliases:
            return f"{self.object_aliases[first]}.{rest}" if rest else self.object_aliases[first]
        if first in self.import_aliases:
            target = self.import_aliases[first]
            if rest and target.split(".")[-1] == rest.split(".", 1)[0]:
                rest = rest.partition(".")[2]
            return f"{target}.{rest}" if rest else target
        return raw

    def _dotted_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._dotted_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def _is_external_client_factory(self, callee: str) -> bool:
        return callee in {
            "requests.Session",
            "httpx.Client",
            "httpx.AsyncClient",
            "openai.OpenAI",
            "openai.AsyncOpenAI",
            "anthropic.Anthropic",
            "anthropic.AsyncAnthropic",
            "google.genai.Client",
            "google.generativeai.GenerativeModel",
            "mistralai.Mistral",
            "cohere.Client",
            "cohere.AsyncClient",
            "groq.Groq",
            "groq.AsyncGroq",
            "ollama.Client",
            "ollama.AsyncClient",
            "boto3.client",
            "boto3.resource",
            "github.Github",
        }

    def _is_ignored(self, lineno: int) -> bool:
        current = self.lines[lineno - 1] if 0 < lineno <= len(self.lines) else ""
        previous = self.lines[lineno - 2] if 1 < lineno <= len(self.lines) else ""
        return IGNORE_SAME_LINE in current or IGNORE_NEXT_LINE in previous
