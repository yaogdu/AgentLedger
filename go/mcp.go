package agentledger

import (
	"context"
	"fmt"
	"sort"
)

type MCPCall func(name string, args JSONObject) (any, error)
type MCPResourceRead func(uri string) (any, error)

type MCPResourceDescriptor struct {
	URI      string `json:"uri"`
	Name     string `json:"name"`
	MimeType string `json:"mimeType"`
}

func (d MCPResourceDescriptor) ToJSON() JSONObject {
	mime := d.MimeType
	if mime == "" {
		mime = "application/json"
	}
	return JSONObject{"uri": d.URI, "name": d.Name, "mimeType": mime}
}

type InMemoryMCPToolServer struct {
	tools map[string]mcpToolEntry
}

type mcpToolEntry struct {
	descriptor JSONObject
	handler    MCPCall
}

func NewInMemoryMCPToolServer() *InMemoryMCPToolServer {
	return &InMemoryMCPToolServer{tools: map[string]mcpToolEntry{}}
}

func (s *InMemoryMCPToolServer) AddTool(descriptor JSONObject, handler MCPCall) {
	name, _ := descriptor["name"].(string)
	s.tools[name] = mcpToolEntry{descriptor: descriptor, handler: handler}
}

func (s *InMemoryMCPToolServer) ListTools() []JSONObject {
	names := []string{}
	for name := range s.tools {
		names = append(names, name)
	}
	sort.Strings(names)
	out := []JSONObject{}
	for _, name := range names {
		out = append(out, s.tools[name].descriptor)
	}
	return out
}

func (s *InMemoryMCPToolServer) CallTool(name string, args JSONObject) (any, error) {
	entry, ok := s.tools[name]
	if !ok {
		return nil, fmt.Errorf("MCP tool not found: %s", name)
	}
	return entry.handler(name, args)
}

type InMemoryMCPContextServer struct {
	resources map[string]mcpResourceEntry
}

type mcpResourceEntry struct {
	descriptor MCPResourceDescriptor
	reader     MCPResourceRead
}

func NewInMemoryMCPContextServer() *InMemoryMCPContextServer {
	return &InMemoryMCPContextServer{resources: map[string]mcpResourceEntry{}}
}

func (s *InMemoryMCPContextServer) AddResource(uri, name, mimeType string, reader MCPResourceRead) {
	if mimeType == "" {
		mimeType = "application/json"
	}
	s.resources[uri] = mcpResourceEntry{descriptor: MCPResourceDescriptor{URI: uri, Name: name, MimeType: mimeType}, reader: reader}
}

func (s *InMemoryMCPContextServer) ListResources() []JSONObject {
	uris := []string{}
	for uri := range s.resources {
		uris = append(uris, uri)
	}
	sort.Strings(uris)
	out := []JSONObject{}
	for _, uri := range uris {
		out = append(out, s.resources[uri].descriptor.ToJSON())
	}
	return out
}

func (s *InMemoryMCPContextServer) ReadResource(uri string) (JSONObject, error) {
	entry, ok := s.resources[uri]
	if !ok {
		return nil, fmt.Errorf("MCP resource not found: %s", uri)
	}
	content, err := entry.reader(uri)
	if err != nil {
		return nil, err
	}
	return JSONObject{"resource": entry.descriptor.ToJSON(), "content": content}, nil
}

type MCPToolAdapter struct {
	ClientCall MCPCall
}

func (a MCPToolAdapter) ToolSpecFromDescriptor(descriptor JSONObject) ToolSpec {
	name, _ := descriptor["name"].(string)
	version, _ := descriptor["version"].(string)
	annotations, _ := descriptor["annotations"].(map[string]any)
	if annotations == nil {
		if obj, ok := descriptor["annotations"].(JSONObject); ok {
			annotations = map[string]any(obj)
		}
	}
	sideEffect, _ := annotations["side_effect"].(string)
	if sideEffect == "" {
		sideEffect = "none"
	}
	riskLevel, _ := annotations["risk_level"].(string)
	if riskLevel == "" {
		riskLevel = "low"
	}
	idem, ok := annotations["idempotency_required"].(bool)
	if !ok {
		idem = sideEffect != "none"
	}
	input, _ := descriptor["inputSchema"].(JSONObject)
	if input == nil {
		input, _ = descriptor["input_schema"].(JSONObject)
	}
	output, _ := descriptor["outputSchema"].(JSONObject)
	if output == nil {
		output, _ = descriptor["output_schema"].(JSONObject)
	}
	return ToolSpec{Name: name, Version: firstNonEmpty(version, "v1"), InputSchema: input, OutputSchema: output, SideEffect: sideEffect, RiskLevel: riskLevel, IdempotencyRequired: idem, Func: func(ctx context.Context, args JSONObject) (any, error) {
		return a.ClientCall(name, args)
	}}
}

type MCPContextAdapter struct {
	ResourceRead MCPResourceRead
}

func (a MCPContextAdapter) ReadToolSpec(name, riskLevel string) ToolSpec {
	if name == "" {
		name = "mcp.context.read"
	}
	if riskLevel == "" {
		riskLevel = "low"
	}
	return ToolSpec{Name: name, Version: "v1", Description: "Read an MCP-style context resource by URI.", SideEffect: "none", RiskLevel: riskLevel, InputSchema: JSONObject{"type": "object", "required": []any{"uri"}, "properties": JSONObject{"uri": JSONObject{"type": "string", "minLength": 1}}, "additionalProperties": false}, OutputSchema: JSONObject{"type": "object"}, Func: func(ctx context.Context, args JSONObject) (any, error) {
		uri, _ := args["uri"].(string)
		return a.ResourceRead(uri)
	}}
}

func firstNonEmpty(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}
