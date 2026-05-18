package agentledger

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"time"
)

type JSONObject map[string]any

type Run struct {
	RunID        string     `json:"run_id"`
	SessionID    string     `json:"session_id"`
	Status       string     `json:"status"`
	State        JSONObject `json:"state"`
	StateVersion int        `json:"state_version"`
	CreatedAt    float64    `json:"created_at"`
	UpdatedAt    float64    `json:"updated_at"`
}

type Step struct {
	StepID        string  `json:"step_id"`
	RunID         string  `json:"run_id"`
	SessionID     string  `json:"session_id"`
	Status        string  `json:"status"`
	Owner         string  `json:"owner,omitempty"`
	LeaseToken    string  `json:"lease_token,omitempty"`
	LeaseUntil    float64 `json:"lease_until,omitempty"`
	Attempt       int     `json:"attempt"`
	StateVersion  int     `json:"state_version"`
	CheckpointID  string  `json:"checkpoint_id,omitempty"`
	LastErrorType string  `json:"last_error_type,omitempty"`
	LastError     string  `json:"last_error,omitempty"`
	CancelledAt   float64 `json:"cancelled_at,omitempty"`
	CreatedAt     float64 `json:"created_at"`
	UpdatedAt     float64 `json:"updated_at"`
}

type StepClaim struct {
	RunID        string  `json:"run_id"`
	SessionID    string  `json:"session_id"`
	StepID       string  `json:"step_id"`
	Attempt      int     `json:"attempt"`
	LeaseToken   string  `json:"lease_token"`
	StateVersion int     `json:"state_version"`
	LeaseUntil   float64 `json:"lease_until"`
}

type Event struct {
	EventID      string     `json:"event_id"`
	RunID        string     `json:"run_id"`
	SessionID    string     `json:"session_id,omitempty"`
	StepID       string     `json:"step_id,omitempty"`
	Seq          int        `json:"seq"`
	Type         string     `json:"type"`
	Timestamp    float64    `json:"timestamp"`
	AgentRole    string     `json:"agent_role,omitempty"`
	StateVersion int        `json:"state_version,omitempty"`
	CausalToken  string     `json:"causal_token,omitempty"`
	PayloadHash  string     `json:"payload_hash,omitempty"`
	PayloadRef   string     `json:"payload_ref,omitempty"`
	Payload      JSONObject `json:"payload,omitempty"`
}

type ToolLedgerEntry struct {
	LedgerID       string  `json:"ledger_id"`
	RunID          string  `json:"run_id"`
	SessionID      string  `json:"session_id,omitempty"`
	StepID         string  `json:"step_id"`
	ToolName       string  `json:"tool_name"`
	ToolVersion    string  `json:"tool_version"`
	ToolCallID     string  `json:"tool_call_id"`
	IdempotencyKey string  `json:"idempotency_key"`
	CausalToken    string  `json:"causal_token"`
	RequestHash    string  `json:"request_hash"`
	RequestRef     string  `json:"request_ref"`
	Status         string  `json:"status"`
	ExternalID     string  `json:"external_id,omitempty"`
	ResponseHash   string  `json:"response_hash,omitempty"`
	ResponseRef    string  `json:"response_ref,omitempty"`
	ErrorType      string  `json:"error_type,omitempty"`
	Response       any     `json:"response,omitempty"`
	CreatedAt      float64 `json:"created_at"`
	UpdatedAt      float64 `json:"updated_at"`
}

type ApprovalRequest struct {
	ApprovalID     string  `json:"approval_id"`
	ApprovalKey    string  `json:"approval_key"`
	RunID          string  `json:"run_id"`
	SessionID      string  `json:"session_id,omitempty"`
	StepID         string  `json:"step_id"`
	ToolName       string  `json:"tool_name"`
	RiskLevel      string  `json:"risk_level"`
	Status         string  `json:"status"`
	Reason         string  `json:"reason,omitempty"`
	RequestHash    string  `json:"request_hash"`
	RequestRef     string  `json:"request_ref"`
	RequestedBy    string  `json:"requested_by,omitempty"`
	ApprovedBy     string  `json:"approved_by,omitempty"`
	DecisionReason string  `json:"decision_reason,omitempty"`
	CreatedAt      float64 `json:"created_at"`
	UpdatedAt      float64 `json:"updated_at"`
}

type CostRecord struct {
	CostID    string     `json:"cost_id"`
	RunID     string     `json:"run_id"`
	SessionID string     `json:"session_id,omitempty"`
	StepID    string     `json:"step_id,omitempty"`
	Category  string     `json:"category"`
	Name      string     `json:"name"`
	Amount    float64    `json:"amount"`
	Unit      string     `json:"unit"`
	Metadata  JSONObject `json:"metadata,omitempty"`
	CreatedAt float64    `json:"created_at"`
}

type CostSummary struct {
	ToolCalls   float64            `json:"tool_calls"`
	ModelTokens float64            `json:"model_tokens"`
	TotalUSD    float64            `json:"total_usd"`
	ByCategory  map[string]float64 `json:"by_category"`
}

const MediaSchemaVersion = "agentledger.media.v0"
const StreamSchemaVersion = "agentledger.stream.v0"

var mediaKinds = map[string]bool{
	"image": true, "audio": true, "video": true, "frame": true,
	"audio_segment": true, "video_segment": true, "transcript": true,
	"embedding": true, "derived": true,
}

type Artifact struct {
	ArtifactID string     `json:"artifact_id"`
	RunID      string     `json:"run_id"`
	StepID     string     `json:"step_id,omitempty"`
	Name       string     `json:"name"`
	BlobHash   string     `json:"blob_hash"`
	BlobRef    string     `json:"blob_ref"`
	Metadata   JSONObject `json:"metadata"`
	CreatedAt  float64    `json:"created_at"`
}

type MediaArtifactOptions struct {
	URI            string
	ContentRef     string
	MediaMetadata  JSONObject
	Lineage        JSONObject
	DerivedOutputs JSONObject
	Metadata       JSONObject
}

type StreamChunkRef struct {
	StreamID    string
	ChunkID     string
	Offset      any
	ContentRef  string
	ContentHash string
	Sequence    int
	EventTime   float64
	Metadata    JSONObject
}

type StreamCheckpointOptions struct {
	StreamID         string
	ConsumerID       string
	Offset           any
	Watermark        any
	Chunk            any
	PartialResultRef string
	Backpressure     JSONObject
	Metadata         JSONObject
}

type AppendEventInput struct {
	RunID        string
	SessionID    string
	StepID       string
	Type         string
	Payload      JSONObject
	AgentRole    string
	StateVersion int
	CausalToken  string
	PayloadHash  string
	PayloadRef   string
}

type LedgerReservation struct {
	RunID          string
	SessionID      string
	StepID         string
	ToolName       string
	ToolVersion    string
	ToolCallID     string
	IdempotencyKey string
	CausalToken    string
	RequestHash    string
	RequestRef     string
}

type LedgerUpdate struct {
	IdempotencyKey string
	Status         string
	ExternalID     string
	ResponseHash   string
	ResponseRef    string
	ErrorType      string
	Response       any
}

type ApprovalRequestInput struct {
	ApprovalKey string
	RunID       string
	SessionID   string
	StepID      string
	ToolName    string
	RiskLevel   string
	Reason      string
	RequestHash string
	RequestRef  string
	RequestedBy string
}

type CostRecordInput struct {
	RunID     string
	SessionID string
	StepID    string
	Category  string
	Name      string
	Amount    float64
	Unit      string
	Metadata  JSONObject
}

func nowSeconds() float64 {
	return float64(time.Now().UnixNano()) / 1e9
}

func newID(prefix string) string {
	buf := make([]byte, 12)
	if _, err := rand.Read(buf); err != nil {
		panic(fmt.Sprintf("agentledger id generation failed: %v", err))
	}
	return prefix + "_" + hex.EncodeToString(buf)
}

func sha256JSON(value any) (string, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

func mustJSON(value any) string {
	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprintf(`{"marshal_error":%q}`, err.Error())
	}
	return string(data)
}

func cloneJSONObject(value JSONObject) JSONObject {
	if value == nil {
		return JSONObject{}
	}
	data, _ := json.Marshal(value)
	var out JSONObject
	_ = json.Unmarshal(data, &out)
	if out == nil {
		return JSONObject{}
	}
	return out
}

func cloneAny(value any) any {
	if value == nil {
		return nil
	}
	data, _ := json.Marshal(value)
	var out any
	_ = json.Unmarshal(data, &out)
	return out
}

func mergePatch(base JSONObject, patch JSONObject) JSONObject {
	out := cloneJSONObject(base)
	for key, value := range patch {
		if value == nil {
			delete(out, key)
			continue
		}
		patchMap, patchOK := value.(map[string]any)
		baseMap, baseOK := out[key].(map[string]any)
		if patchOK && baseOK {
			out[key] = mergePatch(JSONObject(baseMap), JSONObject(patchMap))
			continue
		}
		out[key] = cloneAny(value)
	}
	return out
}
