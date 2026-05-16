from agentledger import agent, run


@agent
def hello(ctx):
    return "hello world"


if __name__ == "__main__":
    result = run(hello)
    print(result.output)
    print(result.run_id)
