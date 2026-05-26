// Package mcp exposes the AgentLedger MCP adapter boundary for Go.
package mcp

import runtime "github.com/yaogdu/AgentLedger/go"

type ContextAdapter = runtime.MCPContextAdapter
type ContextServer = runtime.InMemoryMCPContextServer
type ResourceDescriptor = runtime.MCPResourceDescriptor
type ResourceRead = runtime.MCPResourceRead
type ToolAdapter = runtime.MCPToolAdapter
type ToolCall = runtime.MCPCall
type ToolServer = runtime.InMemoryMCPToolServer

func NewToolServer() *ToolServer {
	return runtime.NewInMemoryMCPToolServer()
}

func NewContextServer() *ContextServer {
	return runtime.NewInMemoryMCPContextServer()
}

func NewToolAdapter(call ToolCall) ToolAdapter {
	return runtime.MCPToolAdapter{ClientCall: call}
}

func NewContextAdapter(read ResourceRead) ContextAdapter {
	return runtime.MCPContextAdapter{ResourceRead: read}
}

