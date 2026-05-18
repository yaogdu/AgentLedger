package agentledger

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"html"
	"strconv"
)

type TraceSpan struct {
	TraceID      string     `json:"trace_id"`
	SpanID       string     `json:"span_id"`
	ParentSpanID string     `json:"parent_span_id,omitempty"`
	Name         string     `json:"name"`
	StartTime    float64    `json:"start_time"`
	EndTime      float64    `json:"end_time"`
	Attributes   JSONObject `json:"attributes"`
}

func TraceSpans(bundle EvidenceBundle) []TraceSpan {
	runID := bundle.Run.RunID
	spans := []TraceSpan{}
	for i, event := range bundle.Events {
		seq := event.Seq
		if seq == 0 {
			seq = i + 1
		}
		spans = append(spans, TraceSpan{TraceID: runID, SpanID: formatSpanID("evt", seq), Name: event.Type, StartTime: event.Timestamp, EndTime: event.Timestamp, Attributes: compactJSON(JSONObject{
			"agentledger.run_id":        runID,
			"agentledger.session_id":    event.SessionID,
			"agentledger.step_id":       event.StepID,
			"agentledger.seq":           seq,
			"agentledger.state_version": event.StateVersion,
			"agentledger.payload_hash":  event.PayloadHash,
			"agentledger.payload_ref":   event.PayloadRef,
		})})
	}
	for i, artifact := range bundle.MediaArtifacts {
		spans = append(spans, TraceSpan{TraceID: runID, SpanID: formatSpanID("media", i+1), Name: "media_artifact", StartTime: bundle.Run.UpdatedAt, EndTime: bundle.Run.UpdatedAt, Attributes: compactJSON(JSONObject{
			"agentledger.run_id":            runID,
			"agentledger.artifact_id":       artifact["artifact_id"],
			"agentledger.artifact_name":     artifact["name"],
			"agentledger.media_kind":        artifact["kind"],
			"agentledger.media_uri":         artifact["uri"],
			"agentledger.media_content_ref": artifact["content_ref"],
			"agentledger.blob_hash":         artifact["blob_hash"],
			"agentledger.blob_ref":          artifact["blob_ref"],
		})})
	}
	for i, checkpoint := range bundle.StreamCheckpoints {
		spans = append(spans, TraceSpan{TraceID: runID, SpanID: formatSpanID("stream", i+1), Name: "stream_checkpoint", StartTime: bundle.Run.UpdatedAt, EndTime: bundle.Run.UpdatedAt, Attributes: compactJSON(JSONObject{
			"agentledger.run_id":           runID,
			"agentledger.artifact_id":      checkpoint["artifact_id"],
			"agentledger.artifact_name":    checkpoint["name"],
			"agentledger.stream_id":        checkpoint["stream_id"],
			"agentledger.consumer_id":      checkpoint["consumer_id"],
			"agentledger.stream_offset":    checkpoint["offset"],
			"agentledger.stream_watermark": checkpoint["watermark"],
			"agentledger.blob_hash":        checkpoint["blob_hash"],
			"agentledger.blob_ref":         checkpoint["blob_ref"],
		})})
	}
	return spans
}

type OTLPResource struct {
	ServiceName    string     `json:"service_name"`
	ServiceVersion string     `json:"service_version,omitempty"`
	Attributes     JSONObject `json:"attributes,omitempty"`
}

func OTLPTraceJSON(bundle EvidenceBundle, resource OTLPResource) JSONObject {
	if resource.ServiceName == "" {
		resource.ServiceName = "agentledger"
	}
	if resource.Attributes == nil {
		resource.Attributes = JSONObject{}
	}
	resourceAttrs := JSONObject{"service.name": resource.ServiceName}
	if resource.ServiceVersion != "" {
		resourceAttrs["service.version"] = resource.ServiceVersion
	}
	for key, value := range resource.Attributes {
		resourceAttrs[key] = value
	}
	spans := []JSONObject{}
	for _, span := range TraceSpans(bundle) {
		attrs := cloneJSONObject(span.Attributes)
		attrs["agentledger.original_trace_id"] = span.TraceID
		attrs["agentledger.original_span_id"] = span.SpanID
		item := JSONObject{
			"traceId":           hexID(span.TraceID, 32),
			"spanId":            hexID(span.SpanID, 16),
			"name":              span.Name,
			"kind":              "SPAN_KIND_INTERNAL",
			"startTimeUnixNano": fmtInt(int(span.StartTime * 1000000000)),
			"endTimeUnixNano":   fmtInt(int(span.EndTime * 1000000000)),
			"attributes":        otlpAttributes(attrs),
		}
		if span.ParentSpanID != "" {
			item["parentSpanId"] = hexID(span.ParentSpanID, 16)
		}
		spans = append(spans, item)
	}
	return JSONObject{"resourceSpans": []any{JSONObject{"resource": JSONObject{"attributes": otlpAttributes(resourceAttrs)}, "scopeSpans": []any{JSONObject{"scope": JSONObject{"name": "agentledger", "version": resource.ServiceVersion}, "spans": spans}}}}}
}

func otlpAttributes(attrs JSONObject) []JSONObject {
	out := []JSONObject{}
	for key, value := range attrs {
		if value == nil {
			continue
		}
		out = append(out, JSONObject{"key": key, "value": otlpValue(value)})
	}
	return out
}

func otlpValue(value any) JSONObject {
	switch item := value.(type) {
	case bool:
		return JSONObject{"boolValue": item}
	case int:
		return JSONObject{"intValue": fmtInt(item)}
	case int64:
		return JSONObject{"intValue": fmtInt(int(item))}
	case float64:
		return JSONObject{"doubleValue": item}
	case string:
		return JSONObject{"stringValue": item}
	default:
		return JSONObject{"stringValue": mustJSON(item)}
	}
}

func hexID(value string, chars int) string {
	sum := sha256.Sum256([]byte(value))
	encoded := hex.EncodeToString(sum[:])
	if len(encoded) > chars {
		return encoded[:chars]
	}
	for len(encoded) < chars {
		encoded += "0"
	}
	return encoded
}

func TraceJSONL(bundle EvidenceBundle) (string, error) {
	out := ""
	for _, span := range TraceSpans(bundle) {
		data, err := json.Marshal(span)
		if err != nil {
			return "", err
		}
		out += string(data) + "\n"
	}
	return out, nil
}

type SequenceDiff struct {
	LeftCount    int          `json:"left_count"`
	RightCount   int          `json:"right_count"`
	ChangedCount int          `json:"changed_count"`
	Changed      []JSONObject `json:"changed"`
}

type DictDiff struct {
	ChangedCount int                   `json:"changed_count"`
	Changed      map[string]JSONObject `json:"changed"`
}

type EvidenceDiffReport struct {
	LeftRunID  string     `json:"left_run_id"`
	RightRunID string     `json:"right_run_id"`
	Same       bool       `json:"same"`
	Changes    JSONObject `json:"changes"`
}

type DivergenceReport struct {
	LeftRunID         string     `json:"left_run_id"`
	RightRunID        string     `json:"right_run_id"`
	Same              bool       `json:"same"`
	ChangedDimensions []string   `json:"changed_dimensions"`
	Dimensions        JSONObject `json:"dimensions"`
}

func DiffEvidence(left, right EvidenceBundle) EvidenceDiffReport {
	changes := JSONObject{
		"bundle_hash_changed": left.BundleHash != right.BundleHash,
		"summary":             DiffDict(left.Summary, right.Summary),
		"final_state":         DiffDict(left.FinalState, right.FinalState),
		"event_types":         DiffSequence(eventTypes(left.Events), eventTypes(right.Events)),
		"tool_ledger":         DiffSequence(ledgerStatuses(left.ToolLedger), ledgerStatuses(right.ToolLedger)),
		"media_artifacts":     DiffSequence(fingerprints(left.MediaArtifacts, []string{"name", "kind", "uri", "content_ref", "blob_hash", "lineage"}), fingerprints(right.MediaArtifacts, []string{"name", "kind", "uri", "content_ref", "blob_hash", "lineage"})),
		"stream_checkpoints":  DiffSequence(fingerprints(left.StreamCheckpoints, []string{"name", "stream_id", "consumer_id", "offset", "watermark", "chunk", "partial_result_ref"}), fingerprints(right.StreamCheckpoints, []string{"name", "stream_id", "consumer_id", "offset", "watermark", "chunk", "partial_result_ref"})),
	}
	return EvidenceDiffReport{LeftRunID: left.Run.RunID, RightRunID: right.Run.RunID, Same: !hasChanges(changes), Changes: changes}
}

func DivergenceEvidence(left, right EvidenceBundle) DivergenceReport {
	dims := JSONObject{
		"events":             DiffSequence(eventTypes(left.Events), eventTypes(right.Events)),
		"state":              DiffDict(left.FinalState, right.FinalState),
		"artifacts":          DiffSequence(artifactFingerprints(left.Artifacts), artifactFingerprints(right.Artifacts)),
		"media_artifacts":    DiffSequence(fingerprints(left.MediaArtifacts, []string{"name", "kind", "uri", "content_ref", "blob_hash", "lineage"}), fingerprints(right.MediaArtifacts, []string{"name", "kind", "uri", "content_ref", "blob_hash", "lineage"})),
		"stream_checkpoints": DiffSequence(fingerprints(left.StreamCheckpoints, []string{"name", "stream_id", "consumer_id", "offset", "watermark", "chunk", "partial_result_ref"}), fingerprints(right.StreamCheckpoints, []string{"name", "stream_id", "consumer_id", "offset", "watermark", "chunk", "partial_result_ref"})),
		"ledger":             DiffSequence(ledgerFingerprints(left.ToolLedger), ledgerFingerprints(right.ToolLedger)),
	}
	changed := []string{}
	for _, name := range []string{"events", "state", "artifacts", "media_artifacts", "stream_checkpoints", "ledger"} {
		if dimensionChanged(dims[name]) {
			changed = append(changed, name)
		}
	}
	return DivergenceReport{LeftRunID: left.Run.RunID, RightRunID: right.Run.RunID, Same: len(changed) == 0, ChangedDimensions: changed, Dimensions: dims}
}

func DebugHTML(bundle EvidenceBundle) string {
	rows := ""
	for _, event := range bundle.Events {
		rows += "<tr><td>" + fmtInt(event.Seq) + "</td><td><code>" + html.EscapeString(event.Type) + "</code></td><td>" + html.EscapeString(event.StepID) + "</td><td>" + html.EscapeString(event.AgentRole) + "</td></tr>\n"
	}
	state := html.EscapeString(mustJSON(bundle.FinalState))
	return "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>AgentLedger Debug Report</title><style>body{font-family:Georgia,serif;background:#f7f1e8;color:#1f1a15;margin:0}main{max-width:1080px;margin:auto;padding:32px 20px}table{width:100%;border-collapse:collapse;background:#fffaf2}td,th{border-bottom:1px solid #ddcdbb;padding:8px;text-align:left}code,pre{font-family:ui-monospace,Menlo,monospace;background:#efe2d1;border-radius:6px;padding:2px 5px}pre{display:block;padding:12px;overflow:auto}</style></head><body><main><h1>AgentLedger Debug Report</h1><section><h2>Run</h2><p><code>" + html.EscapeString(bundle.Run.RunID) + "</code></p></section><section><h2>Events</h2><table><thead><tr><th>Seq</th><th>Event</th><th>Step</th><th>Role</th></tr></thead><tbody>" + rows + "</tbody></table></section><section><h2>Final State</h2><pre>" + state + "</pre></section></main></body></html>\n"
}

func DebugSummary(bundle EvidenceBundle) JSONObject {
	changed := 0
	for _, event := range bundle.Events {
		if event.Type == "state_committed" || event.Type == "system_state_patch_applied" || event.Type == "run_created" {
			changed++
		}
	}
	return JSONObject{"run_id": bundle.Run.RunID, "event_count": len(bundle.Events), "state_change_count": changed, "final_state": bundle.FinalState}
}

func DiffDict(left, right JSONObject) DictDiff {
	changed := map[string]JSONObject{}
	keys := map[string]bool{}
	for key := range left {
		keys[key] = true
	}
	for key := range right {
		keys[key] = true
	}
	for key := range keys {
		if mustJSON(left[key]) != mustJSON(right[key]) {
			changed[key] = JSONObject{"left": left[key], "right": right[key]}
		}
	}
	return DictDiff{ChangedCount: len(changed), Changed: changed}
}

func DiffSequence(left, right []any) SequenceDiff {
	max := len(left)
	if len(right) > max {
		max = len(right)
	}
	changed := []JSONObject{}
	for i := 0; i < max; i++ {
		var l any
		var r any
		if i < len(left) {
			l = left[i]
		}
		if i < len(right) {
			r = right[i]
		}
		if mustJSON(l) != mustJSON(r) {
			changed = append(changed, JSONObject{"index": i, "left": l, "right": r})
		}
	}
	return SequenceDiff{LeftCount: len(left), RightCount: len(right), ChangedCount: len(changed), Changed: changed}
}

func formatSpanID(prefix string, seq int) string { return prefix + "-" + leftPad6(seq) }
func leftPad6(value int) string {
	s := fmtInt(value)
	for len(s) < 6 {
		s = "0" + s
	}
	return s
}
func fmtInt(value int) string { return strconv.Itoa(value) }

func eventTypes(events []Event) []any {
	out := make([]any, 0, len(events))
	for _, event := range events {
		out = append(out, event.Type)
	}
	return out
}

func ledgerStatuses(entries []ToolLedgerEntry) []any {
	out := make([]any, 0, len(entries))
	for _, entry := range entries {
		out = append(out, entry.Status)
	}
	return out
}

func fingerprints(rows []JSONObject, keys []string) []any {
	out := make([]any, 0, len(rows))
	for _, row := range rows {
		fingerprint := JSONObject{}
		for _, key := range keys {
			fingerprint[key] = row[key]
		}
		out = append(out, fingerprint)
	}
	return out
}

func artifactFingerprints(rows []Artifact) []any {
	out := make([]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, JSONObject{"name": row.Name, "blob_hash": row.BlobHash, "metadata": row.Metadata})
	}
	return out
}

func ledgerFingerprints(rows []ToolLedgerEntry) []any {
	out := make([]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, JSONObject{"tool_name": row.ToolName, "status": row.Status, "external_id": row.ExternalID, "error_type": row.ErrorType, "request_hash": row.RequestHash, "response_hash": row.ResponseHash})
	}
	return out
}

func dimensionChanged(value any) bool {
	switch item := value.(type) {
	case SequenceDiff:
		return item.ChangedCount > 0
	case DictDiff:
		return item.ChangedCount > 0
	default:
		return false
	}
}

func hasChanges(changes JSONObject) bool {
	if changed, ok := changes["bundle_hash_changed"].(bool); ok && changed {
		return true
	}
	for key, value := range changes {
		if key == "bundle_hash_changed" {
			continue
		}
		if dimensionChanged(value) {
			return true
		}
	}
	return false
}
