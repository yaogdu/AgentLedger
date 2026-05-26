// Package framework exposes dependency-free framework adapter boundaries for Go.
package framework

import runtime "github.com/yaogdu/AgentLedger/go"

type AgentFunc = runtime.FrameworkAgentFunc
type FunctionAdapter = runtime.FunctionAdapter
type MethodAdapter = runtime.MethodFrameworkAdapter
type MethodHandler = runtime.MethodHandler

func NewFunction(fn AgentFunc, role string) FunctionAdapter {
	return runtime.NewFunctionAdapter(fn, role)
}

func NewMethod(targetName, role string, candidates []string, methods map[string]MethodHandler, outputKey string) MethodAdapter {
	return runtime.NewMethodFrameworkAdapter(targetName, role, candidates, methods, outputKey)
}

