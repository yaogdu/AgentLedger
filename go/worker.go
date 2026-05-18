package agentledger

import "context"

var terminalRunStatuses = map[string]bool{"completed": true, "failed": true, "cancelled": true}

type WorkerRunSummary struct {
	WorkerID          string `json:"worker_id"`
	RunID             string `json:"run_id,omitempty"`
	Iterations        int    `json:"iterations"`
	Attempts          int    `json:"attempts"`
	SucceededAttempts int    `json:"succeeded_attempts"`
	RecoveredLeases   int    `json:"recovered_leases"`
	FinalStatus       string `json:"final_status,omitempty"`
	StoppedReason     string `json:"stopped_reason"`
}

type LocalWorker struct {
	Runtime        *Runtime
	WorkerID       string
	AgentRole      string
	LeaseSeconds   int
	RecoverExpired bool
}

func NewLocalWorker(runtime *Runtime, workerID, agentRole string) *LocalWorker {
	if workerID == "" {
		workerID = "worker-local"
	}
	if agentRole == "" {
		agentRole = "Agent"
	}
	return &LocalWorker{Runtime: runtime, WorkerID: workerID, AgentRole: agentRole, LeaseSeconds: 60, RecoverExpired: true}
}

func (w *LocalWorker) RunUntilIdle(ctx context.Context, runID string, maxIterations int, agent AgentFunc) (WorkerRunSummary, error) {
	if maxIterations <= 0 {
		maxIterations = 100
	}
	summary := WorkerRunSummary{WorkerID: w.WorkerID, RunID: runID, StoppedReason: "max_iterations"}
	for i := 1; i <= maxIterations; i++ {
		summary.Iterations = i
		if w.RecoverExpired {
			recovered, err := w.Runtime.Store.RecoverExpiredLeases()
			if err != nil {
				return summary, err
			}
			summary.RecoveredLeases += recovered
		}
		if runID != "" {
			run, err := w.Runtime.Store.Run(runID)
			if err != nil {
				return summary, err
			}
			if terminalRunStatuses[run.Status] {
				summary.FinalStatus = run.Status
				summary.StoppedReason = "terminal_status"
				break
			}
		}
		ok, err := w.Runtime.RunOnce(ctx, runID, w.WorkerID, w.AgentRole, w.LeaseSeconds, agent)
		if err != nil {
			return summary, err
		}
		if !ok {
			summary.StoppedReason = "idle"
			break
		}
		summary.Attempts++
		if ok {
			summary.SucceededAttempts++
		}
	}
	if runID != "" {
		if run, err := w.Runtime.Store.Run(runID); err == nil {
			summary.FinalStatus = run.Status
			if terminalRunStatuses[run.Status] {
				summary.StoppedReason = "terminal_status"
			}
		}
	}
	return summary, nil
}

type WorkerServiceSummary struct {
	WorkerID          string `json:"worker_id"`
	RunID             string `json:"run_id,omitempty"`
	Loops             int    `json:"loops"`
	Attempts          int    `json:"attempts"`
	SucceededAttempts int    `json:"succeeded_attempts"`
	RecoveredLeases   int    `json:"recovered_leases"`
	IdlePolls         int    `json:"idle_polls"`
	StoppedReason     string `json:"stopped_reason"`
	FinalStatus       string `json:"final_status,omitempty"`
	StopRequested     bool   `json:"stop_requested"`
}

type WorkerService struct {
	Worker        *LocalWorker
	StopRequested bool
	StopReason    string
}

func NewWorkerService(worker *LocalWorker) *WorkerService {
	return &WorkerService{Worker: worker, StopReason: "stop_requested"}
}
func (s *WorkerService) RequestStop(reason string) {
	if reason == "" {
		reason = "stop_requested"
	}
	s.StopRequested = true
	s.StopReason = reason
}
func (s *WorkerService) Serve(ctx context.Context, runID string, maxLoops int, maxIdlePolls int, agent AgentFunc) (WorkerServiceSummary, error) {
	if maxLoops <= 0 {
		maxLoops = 100
	}
	summary := WorkerServiceSummary{WorkerID: s.Worker.WorkerID, RunID: runID, StoppedReason: "max_loops"}
	for summary.Loops < maxLoops {
		if s.StopRequested {
			summary.StoppedReason = s.StopReason
			summary.StopRequested = true
			break
		}
		summary.Loops++
		runSummary, err := s.Worker.RunUntilIdle(ctx, runID, 1, agent)
		if err != nil {
			return summary, err
		}
		summary.Attempts += runSummary.Attempts
		summary.SucceededAttempts += runSummary.SucceededAttempts
		summary.RecoveredLeases += runSummary.RecoveredLeases
		summary.FinalStatus = runSummary.FinalStatus
		if runSummary.FinalStatus != "" && terminalRunStatuses[runSummary.FinalStatus] {
			summary.StoppedReason = "terminal_status"
			break
		}
		if runSummary.Attempts == 0 {
			summary.IdlePolls++
			if maxIdlePolls > 0 && summary.IdlePolls >= maxIdlePolls {
				summary.StoppedReason = "idle"
				break
			}
		} else {
			summary.IdlePolls = 0
		}
	}
	return summary, nil
}
