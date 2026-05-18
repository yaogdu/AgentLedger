use agentledger::{
    debug_html, export_evidence, replay, AgentContext, BudgetLimits, MemoryStore, Runtime,
    RuntimeError, State, ToolSpec, Value,
};
use std::collections::HashMap;
use std::fs;
use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use std::sync::{LazyLock, Mutex};

// ════════════════════════════════════════════════════════════
// ANSI Colors
// ════════════════════════════════════════════════════════════
const C_R: &str = "\x1b[91m";
const C_G: &str = "\x1b[92m";
const C_Y: &str = "\x1b[93m";
const C_B: &str = "\x1b[94m";
const C_M: &str = "\x1b[95m";
const C_C: &str = "\x1b[96m";
const C_BOLD: &str = "\x1b[1m";
const C_DIM: &str = "\x1b[2m";
const C_RST: &str = "\x1b[0m";

// ════════════════════════════════════════════════════════════
// Mock data (LazyLock for static initialization)
// ════════════════════════════════════════════════════════════
static MOCK_FLIGHTS: LazyLock<Mutex<Vec<HashMap<String, Value>>>> = LazyLock::new(|| {
    Mutex::new(vec![HashMap::from([
        ("id".to_string(), Value::String("FL-002".into())),
        ("from_city".to_string(), Value::String("Beijing".into())),
        ("from_code".to_string(), Value::String("PEK".into())),
        ("to_city".to_string(), Value::String("Tokyo".into())),
        ("to_code".to_string(), Value::String("NRT".into())),
        ("date".to_string(), Value::String("2025-06-15".into())),
        ("airline".to_string(), Value::String("JAL".into())),
        ("price_usd".to_string(), Value::Number(580.0)),
    ])])
});

static MOCK_HOTELS: LazyLock<Mutex<Vec<HashMap<String, Value>>>> = LazyLock::new(|| {
    Mutex::new(vec![HashMap::from([
        ("id".to_string(), Value::String("HT-002".into())),
        ("city".to_string(), Value::String("Tokyo".into())),
        ("name".to_string(), Value::String("APA Hotel Shinjuku".into())),
        ("nightly_usd".to_string(), Value::Number(85.0)),
        ("stars".to_string(), Value::Number(3.0)),
    ])])
});

static BOOKING_DB: LazyLock<Mutex<HashMap<String, HashMap<String, Value>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

// ════════════════════════════════════════════════════════════
// Value helpers (since `state()` is private)
// ════════════════════════════════════════════════════════════

fn make_state(items: &[(&str, Value)]) -> State {
    let mut out = State::new();
    for (key, value) in items {
        out.insert(key.to_string(), value.clone());
    }
    out
}

fn get_string(obj: &Value, key: &str) -> String {
    match obj {
        Value::Object(map) => match map.get(key) {
            Some(Value::String(s)) => s.clone(),
            _ => String::new(),
        },
        _ => String::new(),
    }
}

fn get_number(obj: &Value, key: &str) -> f64 {
    match obj {
        Value::Object(map) => match map.get(key) {
            Some(Value::Number(n)) => *n,
            _ => 0.0,
        },
        _ => 0.0,
    }
}

fn string_arg(args: &State, key: &str) -> String {
    match args.get(key) {
        Some(Value::String(s)) => s.clone(),
        _ => String::new(),
    }
}

fn string_field(map: &HashMap<String, Value>, key: &str) -> String {
    match map.get(key) {
        Some(Value::String(s)) => s.clone(),
        _ => String::new(),
    }
}

// ════════════════════════════════════════════════════════════
// Tool implementations
// ════════════════════════════════════════════════════════════

fn search_flights(args: State) -> agentledger::Result<Value> {
    let origin = string_arg(&args, "from").to_lowercase();
    let dest = string_arg(&args, "to").to_lowercase();
    let flights = MOCK_FLIGHTS.lock().unwrap();
    let results: Vec<Value> = flights
        .iter()
        .filter(|f| {
            let fc = string_field(f, "from_city").to_lowercase();
            let fcode = string_field(f, "from_code").to_lowercase();
            let tc = string_field(f, "to_city").to_lowercase();
            let tcode = string_field(f, "to_code").to_lowercase();
            (fc.contains(&origin) || fcode.contains(&origin))
                && (tc.contains(&dest) || tcode.contains(&dest))
        })
        .map(|f| Value::Object(f.clone()))
        .collect();
    let count = results.len();
    Ok(Value::Object(make_state(&[
        ("results", Value::Array(results)),
        ("count", Value::Number(count as f64)),
    ])))
}

fn search_hotels(args: State) -> agentledger::Result<Value> {
    let city = string_arg(&args, "city").to_lowercase();
    let hotels = MOCK_HOTELS.lock().unwrap();
    let results: Vec<Value> = hotels
        .iter()
        .filter(|h| string_field(h, "city").to_lowercase() == city)
        .map(|h| Value::Object(h.clone()))
        .collect();
    let count = results.len();
    Ok(Value::Object(make_state(&[
        ("results", Value::Array(results)),
        ("count", Value::Number(count as f64)),
    ])))
}

fn check_weather(args: State) -> agentledger::Result<Value> {
    let city = string_arg(&args, "city");
    match city.as_str() {
        "Tokyo" => Ok(Value::Object(make_state(&[
            ("city", Value::String("Tokyo".into())),
            ("temp_c", Value::Number(24.0)),
            ("condition", Value::String("Partly Cloudy".into())),
            ("humidity", Value::Number(65.0)),
        ]))),
        _ => Ok(Value::Object(make_state(&[
            ("city", Value::String(city)),
            ("temp_c", Value::Number(20.0)),
            ("condition", Value::String("Unknown".into())),
        ]))),
    }
}

fn book_flight(args: State) -> agentledger::Result<Value> {
    let flight_id = string_arg(&args, "flight_id");
    let passenger = string_arg(&args, "passenger");
    let prefix: String = passenger.chars().take(3).collect();
    let ref_key = format!("BK-F-{}-{}", flight_id, prefix.to_uppercase());

    let mut db = BOOKING_DB.lock().unwrap();
    if let Some(existing) = db.get(&ref_key) {
        return Ok(Value::Object(existing.clone()));
    }

    let flights = MOCK_FLIGHTS.lock().unwrap();
    let f = flights.iter().find(|f| string_field(f, "id") == flight_id);
    match f {
        Some(flight) => {
            let airline = string_field(flight, "airline");
            let price = get_number(&Value::Object(flight.clone()), "price_usd");
            let booking = make_state(&[
                ("booking_ref", Value::String(ref_key.clone())),
                ("type", Value::String("flight".into())),
                ("airline", Value::String(airline)),
                ("price_usd", Value::Number(price)),
                ("status", Value::String("confirmed".into())),
                ("external_id", Value::String(ref_key.clone())),
            ]);
            db.insert(ref_key, booking.clone());
            Ok(Value::Object(booking))
        }
        None => Err(RuntimeError(format!("flight not found: {}", flight_id))),
    }
}

fn book_hotel(args: State) -> agentledger::Result<Value> {
    let hotel_id = string_arg(&args, "hotel_id");
    let guest = string_arg(&args, "guest");
    let prefix: String = guest.chars().take(3).collect();
    let ref_key = format!("BK-H-{}-{}", hotel_id, prefix.to_uppercase());

    let mut db = BOOKING_DB.lock().unwrap();
    if let Some(existing) = db.get(&ref_key) {
        return Ok(Value::Object(existing.clone()));
    }

    let hotels = MOCK_HOTELS.lock().unwrap();
    let h = hotels.iter().find(|h| string_field(h, "id") == hotel_id);
    match h {
        Some(hotel) => {
            let name = string_field(hotel, "name");
            let nightly = get_number(&Value::Object(hotel.clone()), "nightly_usd");
            let booking = make_state(&[
                ("booking_ref", Value::String(ref_key.clone())),
                ("type", Value::String("hotel".into())),
                ("name", Value::String(name)),
                ("price_total_usd", Value::Number(nightly * 5.0)),
                ("status", Value::String("confirmed".into())),
                ("external_id", Value::String(ref_key.clone())),
            ]);
            db.insert(ref_key, booking.clone());
            Ok(Value::Object(booking))
        }
        None => Err(RuntimeError(format!("hotel not found: {}", hotel_id))),
    }
}

// ════════════════════════════════════════════════════════════
// Agent logic (called per attempt)
// ════════════════════════════════════════════════════════════

fn travel_planner(
    runtime: &mut Runtime,
    ctx: &mut AgentContext,
    attempt: u64,
) -> agentledger::Result<()> {
    // Phase 1: Research
    let flights = runtime.call_tool(ctx, "travel.search_flights", make_state(&[
        ("from", "Beijing".into()),
        ("to", "Tokyo".into()),
    ]))?;
    let hotels = runtime.call_tool(ctx, "travel.search_hotels", make_state(&[
        ("city", "Tokyo".into()),
    ]))?;
    let weather = runtime.call_tool(ctx, "travel.check_weather", make_state(&[
        ("city", "Tokyo".into()),
    ]))?;

    let fc = get_number(&flights, "count") as i64;
    let hc = get_number(&hotels, "count") as i64;
    let wt = get_number(&weather, "temp_c");
    ctx.write_state("research", Value::Object(make_state(&[
        ("flights", Value::Number(fc as f64)),
        ("hotels", Value::Number(hc as f64)),
        ("weather", Value::Number(wt)),
    ])));

    // Phase 2: Book flight (approval required)
    let flight = runtime.call_tool(ctx, "travel.book_flight", make_state(&[
        ("flight_id", "FL-002".into()),
        ("passenger", "Demo User".into()),
        ("_logical_operation", "book-demo-flight".into()),
    ]))?;

    // Phase 3: Simulated crash on attempt 2
    if attempt == 2 {
        return Err(RuntimeError("retryable".to_string()));
    }

    // Phase 4: Book hotel (approval required)
    let hotel = runtime.call_tool(ctx, "travel.book_hotel", make_state(&[
        ("hotel_id", "HT-002".into()),
        ("check_in", "2025-06-15".into()),
        ("check_out", "2025-06-20".into()),
        ("guest", "Demo User".into()),
        ("_logical_operation", "book-demo-hotel".into()),
    ]))?;

    let flight_ref = get_string(&flight, "booking_ref");
    let hotel_ref = get_string(&hotel, "booking_ref");
    ctx.write_state("bookings", Value::Object(make_state(&[
        ("flight", Value::String(flight_ref)),
        ("hotel", Value::String(hotel_ref)),
    ])));
    ctx.write_state("trip_status", Value::String("confirmed".into()));
    Ok(())
}

// ════════════════════════════════════════════════════════════
// Step claim helper
// ════════════════════════════════════════════════════════════

fn claim_context(
    runtime: &mut Runtime,
    run_id: &str,
    worker: &str,
    role: &str,
) -> AgentContext {
    let claim = runtime.store.claim_step(worker, run_id, 60.0)
        .expect("claim step failed");
    let mut payload = State::new();
    payload.insert("agent_role".to_string(), Value::String(role.to_string()));
    payload.insert("attempt".to_string(), Value::Number(claim.attempt as f64));
    runtime.store.append_event(
        run_id,
        Some(&claim.session_id),
        Some(&claim.step_id),
        "agent_started",
        payload,
        Some(role),
        Some(claim.state_version),
        None,
    );
    AgentContext {
        run_id: claim.run_id.clone(),
        session_id: claim.session_id,
        step_id: claim.step_id.clone(),
        agent_role: role.to_string(),
        lease_token: claim.lease_token.clone(),
        attempt: claim.attempt,
        state_version: claim.state_version,
        pending_patch: State::new(),
    }
}

// ════════════════════════════════════════════════════════════
// Display helpers
// ════════════════════════════════════════════════════════════

fn wait(msg: &str) {
    print!("\n{}  ⏎ {}...{}", C_DIM, msg, C_RST);
    io::stdout().flush().ok();
    let mut line = String::new();
    io::stdin().lock().read_line(&mut line).ok();
}

fn show_rows(label: &str, headers: &[&str], rows: &[Vec<String>], color: &str) {
    if rows.is_empty() {
        println!("\n  {}{}:{} {}(empty){}", color, label, C_RST, C_DIM, C_RST);
        return;
    }
    println!("\n  {}{} ({} rows):{}", color, label, rows.len(), C_RST);
    for row in rows {
        let items: Vec<String> = headers
            .iter()
            .zip(row.iter())
            .map(|(h, v)| format!("{}={}{}{}", h, C_BOLD, v, C_RST))
            .collect();
        println!("    {}{}{}", C_DIM, items.join(" | "), C_RST);
    }
}

fn show_db(store: &MemoryStore, run_id: &str) {
    // Runs
    let mut run_rows = Vec::new();
    if let Ok(run) = store.run(run_id) {
        let short_id = if run.run_id.len() > 24 {
            format!("{}...", &run.run_id[..24])
        } else {
            run.run_id.clone()
        };
        run_rows.push(vec![short_id, run.status, run.state_version.to_string()]);
    }
    show_rows("Runs", &["run_id", "status", "state_version"], &run_rows, C_B);

    // Steps
    let step_rows: Vec<Vec<String>> = store
        .steps(run_id)
        .into_iter()
        .map(|s| {
            let short_id = if s.step_id.len() > 24 {
                format!("{}...", &s.step_id[..24])
            } else {
                s.step_id.clone()
            };
            vec![short_id, s.status, s.attempt.to_string()]
        })
        .collect();
    show_rows("Steps", &["step_id", "status", "attempt"], &step_rows, C_B);

    // Tool Ledger
    let ledger_rows: Vec<Vec<String>> = store
        .ledger(run_id)
        .into_iter()
        .map(|tl| {
            let key = &tl.idempotency_key;
            let short_key = match key.rfind(':') {
                Some(idx) => {
                    let prev = key[..idx].rfind(':').unwrap_or(0);
                    if prev > 0 {
                        format!("{}:{}", &key[prev + 1..idx], &key[idx + 1..])
                    } else {
                        format!("{}", &key[idx + 1..])
                    }
                }
                None => key[..key.len().min(25)].to_string(),
            };
            vec![tl.tool_name, tl.status, short_key]
        })
        .collect();
    show_rows(
        "Tool Ledger",
        &["tool", "status", "idemp_key"],
        &ledger_rows,
        C_Y,
    );

    // Approval requests
    let approval_rows: Vec<Vec<String>> = store
        .approval_requests(run_id)
        .into_iter()
        .map(|a| {
            let approved_by = a.approved_by.unwrap_or_else(|| "-".to_string());
            vec![a.tool_name, a.status, approved_by]
        })
        .collect();
    show_rows(
        "Approval Requests",
        &["tool", "status", "approved_by"],
        &approval_rows,
        C_R,
    );

    println!();
}

// ════════════════════════════════════════════════════════════
// Main
// ════════════════════════════════════════════════════════════

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let root = if args.len() > 1 {
        PathBuf::from(&args[1])
    } else {
        PathBuf::from(".agentledger-rust")
    };
    let _ = fs::create_dir_all(&root);

    // Intro
    println!(
        "\n{}{}  ╔════════════════════════════════════════════════════╗{}",
        C_BOLD, C_C, C_RST
    );
    println!(
        "{}{}  ║   AgentLedger Travel Assistant (Rust) — Interactive Demo  ║{}",
        C_BOLD, C_C, C_RST
    );
    println!(
        "{}{}  ║   See real database state at every step                 ║{}",
        C_BOLD, C_C, C_RST
    );
    println!(
        "{}{}  ╚════════════════════════════════════════════════════╝{}",
        C_BOLD, C_C, C_RST
    );

    println!(
        "\n  {}AgentLedger — Durable Execution Runtime for AI Agents{}",
        C_DIM, C_RST
    );
    println!("  ┌────────────────────────────────────────────────────┐");
    println!(
        "  │  {}✓{} Durable execution — crash recovery              │",
        C_G, C_RST
    );
    println!(
        "  │  {}✓{} Tool Ledger — idempotent replay                │",
        C_G, C_RST
    );
    println!(
        "  │  {}✓{} Approval gates — human-in-the-loop              │",
        C_G, C_RST
    );
    println!(
        "  │  {}✓{} Policy engine — risk-based access               │",
        C_G, C_RST
    );
    println!(
        "  │  {}✓{} Budget control — tool call limits               │",
        C_G, C_RST
    );
    println!(
        "  │  {}✓{} Evidence export — full audit trail              │",
        C_G, C_RST
    );
    println!("  └────────────────────────────────────────────────────┘");

    wait("Press Enter to start / 按 Enter 开始");

    // ════════════════════════════════════════════════════════
    // Step 1: Setup
    // ════════════════════════════════════════════════════════
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_B,
        "═".repeat(60)
    );
    println!(
        "{}{}  Step 1: Initialize — Register tools, configure policy{}",
        C_BOLD, C_B, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_B,
        "═".repeat(60)
    );

    let mut runtime = Runtime::new();
    runtime.set_budget(BudgetLimits {
        max_tool_calls: Some(25.0),
        max_model_tokens: None,
        max_total_usd: None,
    });

    // Register tools
    runtime.register_tool(
        ToolSpec::new("travel.search_flights", Box::new(search_flights))
            .side_effect("none")
            .risk_level("low")
            .input_schema(Value::Object(make_state(&[
                ("type", "object".into()),
                (
                    "required",
                    Value::Array(vec!["from".into(), "to".into()]),
                ),
            ]))),
    );
    runtime.register_tool(
        ToolSpec::new("travel.search_hotels", Box::new(search_hotels))
            .side_effect("none")
            .risk_level("low")
            .input_schema(Value::Object(make_state(&[
                ("type", "object".into()),
                ("required", Value::Array(vec!["city".into()])),
            ]))),
    );
    runtime.register_tool(
        ToolSpec::new("travel.check_weather", Box::new(check_weather))
            .side_effect("none")
            .risk_level("low")
            .input_schema(Value::Object(make_state(&[
                ("type", "object".into()),
                ("required", Value::Array(vec!["city".into()])),
            ]))),
    );
    runtime.register_tool(
        ToolSpec::new("travel.book_flight", Box::new(book_flight))
            .side_effect("external_write")
            .risk_level("high")
            .idempotency_required(true)
            .approval_required(true)
            .input_schema(Value::Object(make_state(&[
                ("type", "object".into()),
                (
                    "required",
                    Value::Array(vec!["flight_id".into(), "passenger".into()]),
                ),
            ]))),
    );
    runtime.register_tool(
        ToolSpec::new("travel.book_hotel", Box::new(book_hotel))
            .side_effect("external_write")
            .risk_level("high")
            .idempotency_required(true)
            .approval_required(true)
            .input_schema(Value::Object(make_state(&[
                ("type", "object".into()),
                (
                    "required",
                    Value::Array(vec!["hotel_id".into(), "guest".into()]),
                ),
            ]))),
    );

    println!("\n  {}Registered 5 tools:{}", C_C, C_RST);
    for (name, risk, approval) in [
        ("travel.search_flights", "low", false),
        ("travel.search_hotels", "low", false),
        ("travel.check_weather", "low", false),
        ("travel.book_flight", "high", true),
        ("travel.book_hotel", "high", true),
    ] {
        let rc = if risk == "low" { C_G } else { C_R };
        let ac = if approval {
            format!("{}needs approval{}", C_R, C_RST)
        } else {
            format!("{}no approval{}", C_G, C_RST)
        };
        println!(
            "    {}•{} {}  [{}{}{}] [{}]",
            C_DIM, C_RST, name, rc, risk, C_RST, ac
        );
    }
    println!(
        "  {}Policy: Rust uses risk-based policy (low=allow, high=deny+approval){}",
        C_DIM, C_RST
    );
    println!("  {}Budget: max 25 tool calls{}", C_DIM, C_RST);

    let (run_id, _step_id) = runtime.create_run(make_state(&[
        ("trip", "Tokyo".into()),
        ("budget_usd", Value::Number(3000.0)),
    ]));
    println!(
        "\n  {}Run created: {}{}{}",
        C_B, C_BOLD, run_id, C_RST
    );
    show_db(&runtime.store, &run_id);
    wait("Press Enter to continue");

    // ════════════════════════════════════════════════════════
    // Step 2: Attempt 1 — Approval interception
    // ════════════════════════════════════════════════════════
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_R,
        "═".repeat(60)
    );
    println!(
        "{}{}  Step 2: Attempt 1 — Agent runs → Approval triggered{}",
        C_BOLD, C_R, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_R,
        "═".repeat(60)
    );
    println!(
        "\n  {}Agent executing: search flights → search hotels → check weather → book flight...{}",
        C_DIM, C_RST
    );

    {
        let mut ctx = claim_context(&mut runtime, &run_id, "worker-rust", "TravelPlanner");
        let result = travel_planner(&mut runtime, &mut ctx, 1);
        match result {
            Err(err) if err.0.starts_with("approval required:") => {
                let approval_id = err.0.trim_start_matches("approval required:");
                runtime
                    .store
                    .mark_waiting_human(&run_id, &ctx.step_id, &err.0, approval_id);
            }
            Err(err) => return Err(format!("unexpected error at step 2: {}", err.0).into()),
            Ok(()) => {}
        }
    }

    println!(
        "\n  {}book_flight triggered approval! Runtime paused, waiting for human.{}",
        C_R, C_RST
    );
    show_db(&runtime.store, &run_id);
    println!(
        "  {}Note: Tool Ledger has RESERVED entry, approval status is PENDING{}",
        C_R, C_RST
    );
    wait("Press Enter to approve / 按 Enter 审批");

    for req in runtime.store.approval_requests(&run_id) {
        if req.status == "PENDING" {
            runtime
                .store
                .approve_request(&req.approval_id, "traveler", "Within budget, approved")?;
            println!(
                "\n  {}✅ Approved: {} — by traveler{}",
                C_G, req.tool_name, C_RST
            );
        }
    }
    show_db(&runtime.store, &run_id);
    wait("Press Enter to continue");

    // ════════════════════════════════════════════════════════
    // Step 3: Attempt 2 — Execute + Crash
    // ════════════════════════════════════════════════════════
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_Y,
        "═".repeat(60)
    );
    println!(
        "{}{}  Step 3: Attempt 2 — Approved → Execute booking → Simulated crash{}",
        C_BOLD, C_Y, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_Y,
        "═".repeat(60)
    );
    println!(
        "\n  {}Re-running agent (approval passed, book_flight will execute)...{}",
        C_DIM, C_RST
    );

    {
        let mut ctx = claim_context(&mut runtime, &run_id, "worker-rust", "TravelPlanner");
        let result = travel_planner(&mut runtime, &mut ctx, 2);
        match result {
            Err(err) if err.0 == "retryable" => {
                runtime.store.mark_retry(
                    &run_id,
                    &ctx.step_id,
                    "RetryableAgentError",
                    "after flight booking",
                );
            }
            Err(err) if err.0.starts_with("approval required:") => {
                let approval_id = err.0.trim_start_matches("approval required:");
                runtime
                    .store
                    .mark_waiting_human(&run_id, &ctx.step_id, &err.0, approval_id);
            }
            Err(err) => return Err(format!("unexpected error at step 3: {}", err.0).into()),
            Ok(()) => {}
        }
    }

    println!(
        "\n  {}Agent booked flight, then crashed before committing state!{}",
        C_Y, C_RST
    );
    println!(
        "  {}Flight is booked in external system, but agent state was NOT persisted.{}",
        C_Y, C_RST
    );
    show_db(&runtime.store, &run_id);
    println!(
        "  {}Key: Tool Ledger book_flight status = {}SUCCEEDED{} (external side effect executed){}",
        C_Y, C_G, C_Y, C_RST
    );
    println!(
        "  {}      Step status = retry_scheduled (state not committed, waiting for retry){}",
        C_Y, C_RST
    );
    wait("Press Enter to continue");

    // ════════════════════════════════════════════════════════
    // Step 4: Attempt 3 — Recovery + Hotel approval
    // ════════════════════════════════════════════════════════
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_G,
        "═".repeat(60)
    );
    println!(
        "{}{}  Step 4: Attempt 3 — Crash recovery → Tool Ledger idempotent replay{}",
        C_BOLD, C_G, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_G,
        "═".repeat(60)
    );
    println!(
        "\n  {}Agent re-executes. book_flight: Tool Ledger sees SUCCEEDED record...{}",
        C_DIM, C_RST
    );
    println!(
        "  {}{}→ Returns cached result, no duplicate API call, no double charge!{}",
        C_DIM, C_G, C_RST
    );

    {
        let mut ctx = claim_context(&mut runtime, &run_id, "worker-rust", "TravelPlanner");
        let result = travel_planner(&mut runtime, &mut ctx, 3);
        match result {
            Err(err) if err.0.starts_with("approval required:") => {
                let approval_id = err.0.trim_start_matches("approval required:");
                runtime
                    .store
                    .mark_waiting_human(&run_id, &ctx.step_id, &err.0, approval_id);
            }
            Err(err) => return Err(format!("unexpected error at step 4: {}", err.0).into()),
            Ok(()) => {}
        }
    }

    println!(
        "\n  {}✅ Flight idempotent replay successful! (no duplicate _book_flight call){}",
        C_G, C_RST
    );
    println!("  {}Hotel booking → triggers approval again{}", C_R, C_RST);

    for req in runtime.store.approval_requests(&run_id) {
        if req.status == "PENDING" {
            runtime
                .store
                .approve_request(&req.approval_id, "traveler", "Hotel within budget, approved")?;
            println!(
                "\n  {}✅ Approved: {} — by traveler{}",
                C_G, req.tool_name, C_RST
            );
        }
    }
    show_db(&runtime.store, &run_id);
    wait("Press Enter to continue");

    // ════════════════════════════════════════════════════════
    // Step 5: Attempt 4 — Complete
    // ════════════════════════════════════════════════════════
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_G,
        "═".repeat(60)
    );
    println!(
        "{}{}  Step 5: Attempt 4 — Hotel approved → Full execution → State committed{}",
        C_BOLD, C_G, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_G,
        "═".repeat(60)
    );

    {
        let mut ctx = claim_context(&mut runtime, &run_id, "worker-rust", "TravelPlanner");
        travel_planner(&mut runtime, &mut ctx, 4)?;
        runtime.store.commit_state_patch(
            &run_id,
            &ctx.step_id,
            &ctx.lease_token,
            ctx.state_version,
            ctx.pending_patch,
        )?;
    }

    {
        let db = BOOKING_DB.lock().unwrap();
        if db.len() != 2 {
            return Err(format!("Expected 2 bookings, got {}", db.len()).into());
        }
    }

    println!(
        "\n  {}✅ Travel planning complete! State persisted to database.{}",
        C_G, C_RST
    );
    show_db(&runtime.store, &run_id);
    println!(
        "  {}Step status = completed, State has bookings + trip_status{}",
        C_G, C_RST
    );
    let db = BOOKING_DB.lock().unwrap();
    let keys: Vec<String> = db.keys().cloned().collect();
    println!(
        "  {}External bookings: {:?} ({} total, no duplicates){}",
        C_G,
        keys,
        keys.len(),
        C_RST
    );
    drop(db);
    wait("Press Enter to continue");

    // ════════════════════════════════════════════════════════
    // Step 6: Evidence + Cost + Replay
    // ════════════════════════════════════════════════════════
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_M,
        "═".repeat(60)
    );
    println!(
        "{}{}  Step 6: Evidence export + Cost attribution + Replay verification{}",
        C_BOLD, C_M, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_M,
        "═".repeat(60)
    );

    let bundle = export_evidence(&runtime.store, &run_id)?;
    let replay_result = replay(&runtime.store, &run_id)?;
    let cost = agentledger::cost_attribution(&runtime.store, &run_id);

    println!(
        "\n  {}Cost attribution: {} tool calls{}",
        C_M, cost.total.tool_calls, C_RST
    );
    println!(
        "  {}Replay: {} events, safe={}{}{}",
        C_M, replay_result.event_count, C_G, replay_result.replay_safe, C_RST
    );
    println!(
        "  {}Evidence bundle: {} events total{}",
        C_M,
        bundle.events.len(),
        C_RST
    );

    // Write evidence HTML
    let html_path = root.join("evidence.html");
    let html = debug_html(&bundle);
    fs::write(&html_path, html)?;
    let html_abs = html_path.canonicalize().unwrap_or_else(|_| html_path.clone());

    // Final summary
    println!(
        "\n{}{}{}",
        C_BOLD,
        C_G,
        "═".repeat(60)
    );
    println!(
        "{}{}  Summary: What AgentLedger (Rust) did in this demo{}",
        C_BOLD, C_G, C_RST
    );
    println!(
        "{}{}{}",
        C_BOLD,
        C_G,
        "═".repeat(60)
    );
    println!(
        "
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │  {g}✓ Durable execution{rst}  Crash → auto retry, state preserved         │
  │                   Step: retry_scheduled → completed           │
  │                                                          │
  │  {g}✓ Tool Ledger{rst}      Idempotent replay, flight booked {bold}1x{rst} only       │
  │                   SUCCEEDED → cached result on retry        │
  │                                                          │
  │  {g}✓ Approval gates{rst}    Flight + hotel each trigger approval          │
  │                   approval_requests records in store        │
  │                                                          │
  │  {g}✓ Policy engine{rst}     Risk-based policy (high → deny+approval)     │
  │                   low-risk tools auto-allowed              │
  │                                                          │
  │  {g}✓ Budget control{rst}    Tracked {tc} tool calls                       │
  │                   BudgetController.before_tool_call()       │
  │                                                          │
  │  {g}✓ Evidence export{rst}   {ec} events recorded                         │
  │                   events stored in memory store             │
  │                                                          │
  │  {g}✓ Cost attribution{rst}  Auto-recorded per run                        │
  │                   CostAttribution by agent                │
  │                                                          │
  │  {g}✓ Replay engine{rst}     Event hash verification passed                │
  │                   Verify history without re-running       │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
",
        g = C_G,
        rst = C_RST,
        bold = C_BOLD,
        tc = cost.total.tool_calls,
        ec = bundle.events.len()
    );

    println!("  {}Storage: in-memory (MemoryStore){}", C_DIM, C_RST);
    println!("  {}Evidence HTML: {:?}{}", C_DIM, html_abs, C_RST);
    println!();

    Ok(())
}
