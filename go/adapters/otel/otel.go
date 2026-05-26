// Package otel exposes the AgentLedger OTLP transport adapter boundary for Go.
package otel

import runtime "github.com/yaogdu/AgentLedger/go"

type Client = runtime.OTLPClient
type Transport = runtime.OTLPTransport

func New(endpoint string, client Client) Transport {
	return runtime.OTLPTransport{Endpoint: endpoint, Client: client}
}

