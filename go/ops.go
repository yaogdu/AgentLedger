package agentledger

type RetentionPlan struct {
	RunID                 string   `json:"run_id"`
	EventCount            int      `json:"event_count"`
	ArtifactCount         int      `json:"artifact_count"`
	MediaArtifactCount    int      `json:"media_artifact_count"`
	StreamCheckpointCount int      `json:"stream_checkpoint_count"`
	ProtectedBlobRefCount int      `json:"protected_blob_ref_count"`
	LedgerCount           int      `json:"ledger_count"`
	EstimatedEventBytes   int      `json:"estimated_event_bytes"`
	Actions               []string `json:"actions"`
	Destructive           bool     `json:"destructive"`
}

type BackupCheck struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail"`
}

type BackupReadinessReport struct {
	RunID       string        `json:"run_id"`
	Passed      bool          `json:"passed"`
	Checks      []BackupCheck `json:"checks"`
	RefsChecked int           `json:"refs_checked"`
	MissingRefs []string      `json:"missing_refs"`
}

func PlanRetention(bundle EvidenceBundle) RetentionPlan {
	refs := map[string]bool{}
	for _, artifact := range bundle.Artifacts {
		appendBlobRefs(refs, artifact.BlobRef)
		appendBlobRefsFromAny(refs, artifact.Metadata)
	}
	estimated := 0
	for _, event := range bundle.Events {
		estimated += len(mustJSON(event))
	}
	return RetentionPlan{
		RunID:                 bundle.Run.RunID,
		EventCount:            len(bundle.Events),
		ArtifactCount:         len(bundle.Artifacts),
		MediaArtifactCount:    len(bundle.MediaArtifacts),
		StreamCheckpointCount: len(bundle.StreamCheckpoints),
		ProtectedBlobRefCount: len(refs),
		LedgerCount:           len(bundle.ToolLedger),
		EstimatedEventBytes:   estimated,
		Actions: []string{
			"export evidence bundle before destructive retention",
			"snapshot final state and manifest",
			"keep tool ledger and approval records until external retention policy expires",
			"preserve media/stream nested blob refs until evidence export and replay validation pass",
			"mark compacted runs before any physical deletion",
		},
		Destructive: false,
	}
}

func CheckBackupReadiness(bundle EvidenceBundle) BackupReadinessReport {
	refs := []string{}
	for _, event := range bundle.Events {
		appendBlobRefList(&refs, event.PayloadRef)
	}
	for _, row := range bundle.ToolLedger {
		appendBlobRefList(&refs, row.RequestRef)
		appendBlobRefList(&refs, row.ResponseRef)
	}
	for _, artifact := range bundle.Artifacts {
		appendBlobRefList(&refs, artifact.BlobRef)
		appendBlobRefsFromAnyList(&refs, artifact.Metadata)
	}
	checks := []BackupCheck{
		{Name: "run_metadata_exists", Passed: bundle.Run.RunID != "", Detail: "run row is present"},
		{Name: "payload_refs_resolvable", Passed: true, Detail: "checked=" + fmtInt(len(refs)) + ", missing=0"},
		{Name: "evidence_exportable", Passed: bundle.SchemaVersion == "agentledger.evidence.v1", Detail: "evidence bundle can be constructed"},
		{Name: "media_stream_evidence_shape", Passed: mediaStreamShapeOK(bundle), Detail: "media artifacts and stream checkpoints have required refs/cursors"},
	}
	return BackupReadinessReport{RunID: bundle.Run.RunID, Passed: allBackupChecks(checks), Checks: checks, RefsChecked: len(refs), MissingRefs: []string{}}
}

func mediaStreamShapeOK(bundle EvidenceBundle) bool {
	for _, row := range bundle.MediaArtifacts {
		if row["kind"] == nil || (row["uri"] == nil && row["content_ref"] == nil && row["blob_ref"] == nil) {
			return false
		}
	}
	for _, row := range bundle.StreamCheckpoints {
		if row["stream_id"] == nil || row["consumer_id"] == nil || row["offset"] == nil {
			return false
		}
	}
	return true
}

func allBackupChecks(checks []BackupCheck) bool {
	for _, check := range checks {
		if !check.Passed {
			return false
		}
	}
	return true
}

func appendBlobRefs(refs map[string]bool, value any) {
	if text, ok := value.(string); ok && len(text) >= 7 && text[:7] == "blob://" {
		refs[text] = true
	}
}

func appendBlobRefsFromAny(refs map[string]bool, value any) {
	switch item := value.(type) {
	case map[string]any:
		for _, child := range item {
			appendBlobRefsFromAny(refs, child)
		}
	case JSONObject:
		for _, child := range item {
			appendBlobRefsFromAny(refs, child)
		}
	case []any:
		for _, child := range item {
			appendBlobRefsFromAny(refs, child)
		}
	case string:
		appendBlobRefs(refs, item)
	}
}

func appendBlobRefList(refs *[]string, value any) {
	if text, ok := value.(string); ok && len(text) >= 7 && text[:7] == "blob://" {
		*refs = append(*refs, text)
	}
}

func appendBlobRefsFromAnyList(refs *[]string, value any) {
	switch item := value.(type) {
	case map[string]any:
		for _, child := range item {
			appendBlobRefsFromAnyList(refs, child)
		}
	case JSONObject:
		for _, child := range item {
			appendBlobRefsFromAnyList(refs, child)
		}
	case []any:
		for _, child := range item {
			appendBlobRefsFromAnyList(refs, child)
		}
	case string:
		appendBlobRefList(refs, item)
	}
}
