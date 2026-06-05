use agentledger::{AgentContext, InMemoryMCPToolServer, MCPToolAdapter, Runtime, SandboxExecutor, SandboxPolicy, SandboxResult, State, Value};

fn state(items: &[(&str, Value)]) -> State {
    items
        .iter()
        .map(|(key, value)| ((*key).to_string(), value.clone()))
        .collect()
}

fn create_pr(_name: &str, args: State) -> agentledger::Result<Value> {
    Ok(Value::Object(state(&[
        ("external_id", "PR-1".into()),
        ("title", args["title"].clone()),
    ])))
}

struct DemoSandboxExecutor;

impl SandboxExecutor for DemoSandboxExecutor {
    fn run_tool(&self, args: State, _policy: &SandboxPolicy) -> SandboxResult {
        SandboxResult {
            ok: true,
            output: create_pr("mcp.github.create_pr", args).unwrap_or(Value::Null),
            error: None,
            metadata: state(&[
                ("executor", "demo-local".into()),
                ("isolation_level", "none".into()),
            ]),
        }
    }
}

fn main() -> agentledger::Result<()> {
    let mut runtime = Runtime::new();
    runtime.set_sandbox(Box::new(DemoSandboxExecutor));
    let mut server = InMemoryMCPToolServer::new();
    server.add_tool(
        state(&[
            ("name", "mcp.github.create_pr".into()),
            (
                "inputSchema",
                Value::Object(state(&[
                    ("type", "object".into()),
                    (
                        "required",
                        Value::Array(vec![Value::String("title".to_string())]),
                    ),
                    (
                        "properties",
                        Value::Object(state(&[(
                            "title",
                            Value::Object(state(&[
                                ("type", "string".into()),
                                ("minLength", 1_i64.into()),
                            ])),
                        )])),
                    ),
                ])),
            ),
            (
                "annotations",
                Value::Object(state(&[
                    ("side_effect", "external_write".into()),
                    ("risk_level", "high".into()),
                    ("idempotency_required", true.into()),
                    ("approval_required", true.into()),
                    ("sandbox_required", true.into()),
                    (
                        "sandbox_policy",
                        Value::Object(state(&[
                            ("network", "deny".into()),
                            ("filesystem", "read-only".into()),
                        ])),
                    ),
                ])),
            ),
        ]),
        create_pr,
    );
    let adapter = MCPToolAdapter { client_call: create_pr };
    for descriptor in server.list_tools() {
        runtime.register_tool(adapter.tool_spec_from_descriptor(&descriptor));
    }

    let (run_id, _) = runtime.create_run(State::new());
    let first_claim = runtime.store.claim_step("worker-before-approval", &run_id, 60.0)?;
    let first_ctx = AgentContext {
        run_id: run_id.clone(),
        session_id: first_claim.session_id.clone(),
        step_id: first_claim.step_id.clone(),
        agent_role: "MCPAgent".to_string(),
        lease_token: first_claim.lease_token.clone(),
        attempt: first_claim.attempt,
        state_version: first_claim.state_version,
        pending_patch: State::new(),
    };
    let first = runtime.call_tool(
        &first_ctx,
        "mcp.github.create_pr",
        state(&[
            ("title", "Update runtime docs".into()),
            ("_logical_operation", "docs-pr".into()),
        ]),
    );
    let approval_id = first
        .unwrap_err()
        .0
        .trim_start_matches("approval required:")
        .to_string();
    runtime.store.mark_waiting_human(
        &run_id,
        &first_ctx.step_id,
        "approval required for tool mcp.github.create_pr",
        &approval_id,
    );
    runtime
        .store
        .approve_request(&approval_id, "maintainer", "demo approval")?;

    let second_claim = runtime.store.claim_step("worker-after-approval", &run_id, 60.0)?;
    let mut second_ctx = AgentContext {
        run_id: run_id.clone(),
        session_id: second_claim.session_id.clone(),
        step_id: second_claim.step_id.clone(),
        agent_role: "MCPAgent".to_string(),
        lease_token: second_claim.lease_token.clone(),
        attempt: second_claim.attempt,
        state_version: second_claim.state_version,
        pending_patch: State::new(),
    };
    let result = runtime.call_tool(
        &second_ctx,
        "mcp.github.create_pr",
        state(&[
            ("title", "Update runtime docs".into()),
            ("_logical_operation", "docs-pr".into()),
        ]),
    )?;
    second_ctx.write_state("pull_request", result);
    runtime.store.commit_state_patch(
        &run_id,
        &second_ctx.step_id,
        &second_ctx.lease_token,
        second_ctx.state_version,
        second_ctx.pending_patch,
    )?;

    let approvals = runtime.store.approval_requests(&run_id);
    println!(
        "{{\n  \"run_id\": \"{}\",\n  \"first_attempt_waited_for_approval\": true,\n  \"second_attempt_ok\": true,\n  \"approval_count\": {},\n  \"approval_status\": \"{}\",\n  \"external_action_count\": 1,\n  \"final_state_has_pull_request\": {}\n}}",
        run_id,
        approvals.len(),
        approvals.first().map(|row| row.status.as_str()).unwrap_or(""),
        runtime
            .store
            .final_state(&run_id)?
            .contains_key("pull_request")
    );
    Ok(())
}
