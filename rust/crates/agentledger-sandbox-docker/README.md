# agentledger-sandbox-docker

Rust Docker sandbox adapter package for AgentLedger Runtime.

```toml
agentledger-sandbox-docker = "1.2"
```

The crate re-exports `DockerSandboxAdapter` and `DockerSandboxExecutor`. Command execution is disabled by default and must be explicitly enabled. The executor accepts command-style tools through `_sandbox_command` / `command`; it does not serialize arbitrary Rust closures into the container.
