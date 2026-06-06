package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

// ANSI colors
const (
	cR    = "\033[91m"
	cG    = "\033[92m"
	cY    = "\033[93m"
	cB    = "\033[94m"
	cM    = "\033[95m"
	cC    = "\033[96m"
	cBold = "\033[1m"
	cDim  = "\033[2m"
	cRst  = "\033[0m"
)

// Mock data
var mockFlights = []map[string]any{
	{"id": "FL-002", "from_city": "Beijing", "from_code": "PEK", "to_city": "Tokyo", "to_code": "NRT", "date": "2025-06-15", "airline": "JAL", "price_usd": 580.0},
}
var mockHotels = []map[string]any{
	{"id": "HT-002", "city": "Tokyo", "name": "APA Hotel Shinjuku", "nightly_usd": 85.0, "stars": 3},
}
var mockWeather = map[string]map[string]any{
	"Tokyo": {"temp_c": 24.0, "condition": "Partly Cloudy", "humidity": 65.0},
}

var bookingDB = map[string]map[string]any{}

// Tool implementations
func searchFlights(_ context.Context, args agentledger.JSONObject) (any, error) {
	origin := strings.ToLower(strings.TrimSpace(fmt.Sprint(args["from"])))
	dest := strings.ToLower(strings.TrimSpace(fmt.Sprint(args["to"])))
	var results []map[string]any
	for _, f := range mockFlights {
		fc := strings.ToLower(fmt.Sprint(f["from_city"]))
		fcode := strings.ToLower(fmt.Sprint(f["from_code"]))
		tc := strings.ToLower(fmt.Sprint(f["to_city"]))
		tcode := strings.ToLower(fmt.Sprint(f["to_code"]))
		if strings.Contains(fc, origin) || strings.Contains(fcode, origin) {
			if strings.Contains(tc, dest) || strings.Contains(tcode, dest) {
				results = append(results, f)
			}
		}
	}
	return map[string]any{"results": results, "count": len(results)}, nil
}

func searchHotels(_ context.Context, args agentledger.JSONObject) (any, error) {
	city := strings.ToLower(strings.TrimSpace(fmt.Sprint(args["city"])))
	var results []map[string]any
	for _, h := range mockHotels {
		if strings.ToLower(fmt.Sprint(h["city"])) == city {
			results = append(results, h)
		}
	}
	return map[string]any{"results": results, "count": len(results)}, nil
}

func checkWeather(_ context.Context, args agentledger.JSONObject) (any, error) {
	city := strings.TrimSpace(fmt.Sprint(args["city"]))
	if w, ok := mockWeather[city]; ok {
		result := map[string]any{"city": city}
		for k, v := range w {
			result[k] = v
		}
		return result, nil
	}
	return map[string]any{"city": city, "temp_c": 20.0, "condition": "Unknown"}, nil
}

func bookFlight(_ context.Context, args agentledger.JSONObject) (any, error) {
	ref := fmt.Sprintf("BK-F-%s-%s", args["flight_id"], strings.ToUpper(fmt.Sprint(args["passenger"])[:3]))
	if b, ok := bookingDB[ref]; ok {
		return b, nil
	}
	for _, f := range mockFlights {
		if f["id"] == args["flight_id"] {
			booking := map[string]any{
				"booking_ref": ref, "type": "flight", "airline": f["airline"],
				"price_usd": f["price_usd"], "status": "confirmed", "external_id": ref,
			}
			bookingDB[ref] = booking
			return booking, nil
		}
	}
	return nil, fmt.Errorf("flight not found: %s", args["flight_id"])
}

func bookHotel(_ context.Context, args agentledger.JSONObject) (any, error) {
	ref := fmt.Sprintf("BK-H-%s-%s", args["hotel_id"], strings.ToUpper(fmt.Sprint(args["guest"])[:3]))
	if b, ok := bookingDB[ref]; ok {
		return b, nil
	}
	for _, h := range mockHotels {
		if h["id"] == args["hotel_id"] {
			nights := 5
			booking := map[string]any{
				"booking_ref": ref, "type": "hotel", "name": h["name"],
				"price_total_usd": h["nightly_usd"].(float64) * float64(nights),
				"status":          "confirmed", "external_id": ref,
			}
			bookingDB[ref] = booking
			return booking, nil
		}
	}
	return nil, fmt.Errorf("hotel not found: %s", args["hotel_id"])
}

// Agent function
func travelPlanner(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
	// Phase 1: Research
	flights, _ := agentCtx.CallTool(ctx, "travel.search_flights", agentledger.JSONObject{"from": "Beijing", "to": "Tokyo"})
	hotels, _ := agentCtx.CallTool(ctx, "travel.search_hotels", agentledger.JSONObject{"city": "Tokyo"})
	weather, _ := agentCtx.CallTool(ctx, "travel.check_weather", agentledger.JSONObject{"city": "Tokyo"})

	fc := 0
	if fm, ok := flights.(map[string]any); ok {
		if c, ok := fm["count"].(int); ok {
			fc = c
		} else if c, ok := fm["count"].(float64); ok {
			fc = int(c)
		}
	}
	hc := 0
	if hm, ok := hotels.(map[string]any); ok {
		if c, ok := hm["count"].(int); ok {
			hc = c
		} else if c, ok := hm["count"].(float64); ok {
			hc = int(c)
		}
	}
	wt := 0.0
	if wm, ok := weather.(map[string]any); ok {
		if t, ok := wm["temp_c"].(float64); ok {
			wt = t
		}
	}
	_ = agentCtx.WriteState("research", map[string]any{"flights": fc, "hotels": hc, "weather": wt})

	// Phase 2: Book flight (approval required)
	flight, err := agentCtx.CallTool(ctx, "travel.book_flight", agentledger.JSONObject{
		"flight_id": "FL-002", "passenger": "Demo User",
		"_logical_operation": "book-demo-flight",
	})
	if err != nil {
		return err
	}

	// Phase 3: Simulated crash on attempt 2
	if agentCtx.Attempt == 2 {
		return agentledger.ErrRetryable
	}

	// Phase 4: Book hotel (approval required)
	hotel, err := agentCtx.CallTool(ctx, "travel.book_hotel", agentledger.JSONObject{
		"hotel_id": "HT-002", "check_in": "2025-06-15", "check_out": "2025-06-20",
		"guest": "Demo User", "_logical_operation": "book-demo-hotel",
	})
	if err != nil {
		return err
	}

	fr := ""
	if fm, ok := flight.(map[string]any); ok {
		fr = fmt.Sprint(fm["booking_ref"])
	}
	hr := ""
	if hm, ok := hotel.(map[string]any); ok {
		hr = fmt.Sprint(hm["booking_ref"])
	}
	_ = agentCtx.WriteState("bookings", map[string]any{"flight": fr, "hotel": hr})
	_ = agentCtx.WriteState("trip_status", "confirmed")
	return nil
}

// Display helpers
func wait(msg string) {
	fmt.Printf("\n%s  ⏎ %s...%s", cDim, msg, cRst)
	bufio.NewReader(os.Stdin).ReadString('\n')
}

func showRows(label string, headers []string, rows [][]string, color string) {
	if len(rows) == 0 {
		fmt.Printf("\n  %s%s:%s %s(empty)%s\n", color, label, cRst, cDim, cRst)
		return
	}
	fmt.Printf("\n  %s%s (%d rows):%s\n", color, label, len(rows), cRst)
	for _, row := range rows {
		parts := []string{}
		for i, v := range row {
			parts = append(parts, fmt.Sprintf("%s=%s%s%s", headers[i], cBold, v, cRst))
		}
		fmt.Printf("    %s%s%s\n", cDim, strings.Join(parts, " | "), cRst)
	}
}

func showDB(store *agentledger.JSONStore, runID string) {
	// Runs
	run, err := store.Run(runID)
	var runRows [][]string
	if err == nil {
		shortID := run.RunID
		if len(shortID) > 24 {
			shortID = shortID[:24] + "..."
		}
		runRows = append(runRows, []string{shortID, run.Status, fmt.Sprintf("%d", run.StateVersion)})
	}
	showRows("Runs", []string{"run_id", "status", "state_version"}, runRows, cB)

	// Steps
	var stepRows [][]string
	for _, s := range store.Steps(runID) {
		shortID := s.StepID
		if len(shortID) > 24 {
			shortID = shortID[:24] + "..."
		}
		stepRows = append(stepRows, []string{shortID, s.Status, fmt.Sprintf("%d", s.Attempt)})
	}
	showRows("Steps", []string{"step_id", "status", "attempt"}, stepRows, cB)

	// Tool Ledger
	var ledgerRows [][]string
	for _, tl := range store.Ledger(runID) {
		key := tl.IdempotencyKey
		shortKey := key
		if idx := strings.LastIndex(key, ":"); idx >= 0 {
			prevIdx := strings.LastIndex(key[:idx], ":")
			if prevIdx >= 0 {
				shortKey = key[prevIdx+1:idx] + ":" + key[idx+1:]
			}
		}
		if len(shortKey) > 30 {
			shortKey = shortKey[:30]
		}
		ledgerRows = append(ledgerRows, []string{tl.ToolName, tl.Status, shortKey})
	}
	showRows("Tool Ledger", []string{"tool", "status", "idemp_key"}, ledgerRows, cY)

	// Approval requests
	var approvalRows [][]string
	for _, a := range store.ApprovalRequests(runID) {
		approvedBy := a.ApprovedBy
		if approvedBy == "" {
			approvedBy = "-"
		}
		approvalRows = append(approvalRows, []string{a.ToolName, a.Status, approvedBy})
	}
	showRows("Approval Requests", []string{"tool", "status", "approved_by"}, approvalRows, cR)

	fmt.Println()
}

func main() {
	root, err := os.MkdirTemp("", "agentledger-go-")
	if err != nil {
		panic(err)
	}
	if len(os.Args) > 1 {
		root = os.Args[1]
	}

	// Intro
	fmt.Printf("\n%s%s  ╔════════════════════════════════════════════════════╗%s\n", cBold, cC, cRst)
	fmt.Printf("%s%s  ║   AgentLedger Travel Assistant (Go) — Interactive Demo  ║%s\n", cBold, cC, cRst)
	fmt.Printf("%s%s  ║   See real database state at every step                 ║%s\n", cBold, cC, cRst)
	fmt.Printf("%s%s  ╚════════════════════════════════════════════════════╝%s\n", cBold, cC, cRst)

	fmt.Printf("\n  %sAgentLedger — Durable Execution Runtime for AI Agents%s\n", cDim, cRst)
	fmt.Printf("  ┌────────────────────────────────────────────────────┐\n")
	fmt.Printf("  │  %s✓%s Durable execution — crash recovery              │\n", cG, cRst)
	fmt.Printf("  │  %s✓%s Tool Ledger — idempotent replay                │\n", cG, cRst)
	fmt.Printf("  │  %s✓%s Approval gates — human-in-the-loop              │\n", cG, cRst)
	fmt.Printf("  │  %s✓%s Policy engine — role-based access               │\n", cG, cRst)
	fmt.Printf("  │  %s✓%s Budget control — tool call limits               │\n", cG, cRst)
	fmt.Printf("  │  %s✓%s Evidence export — full audit trail              │\n", cG, cRst)
	fmt.Printf("  └────────────────────────────────────────────────────┘\n")

	wait("Press Enter to start / 按 Enter 开始")

	// Step 1: Setup
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cB, cRst)
	fmt.Printf("%s%s  Step 1: Initialize — Register tools, configure policy%s\n", cBold, cB, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cB, cRst)

	rt, err := agentledger.NewLocalRuntime(root + "/state.json")
	if err != nil {
		panic(err)
	}

	for _, t := range []string{"travel.search_flights", "travel.search_hotels", "travel.check_weather",
		"travel.book_flight", "travel.book_hotel"} {
		rt.Policy.AllowTool("TravelPlanner", t)
	}
	rt.SetBudget(agentledger.BudgetLimits{MaxToolCalls: 25})

	rt.RegisterTool(agentledger.ToolSpec{
		Name: "travel.search_flights", Version: "v1", SideEffect: "none", RiskLevel: "low",
		InputSchema:  map[string]any{"type": "object", "required": []any{"from", "to"}},
		OutputSchema: map[string]any{"type": "object"},
		Func:         searchFlights,
	})
	rt.RegisterTool(agentledger.ToolSpec{
		Name: "travel.search_hotels", Version: "v1", SideEffect: "none", RiskLevel: "low",
		InputSchema:  map[string]any{"type": "object", "required": []any{"city"}},
		OutputSchema: map[string]any{"type": "object"},
		Func:         searchHotels,
	})
	rt.RegisterTool(agentledger.ToolSpec{
		Name: "travel.check_weather", Version: "v1", SideEffect: "none", RiskLevel: "low",
		InputSchema:  map[string]any{"type": "object", "required": []any{"city"}},
		OutputSchema: map[string]any{"type": "object"},
		Func:         checkWeather,
	})
	rt.RegisterTool(agentledger.ToolSpec{
		Name: "travel.book_flight", Version: "v1", SideEffect: "external_write", RiskLevel: "high",
		IdempotencyRequired: true, ApprovalRequired: true,
		InputSchema:  map[string]any{"type": "object", "required": []any{"flight_id", "passenger"}},
		OutputSchema: map[string]any{"type": "object"},
		Func:         bookFlight,
	})
	rt.RegisterTool(agentledger.ToolSpec{
		Name: "travel.book_hotel", Version: "v1", SideEffect: "external_write", RiskLevel: "high",
		IdempotencyRequired: true, ApprovalRequired: true,
		InputSchema:  map[string]any{"type": "object", "required": []any{"hotel_id", "guest"}},
		OutputSchema: map[string]any{"type": "object"},
		Func:         bookHotel,
	})

	runID, _, err := rt.CreateRun(map[string]any{"trip": "Tokyo", "budget_usd": 3000})
	if err != nil {
		panic(err)
	}
	fmt.Printf("\n  %sRun created: %s%s%s\n", cB, cBold, runID, cRst)
	showDB(rt.Store, runID)
	wait("Press Enter to continue")

	// Step 2: Attempt 1 — Approval interception
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cR, cRst)
	fmt.Printf("%s%s  Step 2: Attempt 1 — Agent runs → Approval triggered%s\n", cBold, cR, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cR, cRst)
	fmt.Printf("\n  %sAgent executing: search flights → search hotels → check weather → book flight...%s\n", cDim, cRst)

	ctx := context.Background()
	rt.RunOnce(ctx, runID, "worker-go", "TravelPlanner", 60, travelPlanner)

	fmt.Printf("\n  %sbook_flight triggered approval! Runtime paused, waiting for human.%s\n", cR, cRst)
	showDB(rt.Store, runID)
	fmt.Printf("  %sNote: Tool Ledger has RESERVED entry, approval status is PENDING%s\n", cR, cRst)
	wait("Press Enter to approve / 按 Enter 审批")

	for _, req := range rt.Store.ApprovalRequests(runID) {
		if req.Status == "PENDING" {
			rt.Store.ApproveRequest(req.ApprovalID, "traveler", "Within budget, approved")
			fmt.Printf("\n  %s✅ Approved: %s — by traveler%s\n", cG, req.ToolName, cRst)
		}
	}
	showDB(rt.Store, runID)
	wait("Press Enter to continue")

	// Step 3: Attempt 2 — Execute + Crash
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cY, cRst)
	fmt.Printf("%s%s  Step 3: Attempt 2 — Approved → Execute booking → Simulated crash%s\n", cBold, cY, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cY, cRst)
	fmt.Printf("\n  %sRe-running agent (approval passed, book_flight will execute)...%s\n", cDim, cRst)

	rt.RunOnce(ctx, runID, "worker-go", "TravelPlanner", 60, travelPlanner)

	fmt.Printf("\n  %sAgent booked flight, then crashed before committing state!%s\n", cY, cRst)
	fmt.Printf("  %sFlight is booked in external system, but agent state was NOT persisted.%s\n", cY, cRst)
	showDB(rt.Store, runID)
	fmt.Printf("  %sKey: Tool Ledger book_flight status = %sSUCCEEDED%s (external side effect executed)%s\n", cY, cG, cY, cRst)
	fmt.Printf("  %s      Step status = retry_scheduled (state not committed, waiting for retry)%s\n", cY, cRst)
	wait("Press Enter to continue")

	// Step 4: Attempt 3 — Recovery + Hotel approval
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cG, cRst)
	fmt.Printf("%s%s  Step 4: Attempt 3 — Crash recovery → Tool Ledger idempotent replay%s\n", cBold, cG, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cG, cRst)
	fmt.Printf("\n  %sAgent re-executes. book_flight: Tool Ledger sees SUCCEEDED record...%s\n", cDim, cRst)
	fmt.Printf("  %s%s→ Returns cached result, no duplicate API call, no double charge!%s\n", cDim, cG, cRst)

	rt.RunOnce(ctx, runID, "worker-go", "TravelPlanner", 60, travelPlanner)

	fmt.Printf("\n  %s✅ Flight idempotent replay successful! (no duplicate _book_flight call)%s\n", cG, cRst)
	fmt.Printf("  %sHotel booking → triggers approval again%s\n", cR, cRst)

	for _, req := range rt.Store.ApprovalRequests(runID) {
		if req.Status == "PENDING" {
			rt.Store.ApproveRequest(req.ApprovalID, "traveler", "Hotel within budget, approved")
			fmt.Printf("\n  %s✅ Approved: %s — by traveler%s\n", cG, req.ToolName, cRst)
		}
	}
	showDB(rt.Store, runID)
	wait("Press Enter to continue")

	// Step 5: Attempt 4 — Complete
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cG, cRst)
	fmt.Printf("%s%s  Step 5: Attempt 4 — Hotel approved → Full execution → State committed%s\n", cBold, cG, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cG, cRst)

	ok, err := rt.RunOnce(ctx, runID, "worker-go", "TravelPlanner", 60, travelPlanner)
	if err != nil || !ok {
		fmt.Printf("Recovery failed: %v\n", err)
		os.Exit(1)
	}
	if len(bookingDB) != 2 {
		fmt.Printf("Expected 2 bookings, got %d\n", len(bookingDB))
		os.Exit(1)
	}

	fmt.Printf("\n  %s✅ Travel planning complete! State persisted to database.%s\n", cG, cRst)
	showDB(rt.Store, runID)
	fmt.Printf("  %sStep status = completed, State has bookings + trip_status%s\n", cG, cRst)
	keys := []string{}
	for k := range bookingDB {
		keys = append(keys, k)
	}
	fmt.Printf("  %sExternal bookings: %v (2 total, no duplicates)%s\n", cG, keys, cRst)
	wait("Press Enter to continue")

	// Step 6: Evidence + Cost + Replay
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cM, cRst)
	fmt.Printf("%s%s  Step 6: Evidence export + Cost attribution + Replay verification%s\n", cBold, cM, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cM, cRst)

	bundle, _ := agentledger.ExportEvidence(rt.Store, runID)
	replay, _ := agentledger.Replay(rt.Store, runID)
	cost := agentledger.CostAttribution(rt.Store, runID)

	tc := cost.Total.ToolCalls

	fmt.Printf("\n  %sCost attribution: %.0f tool calls%s\n", cM, tc, cRst)
	fmt.Printf("  %sReplay: %d events, safe=%s%v%s\n", cM, replay.EventCount, cG, replay.ReplaySafe, cRst)
	fmt.Printf("  %sEvidence bundle: %d events total%s\n", cM, len(bundle.Events), cRst)

	// Final summary
	fmt.Printf("\n%s%s════════════════════════════════════════════════════════════%s\n", cBold, cG, cRst)
	fmt.Printf("%s%s  Summary: What AgentLedger (Go) did in this demo%s\n", cBold, cG, cRst)
	fmt.Printf("%s%s════════════════════════════════════════════════════════════%s\n", cBold, cG, cRst)
	fmt.Printf(`
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │  %s✓ Durable execution%s  Crash → auto retry, state preserved         │
  │                   Step: retry_scheduled → completed           │
  │                                                          │
  │  %s✓ Tool Ledger%s      Idempotent replay, flight booked %s1x%s only       │
  │                   SUCCEEDED → cached result on retry        │
  │                                                          │
  │  %s✓ Approval gates%s    Flight + hotel each trigger approval          │
  │                   approval_requests records in store        │
  │                                                          │
  │  %s✓ Policy engine%s     Each tool call checked by policy             │
  │                   TravelPlanner role allowed              │
  │                                                          │
  │  %s✓ Budget control%s    Tracked %.0f tool calls                       │
  │                   BudgetController.beforeToolCall()       │
  │                                                          │
  │  %s✓ Evidence export%s   %d events recorded                         │
  │                   events stored in JSON store              │
  │                                                          │
  │  %s✓ Cost attribution%s  Auto-recorded per run                        │
  │                   CostAttribution by agent                │
  │                                                          │
  │  %s✓ Replay engine%s     Event hash verification passed                │
  │                   Verify history without re-running       │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
`, cG, cRst, cG, cRst, cBold, cRst, cG, cRst, cG, cRst, cG, cRst, tc, cG, cRst, len(bundle.Events), cG, cRst, cG, cRst)

	fmt.Printf("  %sStorage file: %s/state.json%s\n", cDim, root, cRst)
	fmt.Printf("  %sRun: agentledger-go %s%s\n", cDim, root, cRst)
	fmt.Println()
}

func ptr(f float64) *float64 { return &f }
