package agentledger

// OptionalAdapterCapability describes an integration boundary that is supported
// by runtime contract but intentionally kept out of the dependency-free core.
type OptionalAdapterCapability struct {
	Name                 string   `json:"name"`
	Category             string   `json:"category"`
	CoreImportsHeavySDKs bool     `json:"core_imports_heavy_sdks"`
	AdapterIsOptional    bool     `json:"adapter_is_optional"`
	FailClosedWithout    bool     `json:"fail_closed_without_adapter"`
	ContractSurface      []string `json:"contract_surface"`
}

func OptionalAdapterCapabilities() []OptionalAdapterCapability {
	return []OptionalAdapterCapability{
		{Name: "postgres", Category: "storage", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"ddl_for", "migrations_for", "state_store"}},
		{Name: "mysql", Category: "storage", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"ddl_for", "migrations_for", "state_store"}},
		{Name: "s3", Category: "blobstore", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"put_json", "get_json", "content_address"}},
		{Name: "docker", Category: "sandbox", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"sandbox_policy", "sandbox_result", "tool_gateway"}},
		{Name: "e2b", Category: "sandbox", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"sandbox_policy", "sandbox_result", "tool_gateway"}},
		{Name: "bubblewrap", Category: "sandbox", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"sandbox_policy", "sandbox_result", "tool_gateway"}},
		{Name: "kubernetes", Category: "sandbox", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"sandbox_policy", "sandbox_result", "tool_gateway"}},
		{Name: "gvisor", Category: "sandbox", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"sandbox_policy", "sandbox_result", "tool_gateway"}},
		{Name: "firecracker", Category: "sandbox", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"sandbox_policy", "sandbox_result", "tool_gateway"}},
		{Name: "langgraph", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter", "checkpoint_contract"}},
		{Name: "langchain", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter"}},
		{Name: "crewai", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter"}},
		{Name: "autogen", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter"}},
		{Name: "openai-agents-sdk", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter"}},
		{Name: "llamaindex", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter"}},
		{Name: "semantic-kernel", Category: "framework", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"framework_adapter"}},
		{Name: "mcp-transport", Category: "mcp", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"mcp_tool_descriptor", "mcp_resource_descriptor"}},
		{Name: "langfuse", Category: "observability", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"evidence_bundle", "trace_payload", "correlation_ids"}},
		{Name: "shadow-runner", Category: "shadow", AdapterIsOptional: true, FailClosedWithout: true, ContractSurface: []string{"evidence_bundle", "tool_ledger", "state_diff"}},
	}
}
