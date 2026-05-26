// Package docker exposes the AgentLedger Docker sandbox adapter boundary for Go.
package docker

import runtime "github.com/yaogdu/AgentLedger/go"

type Adapter = runtime.DockerSandboxAdapter
type Policy = runtime.SandboxPolicy
type JSONObject = runtime.JSONObject

func New(image string) Adapter {
	return runtime.DockerSandboxAdapter{Image: image}
}

