use agentledger::{simple_run, AgentContext, Result, State, Value};

fn hello(_ctx: &mut AgentContext, input: State) -> Result<Option<Value>> {
    let mut output = State::new();
    output.insert("message".to_string(), Value::String("hello from rust".to_string()));
    output.insert("input".to_string(), input.get("input").cloned().unwrap_or(Value::Null));
    Ok(Some(Value::Object(output)))
}

fn main() -> Result<()> {
    let mut input = State::new();
    input.insert("input".to_string(), "world".into());
    let result = simple_run(hello, input)?;
    println!("{}", result.run_id);
    Ok(())
}
