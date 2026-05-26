def test_imports() -> None:
    from agentledger_sandbox_docker import DockerSandboxExecutor, SandboxPolicy

    assert DockerSandboxExecutor.__name__ == "DockerSandboxExecutor"
    assert SandboxPolicy.__name__ == "SandboxPolicy"

