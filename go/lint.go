package agentledger

import "strings"

const IgnoreSameLine = "agentledger: ignore-boundary"
const IgnoreNextLine = "agentledger: ignore-next-line"

type BoundaryLintRule struct {
	RuleID     string
	Pattern    string
	Category   string
	Message    string
	Suggestion string
	Prefix     bool
}

type BoundaryLintFinding struct {
	Path       string `json:"path"`
	Line       int    `json:"line"`
	Column     int    `json:"column"`
	RuleID     string `json:"rule_id"`
	Severity   string `json:"severity"`
	Callee     string `json:"callee"`
	Category   string `json:"category"`
	Message    string `json:"message"`
	Suggestion string `json:"suggestion"`
}

type BoundaryLintReport struct {
	Passed       bool                  `json:"passed"`
	ScannedFiles []string              `json:"scanned_files"`
	FindingCount int                   `json:"finding_count"`
	Findings     []BoundaryLintFinding `json:"findings"`
}

func (r BoundaryLintRule) matches(callee string) bool {
	if r.Prefix {
		return strings.HasPrefix(callee, r.Pattern)
	}
	return callee == r.Pattern
}

func DefaultBoundaryRules() []BoundaryLintRule {
	return []BoundaryLintRule{
		{RuleID: "direct-shell-os-system", Pattern: "os.system", Category: "shell", Message: "direct shell execution bypasses ToolGateway, policy, ledger, sandbox, and audit", Suggestion: "wrap shell execution as a runtime-managed tool and call ctx.CallTool('shell.exec', args)"},
		{RuleID: "direct-shell-subprocess", Pattern: "subprocess.", Category: "shell", Message: "direct subprocess execution bypasses ToolGateway, policy, ledger, sandbox, and audit", Suggestion: "wrap command execution as a runtime-managed tool and call ctx.CallTool('shell.exec', args)", Prefix: true},
		{RuleID: "direct-http-requests", Pattern: "requests.", Category: "network", Message: "direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit", Suggestion: "register the HTTP/API call as a runtime-managed tool and call ctx.CallTool(...) ", Prefix: true},
		{RuleID: "direct-http-httpx", Pattern: "httpx.", Category: "network", Message: "direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit", Suggestion: "register the HTTP/API call as a runtime-managed tool and call ctx.CallTool(...) ", Prefix: true},
		{RuleID: "direct-openai-sdk", Pattern: "openai.", Category: "model", Message: "direct model SDK usage bypasses model provider archives, replay, budget, and attribution", Suggestion: "call models through the runtime model boundary", Prefix: true},
		{RuleID: "direct-anthropic-sdk", Pattern: "anthropic.", Category: "model", Message: "direct model SDK usage bypasses model provider archives, replay, budget, and attribution", Suggestion: "call models through the runtime model boundary", Prefix: true},
	}
}

func ScanBoundarySource(path, source string, rules []BoundaryLintRule) BoundaryLintReport {
	if rules == nil {
		rules = DefaultBoundaryRules()
	}
	findings := []BoundaryLintFinding{}
	lines := strings.Split(source, "\n")
	for i, line := range lines {
		prev := ""
		if i > 0 {
			prev = lines[i-1]
		}
		if strings.Contains(line, IgnoreSameLine) || strings.Contains(prev, IgnoreNextLine) {
			continue
		}
		for _, rule := range rules {
			idx := strings.Index(line, rule.Pattern)
			if idx < 0 {
				continue
			}
			callee := rule.Pattern
			if rule.Prefix {
				end := idx + len(rule.Pattern)
				for end < len(line) {
					c := line[end]
					if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '.' {
						end++
					} else {
						break
					}
				}
				callee = line[idx:end]
			}
			findings = append(findings, BoundaryLintFinding{Path: path, Line: i + 1, Column: idx + 1, RuleID: rule.RuleID, Severity: "error", Callee: callee, Category: rule.Category, Message: rule.Message, Suggestion: rule.Suggestion})
			break
		}
	}
	return BoundaryLintReport{Passed: len(findings) == 0, ScannedFiles: []string{path}, FindingCount: len(findings), Findings: findings}
}
