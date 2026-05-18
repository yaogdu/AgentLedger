package agentledger

type RecoverySummary struct {
	RecoveredSteps int `json:"recovered_steps"`
}

type SchedulerStepStatus struct {
	StepID        string  `json:"step_id"`
	Status        string  `json:"status"`
	Owner         string  `json:"owner"`
	Attempt       int     `json:"attempt"`
	LeaseUntil    float64 `json:"lease_until"`
	LastErrorType string  `json:"last_error_type,omitempty"`
}

type SchedulerStatus struct {
	RunID        string                `json:"run_id"`
	RunStatus    string                `json:"run_status"`
	StateVersion int                   `json:"state_version"`
	Steps        []SchedulerStepStatus `json:"steps"`
	CostSummary  CostSummary           `json:"cost_summary"`
}

type RuntimeScheduler struct{ Store *JSONStore }

func NewRuntimeScheduler(store *JSONStore) *RuntimeScheduler { return &RuntimeScheduler{Store: store} }

func (s *RuntimeScheduler) RecoverExpiredLeases() (RecoverySummary, error) {
	recovered, err := s.Store.RecoverExpiredLeases()
	return RecoverySummary{RecoveredSteps: recovered}, err
}

func (s *RuntimeScheduler) CancelRun(runID, reason string) (int, error) {
	return s.Store.CancelRun(runID, reason)
}

func (s *RuntimeScheduler) Status(runID string) (SchedulerStatus, error) {
	run, err := s.Store.Run(runID)
	if err != nil {
		return SchedulerStatus{}, err
	}
	items := []SchedulerStepStatus{}
	for _, step := range s.Store.Steps(runID) {
		items = append(items, SchedulerStepStatus{StepID: step.StepID, Status: step.Status, Owner: step.Owner, Attempt: step.Attempt, LeaseUntil: step.LeaseUntil, LastErrorType: step.LastErrorType})
	}
	return SchedulerStatus{RunID: runID, RunStatus: run.Status, StateVersion: run.StateVersion, Steps: items, CostSummary: s.Store.CostSummary(runID)}, nil
}
