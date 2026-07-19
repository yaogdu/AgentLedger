export function langfuseTracePayload(bundle, { project = null, environment = null, release = null, tags = [] } = {}) {
  const runId = bundle?.run?.run_id ?? 'run_unknown';
  const events = Array.isArray(bundle?.events) ? bundle.events : [];
  const batch = events.map((event, index) => {
    const seq = Number(event?.seq ?? index + 1);
    return {
      type: 'trace-span',
      traceId: runId,
      id: `evt-${String(seq).padStart(6, '0')}`,
      parentObservationId: null,
      name: String(event?.type ?? 'event'),
      startTime: Number(event?.timestamp ?? 0),
      endTime: Number(event?.timestamp ?? 0),
      metadata: {
        'agentledger.run_id': runId,
        'agentledger.session_id': event?.session_id ?? null,
        'agentledger.step_id': event?.step_id ?? null,
        'agentledger.seq': seq,
        'agentledger.state_version': event?.state_version ?? null,
        'agentledger.payload_hash': event?.payload_hash ?? null,
        'agentledger.payload_ref': event?.payload_ref ?? null,
        'agentledger.exporter': 'langfuse',
        'agentledger.project': project,
        'agentledger.environment': environment,
        'agentledger.release': release,
      },
      tags,
    };
  });
  return { batch, metadata: { source: 'agentledger', project, environment, release, tags } };
}

export const adapterPackage = {
  name: 'agentledger-langfuse',
  runtimePackage: 'agentledger-runtime',
  version: '1.5.2',
  category: 'observability',
};
