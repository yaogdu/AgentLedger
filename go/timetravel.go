package agentledger

import "html"

type TimeTravelFrame struct {
	Seq          int        `json:"seq"`
	EventID      string     `json:"event_id"`
	Type         string     `json:"type"`
	StepID       string     `json:"step_id,omitempty"`
	AgentRole    string     `json:"agent_role,omitempty"`
	StateVersion int        `json:"state_version,omitempty"`
	Timestamp    float64    `json:"timestamp"`
	StateChanged bool       `json:"state_changed"`
	ChangedKeys  []string   `json:"changed_keys"`
	Patch        JSONObject `json:"patch,omitempty"`
	StateAfter   JSONObject `json:"state_after,omitempty"`
}
type TimeTravelReport struct {
	RunID         string            `json:"run_id"`
	AtSeq         int               `json:"at_seq,omitempty"`
	EventCount    int               `json:"event_count"`
	Timeline      []TimeTravelFrame `json:"timeline"`
	StateAtSeq    JSONObject        `json:"state_at_seq"`
	SelectedEvent *TimeTravelFrame  `json:"selected_event,omitempty"`
}

func TimeTravel(bundle EvidenceBundle, atSeq int, includeStates bool) TimeTravelReport {
	state := JSONObject{}
	stateAt := JSONObject{}
	frames := []TimeTravelFrame{}
	var selected *TimeTravelFrame
	for _, event := range bundle.Events {
		before := cloneJSONObject(state)
		patch := patchForTimeTravelEvent(event)
		if patch != nil {
			for k, v := range patch {
				state[k] = v
			}
		}
		diff := DiffDict(before, state)
		keys := []string{}
		for k := range diff.Changed {
			keys = append(keys, k)
		}
		frame := TimeTravelFrame{Seq: event.Seq, EventID: event.EventID, Type: event.Type, StepID: event.StepID, AgentRole: event.AgentRole, StateVersion: event.StateVersion, Timestamp: event.Timestamp, StateChanged: diff.ChangedCount > 0, ChangedKeys: keys, Patch: patch}
		if includeStates {
			frame.StateAfter = cloneJSONObject(state)
		}
		frames = append(frames, frame)
		if atSeq > 0 && event.Seq <= atSeq {
			copyFrame := frame
			selected = &copyFrame
			stateAt = cloneJSONObject(state)
		}
	}
	if atSeq == 0 {
		stateAt = cloneJSONObject(state)
	}
	return TimeTravelReport{RunID: bundle.Run.RunID, AtSeq: atSeq, EventCount: len(frames), Timeline: frames, StateAtSeq: stateAt, SelectedEvent: selected}
}
func patchForTimeTravelEvent(event Event) JSONObject {
	if event.Type == "run_created" {
		if p, ok := event.Payload["initial_state"].(map[string]any); ok {
			return JSONObject(p)
		}
		if p, ok := event.Payload["initial_state"].(JSONObject); ok {
			return p
		}
		return JSONObject{}
	}
	if event.Type == "state_committed" || event.Type == "state_patch_committed" || event.Type == "system_state_patch_applied" {
		if p, ok := event.Payload["patch"].(map[string]any); ok {
			return JSONObject(p)
		}
		if p, ok := event.Payload["patch"].(JSONObject); ok {
			return p
		}
	}
	return nil
}
func (r TimeTravelReport) HTML() string {
	rows := ""
	for _, frame := range r.Timeline {
		rows += "<tr><td>" + fmtInt(frame.Seq) + "</td><td>" + html.EscapeString(frame.Type) + "</td><td>" + html.EscapeString(mustJSON(frame.ChangedKeys)) + "</td></tr>"
	}
	return "<!doctype html><html><head><meta charset=\"utf-8\"><title>AgentLedger Time Travel Report</title></head><body><h1>AgentLedger Time Travel Report</h1><p>Run <code>" + html.EscapeString(r.RunID) + "</code></p><table>" + rows + "</table><h2>State At Selected Point</h2><pre>" + html.EscapeString(mustJSON(r.StateAtSeq)) + "</pre><h2>Selected Event</h2><pre>" + html.EscapeString(mustJSON(r.SelectedEvent)) + "</pre></body></html>"
}
