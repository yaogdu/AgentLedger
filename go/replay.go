package agentledger

import "strings"

type ReplaySummary struct {
	RunID                 string     `json:"run_id"`
	EventCount            int        `json:"event_count"`
	ToolCallCount         int        `json:"tool_call_count"`
	FinalState            JSONObject `json:"final_state"`
	EventHash             string     `json:"event_hash"`
	ReplaySafe            bool       `json:"replay_safe"`
	ArtifactCount         int        `json:"artifact_count"`
	MediaArtifactCount    int        `json:"media_artifact_count"`
	StreamCheckpointCount int        `json:"stream_checkpoint_count"`
}

func Replay(store *JSONStore, runID string) (ReplaySummary, error) {
	events := store.Events(runID)
	digestInput := make([]JSONObject, 0, len(events))
	toolCalls := 0
	for _, event := range events {
		if strings.HasPrefix(event.Type, "tool_call_") {
			toolCalls++
		}
		digestInput = append(digestInput, JSONObject{"seq": event.Seq, "type": event.Type, "payload_hash": event.PayloadHash, "payload_ref": event.PayloadRef})
	}
	eventHash, err := sha256JSON(digestInput)
	if err != nil {
		return ReplaySummary{}, err
	}
	finalState, err := store.FinalState(runID)
	if err != nil {
		return ReplaySummary{}, err
	}
	artifacts := store.Artifacts(runID)
	return ReplaySummary{
		RunID: runID, EventCount: len(events), ToolCallCount: toolCalls,
		FinalState: finalState, EventHash: eventHash, ReplaySafe: true,
		ArtifactCount:         len(artifacts),
		MediaArtifactCount:    len(mediaArtifactsFrom(artifacts)),
		StreamCheckpointCount: len(streamCheckpointsFrom(artifacts)),
	}, nil
}
