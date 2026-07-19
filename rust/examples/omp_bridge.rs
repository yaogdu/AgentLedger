use agentledger::{
    OmpLedgerBridge, OmpModelCall, OmpSession, OmpStateChange, OmpToolExecution, OmpToolProposal,
    OmpTurn, Runtime, State, Value,
};

fn state(items: &[(&str, Value)]) -> State {
    items
        .iter()
        .map(|(key, value)| ((*key).to_string(), value.clone()))
        .collect()
}

fn main() -> agentledger::Result<()> {
    let runtime = Runtime::new();
    let mut bridge = OmpLedgerBridge::new(runtime, "omp-demo");
    let run_id = bridge.record_session_started(OmpSession {
        session_id: "omp-session-1".to_string(),
        initial_state: state(&[("task", "review contract".into())]),
        metadata: state(&[("runtime", "synthetic-omp".into())]),
        ..Default::default()
    })?;
    bridge.record_turn_started(OmpTurn {
        session_id: "omp-session-1".to_string(),
        turn_id: "turn-1".to_string(),
        agent_role: "OMPPlanner".to_string(),
        metadata: state(&[("phase", "planning".into())]),
        ..Default::default()
    })?;
    bridge.record_model_call(OmpModelCall {
        session_id: "omp-session-1".to_string(),
        turn_id: "turn-1".to_string(),
        provider: "openai-compatible-gateway".to_string(),
        model: "legal-router".to_string(),
        request: state(&[(
            "messages",
            Value::Array(vec![Value::Object(state(&[
                ("role", "user".into()),
                ("content", "find payment clause".into()),
            ]))]),
        )]),
        response: state(&[(
            "tool_calls",
            Value::Array(vec![Value::Object(state(&[
                ("name", "contract.search".into()),
                (
                    "arguments",
                    Value::Object(state(&[("clause", "payment".into())])),
                ),
            ]))]),
        )]),
        usage: state(&[
            ("input_tokens", Value::Number(12.0)),
            ("output_tokens", Value::Number(7.0)),
            ("total_tokens", Value::Number(19.0)),
        ]),
        total_usd: 0.003,
        ..Default::default()
    })?;
    bridge.record_tool_proposal(OmpToolProposal {
        session_id: "omp-session-1".to_string(),
        turn_id: "turn-1".to_string(),
        tool_name: "contract.search".to_string(),
        arguments: state(&[("clause", "payment".into())]),
        provider: Some("openai-compatible-gateway".to_string()),
        model: Some("legal-router".to_string()),
        reason: Some("model proposed a contract search".to_string()),
        ..Default::default()
    })?;
    bridge.record_tool_execution(OmpToolExecution {
        session_id: "omp-session-1".to_string(),
        turn_id: "turn-1".to_string(),
        tool_name: "contract.search".to_string(),
        arguments: state(&[("clause", "payment".into())]),
        result: Some(Value::Object(state(&[
            ("matches", Value::Array(vec!["Section 9.2".into()])),
            ("external_id", "search-001".into()),
        ]))),
        ledger_status: Some("SUCCEEDED".to_string()),
        ..Default::default()
    })?;
    bridge.record_state_change(OmpStateChange {
        session_id: "omp-session-1".to_string(),
        turn_id: Some("turn-1".to_string()),
        reason: "persist normalized runtime-adjacent state".to_string(),
        patch: state(&[("memory_version", Value::Number(1.0))]),
        before_snapshot: Some(Value::Object(state(&[("memory_version", Value::Number(0.0))]))),
        after_snapshot: Some(Value::Object(state(&[("memory_version", Value::Number(1.0))]))),
        diff: Some(Value::Object(state(&[(
            "memory_version",
            Value::Array(vec![Value::Number(0.0), Value::Number(1.0)]),
        )]))),
        ..Default::default()
    })?;
    bridge.record_turn_completed(OmpTurn {
        session_id: "omp-session-1".to_string(),
        turn_id: "turn-1".to_string(),
        state_patch: state(&[("last_tool", "contract.search".into())]),
        ..Default::default()
    })?;

    let events = bridge
        .runtime
        .store
        .events(&run_id)
        .iter()
        .map(|event| event.event_type.clone())
        .collect::<Vec<_>>();
    let final_state = bridge.runtime.store.final_state(&run_id)?;
    let rendered_events = format!("{:?}", events);
    let memory_version = match final_state.get("memory_version") {
        Some(Value::Number(value)) => *value,
        _ => 0.0,
    };
    let last_tool = match final_state.get("last_tool") {
        Some(Value::String(value)) => value.as_str(),
        _ => "",
    };
    println!(
        concat!(
            "{{\n",
            "  \"run_id\": \"{}\",\n",
            "  \"events\": {},\n",
            "  \"tool_ledger_count\": {},\n",
            "  \"final_state_memory_version\": {},\n",
            "  \"final_state_last_tool\": \"{}\"\n",
            "}}"
        ),
        run_id,
        rendered_events,
        bridge.runtime.store.ledger(&run_id).len(),
        memory_version,
        last_tool
    );
    Ok(())
}
