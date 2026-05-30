// Package langfuse exposes the AgentLedger Langfuse evidence export boundary for Go.
package langfuse

import "fmt"

import runtime "github.com/yaogdu/AgentLedger/go"

type Payload map[string]any

func PayloadFromEvidence(bundle any) Payload {
	if typed, ok := bundle.(runtime.EvidenceBundle); ok {
		return payloadFromTypedEvidence(typed)
	}
	object, _ := bundle.(runtime.JSONObject)
	if object == nil {
		if value, ok := bundle.(map[string]any); ok {
			object = runtime.JSONObject(value)
		}
	}
	return payloadFromJSONObject(object)
}

func payloadFromTypedEvidence(bundle runtime.EvidenceBundle) Payload {
	runID := bundle.Run.RunID
	if runID == "" {
		runID = "run_unknown"
	}
	batch := make([]any, 0, len(bundle.Events))
	for index, event := range bundle.Events {
		seq := event.Seq
		if seq == 0 {
			seq = index + 1
		}
		batch = append(batch, map[string]any{
			"type":                "trace-span",
			"traceId":             runID,
			"id":                  fmt.Sprintf("evt-%06d", seq),
			"parentObservationId": nil,
			"name":                event.Type,
			"startTime":           event.Timestamp,
			"endTime":             event.Timestamp,
			"metadata": map[string]any{
				"agentledger.run_id":        runID,
				"agentledger.session_id":    event.SessionID,
				"agentledger.step_id":       event.StepID,
				"agentledger.seq":           seq,
				"agentledger.state_version": event.StateVersion,
				"agentledger.payload_hash":  event.PayloadHash,
				"agentledger.payload_ref":   event.PayloadRef,
				"agentledger.exporter":      "langfuse",
			},
		})
	}
	return Payload{"batch": batch, "metadata": map[string]any{"source": "agentledger"}}
}

func payloadFromJSONObject(bundle runtime.JSONObject) Payload {
	runID, _ := bundle["run_id"].(string)
	if run, ok := bundle["run"].(map[string]any); ok {
		if value, ok := run["run_id"].(string); ok {
			runID = value
		}
	}
	if runID == "" {
		runID = "run_unknown"
	}
	events, _ := bundle["events"].([]any)
	batch := make([]any, 0, len(events))
	for index, raw := range events {
		event, _ := raw.(map[string]any)
		seq := index + 1
		if value, ok := event["seq"].(int); ok {
			seq = value
		}
		batch = append(batch, map[string]any{
			"type":                "trace-span",
			"traceId":             runID,
			"id":                  fmt.Sprintf("evt-%06d", seq),
			"parentObservationId": nil,
			"name":                event["type"],
			"startTime":           event["timestamp"],
			"endTime":             event["timestamp"],
			"metadata": map[string]any{
				"agentledger.run_id":        runID,
				"agentledger.session_id":    event["session_id"],
				"agentledger.step_id":       event["step_id"],
				"agentledger.seq":           seq,
				"agentledger.state_version": event["state_version"],
				"agentledger.payload_hash":  event["payload_hash"],
				"agentledger.payload_ref":   event["payload_ref"],
				"agentledger.exporter":      "langfuse",
			},
		})
	}
	return Payload{"batch": batch, "metadata": map[string]any{"source": "agentledger"}}
}
