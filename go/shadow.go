package agentledger

import "reflect"

type ShadowReport struct {
	SourceRunID string     `json:"source_run_id"`
	ShadowRunID string     `json:"shadow_run_id"`
	OK          bool       `json:"ok"`
	StateDiff   JSONObject `json:"state_diff"`
}

func DiffStates(source, shadow JSONObject) JSONObject {
	changed := JSONObject{}
	keys := map[string]bool{}
	for key := range source {
		keys[key] = true
	}
	for key := range shadow {
		keys[key] = true
	}
	for key := range keys {
		if !reflect.DeepEqual(source[key], shadow[key]) {
			changed[key] = JSONObject{"source": source[key], "shadow": shadow[key]}
		}
	}
	return JSONObject{"changed": changed, "changed_count": len(changed)}
}

func NewShadowReport(sourceRunID, shadowRunID string, ok bool, source, shadow JSONObject) ShadowReport {
	return ShadowReport{SourceRunID: sourceRunID, ShadowRunID: shadowRunID, OK: ok, StateDiff: DiffStates(source, shadow)}
}
