from agentledger import agent, run
import tempfile


@agent
def hello(ctx):
    return "hello world"


if __name__ == "__main__":
    result = run(hello, root=tempfile.mkdtemp(prefix="agentledger-hello-"))
    print(result.output)
    print(result.run_id)
