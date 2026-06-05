use agentledger::{replay, AgentContext, Runtime, State, ToolSpec, Value};

fn state(items: &[(&str, Value)]) -> State {
    items
        .iter()
        .map(|(key, value)| ((*key).to_string(), value.clone()))
        .collect()
}

fn get_string(value: &Value, key: &str) -> String {
    match value {
        Value::Object(map) => match map.get(key) {
            Some(Value::String(text)) => text.clone(),
            _ => String::new(),
        },
        _ => String::new(),
    }
}

fn main() -> agentledger::Result<()> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "ticket.create",
            Box::new(|args| {
                Ok(Value::Object(state(&[
                    ("external_id", "TICKET-1".into()),
                    ("title", args["title"].clone()),
                ])))
            }),
        )
        .side_effect("external_write")
        .idempotency_required(true)
        .input_schema(Value::Object(state(&[
            ("type", "object".into()),
            (
                "required",
                Value::Array(vec![Value::String("title".to_string())]),
            ),
        ]))),
    );
    let (run_id, _) = runtime.create_run(State::new());

    let first_claim = runtime.store.claim_step("worker-before-crash", &run_id, 60.0)?;
    let first_ctx = AgentContext {
        run_id: run_id.clone(),
        session_id: first_claim.session_id.clone(),
        step_id: first_claim.step_id.clone(),
        agent_role: "SupportAgent".to_string(),
        lease_token: first_claim.lease_token.clone(),
        attempt: first_claim.attempt,
        state_version: first_claim.state_version,
        pending_patch: State::new(),
    };
    let ticket = runtime.call_tool(
        &first_ctx,
        "ticket.create",
        state(&[
            ("title", "Investigate failed payment".into()),
            ("_logical_operation", "open-payment-ticket".into()),
        ]),
    )?;
    runtime.store.mark_retry(
        &run_id,
        &first_ctx.step_id,
        "RetryableAgentError",
        "after external ticket create, before state commit",
    );

    let second_claim = runtime.store.claim_step("worker-after-restart", &run_id, 60.0)?;
    let mut second_ctx = AgentContext {
        run_id: run_id.clone(),
        session_id: second_claim.session_id.clone(),
        step_id: second_claim.step_id.clone(),
        agent_role: "SupportAgent".to_string(),
        lease_token: second_claim.lease_token.clone(),
        attempt: second_claim.attempt,
        state_version: second_claim.state_version,
        pending_patch: State::new(),
    };
    let replayed_ticket = runtime.call_tool(
        &second_ctx,
        "ticket.create",
        state(&[
            ("title", "Investigate failed payment".into()),
            ("_logical_operation", "open-payment-ticket".into()),
        ]),
    )?;
    second_ctx.write_state("ticket", replayed_ticket);
    second_ctx.write_state("recovered", true.into());
    runtime.store.commit_state_patch(
        &run_id,
        &second_ctx.step_id,
        &second_ctx.lease_token,
        second_ctx.state_version,
        second_ctx.pending_patch,
    )?;

    let summary = replay(&runtime.store, &run_id)?;
    let ledger = runtime.store.ledger(&run_id);
    let final_state = runtime.store.final_state(&run_id)?;
    println!(
        "{{\n  \"run_id\": \"{}\",\n  \"first_attempt_ok\": false,\n  \"second_attempt_ok\": true,\n  \"external_ticket_count\": 1,\n  \"actual_tool_executions\": 1,\n  \"tool_ledger_count\": {},\n  \"tool_ledger_status\": \"{}\",\n  \"first_ticket_external_id\": \"{}\",\n  \"final_state_recovered\": {},\n  \"replay\": {{\n    \"safe\": {},\n    \"event_count\": {},\n    \"tool_call_count\": {}\n  }}\n}}",
        run_id,
        ledger.len(),
        ledger.first().map(|row| row.status.as_str()).unwrap_or(""),
        get_string(&ticket, "external_id"),
        final_state.get("recovered") == Some(&Value::Bool(true)),
        summary.replay_safe,
        summary.event_count,
        summary.tool_call_count
    );
    Ok(())
}
