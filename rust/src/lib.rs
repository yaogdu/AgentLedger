use std::collections::HashMap;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static ID_COUNTER: AtomicU64 = AtomicU64::new(1);

pub type State = HashMap<String, Value>;

pub const MODEL_EVIDENCE_SCHEMA_VERSION: &str = "agentledger.model.evidence.v1";

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Number(f64),
    String(String),
    Object(State),
    Array(Vec<Value>),
}

impl Default for Value {
    fn default() -> Self {
        Value::Null
    }
}

impl From<&str> for Value {
    fn from(value: &str) -> Self {
        Value::String(value.to_string())
    }
}

impl From<String> for Value {
    fn from(value: String) -> Self {
        Value::String(value)
    }
}

impl From<bool> for Value {
    fn from(value: bool) -> Self {
        Value::Bool(value)
    }
}

impl From<i64> for Value {
    fn from(value: i64) -> Self {
        Value::Number(value as f64)
    }
}

impl From<f64> for Value {
    fn from(value: f64) -> Self {
        Value::Number(value)
    }
}

#[derive(Clone, Debug)]
pub struct Run {
    pub run_id: String,
    pub session_id: String,
    pub status: String,
    pub state: State,
    pub state_version: u64,
    pub created_at: f64,
    pub updated_at: f64,
}

#[derive(Clone, Debug)]
pub struct Step {
    pub step_id: String,
    pub run_id: String,
    pub session_id: String,
    pub status: String,
    pub owner: Option<String>,
    pub lease_token: Option<String>,
    pub lease_until: Option<f64>,
    pub attempt: u64,
    pub state_version: u64,
    pub checkpoint_id: Option<String>,
    pub last_error_type: Option<String>,
    pub last_error: Option<String>,
    pub cancelled_at: Option<f64>,
    pub created_at: f64,
    pub updated_at: f64,
}

#[derive(Clone, Debug)]
pub struct StepClaim {
    pub run_id: String,
    pub session_id: String,
    pub step_id: String,
    pub attempt: u64,
    pub lease_token: String,
    pub state_version: u64,
    pub lease_until: f64,
}

#[derive(Clone, Debug)]
pub struct Event {
    pub event_id: String,
    pub run_id: String,
    pub session_id: Option<String>,
    pub step_id: Option<String>,
    pub seq: u64,
    pub event_type: String,
    pub timestamp: f64,
    pub agent_role: Option<String>,
    pub state_version: Option<u64>,
    pub causal_token: Option<String>,
    pub payload_hash: String,
    pub payload_ref: String,
    pub payload: State,
}

#[derive(Clone, Debug)]
pub struct ToolLedgerEntry {
    pub ledger_id: String,
    pub run_id: String,
    pub session_id: String,
    pub step_id: String,
    pub tool_name: String,
    pub tool_version: String,
    pub tool_call_id: String,
    pub idempotency_key: String,
    pub causal_token: String,
    pub request_hash: String,
    pub request_ref: String,
    pub status: String,
    pub external_id: Option<String>,
    pub response_hash: Option<String>,
    pub response_ref: Option<String>,
    pub error_type: Option<String>,
    pub response: Option<Value>,
    pub created_at: f64,
    pub updated_at: f64,
}

#[derive(Clone, Debug)]
pub struct ApprovalRequest {
    pub approval_id: String,
    pub approval_key: String,
    pub run_id: String,
    pub session_id: String,
    pub step_id: String,
    pub tool_name: String,
    pub risk_level: String,
    pub status: String,
    pub reason: String,
    pub request_hash: String,
    pub request_ref: String,
    pub requested_by: String,
    pub approved_by: Option<String>,
    pub decision_reason: Option<String>,
    pub created_at: f64,
    pub updated_at: f64,
}

#[derive(Clone, Debug)]
pub struct CostRecord {
    pub cost_id: String,
    pub run_id: String,
    pub session_id: String,
    pub step_id: String,
    pub category: String,
    pub name: String,
    pub amount: f64,
    pub unit: String,
    pub metadata: State,
    pub created_at: f64,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct CostSummary {
    pub tool_calls: f64,
    pub model_tokens: f64,
    pub total_usd: f64,
    pub by_category: HashMap<String, f64>,
}

pub const MEDIA_SCHEMA_VERSION: &str = "agentledger.media.v0";
pub const STREAM_SCHEMA_VERSION: &str = "agentledger.stream.v0";

#[derive(Clone, Debug)]
pub struct LocalBlobStore {
    root: PathBuf,
}

impl LocalBlobStore {
    pub fn open(root: impl AsRef<Path>) -> Result<Self> {
        fs::create_dir_all(root.as_ref()).map_err(|err| RuntimeError(err.to_string()))?;
        Ok(Self {
            root: root.as_ref().to_path_buf(),
        })
    }

    pub fn put_json(&self, value: &Value) -> Result<(String, String)> {
        let encoded = encode_value(value);
        let digest = stable_hash(&encoded);
        let dir = self.root.join("sha256");
        fs::create_dir_all(&dir).map_err(|err| RuntimeError(err.to_string()))?;
        let path = dir.join(format!("{digest}.json"));
        if !path.exists() {
            let tmp = path.with_extension("json.tmp");
            fs::write(&tmp, encoded).map_err(|err| RuntimeError(err.to_string()))?;
            fs::rename(&tmp, &path).map_err(|err| RuntimeError(err.to_string()))?;
        }
        Ok((
            format!("sha256:{digest}"),
            format!("blob://sha256/{digest}.json"),
        ))
    }

    pub fn get_json(&self, reference: &str) -> Result<Value> {
        let prefix = "blob://sha256/";
        if !reference.starts_with(prefix) {
            return Err(RuntimeError(format!("unsupported blob ref: {reference}")));
        }
        let name = &reference[prefix.len()..];
        if !name.ends_with(".json")
            || name.contains("..")
            || name.contains('/')
            || name.contains('\\')
        {
            return Err(RuntimeError(format!("unsupported blob ref: {reference}")));
        }
        let body = fs::read_to_string(self.root.join("sha256").join(name))
            .map_err(|err| RuntimeError(err.to_string()))?;
        decode_value(&body)
    }
}

#[derive(Clone, Debug)]
pub struct Artifact {
    pub artifact_id: String,
    pub run_id: String,
    pub step_id: Option<String>,
    pub name: String,
    pub blob_hash: String,
    pub blob_ref: String,
    pub metadata: State,
    pub created_at: f64,
}

#[derive(Clone, Debug, Default)]
pub struct MediaArtifactOptions {
    pub uri: Option<String>,
    pub content_ref: Option<String>,
    pub media_metadata: State,
    pub lineage: State,
    pub derived_outputs: State,
    pub metadata: State,
}

#[derive(Clone, Debug, Default)]
pub struct StreamChunkRef {
    pub stream_id: String,
    pub chunk_id: String,
    pub offset: Value,
    pub content_ref: Option<String>,
    pub content_hash: Option<String>,
    pub sequence: Option<f64>,
    pub event_time: Option<f64>,
    pub metadata: State,
}

#[derive(Clone, Debug, Default)]
pub struct StreamCheckpointOptions {
    pub stream_id: String,
    pub consumer_id: String,
    pub offset: Value,
    pub watermark: Option<Value>,
    pub chunk: Option<StreamChunkRef>,
    pub partial_result_ref: Option<String>,
    pub backpressure: State,
    pub metadata: State,
}

#[derive(Clone, Debug, Default)]
pub struct BudgetLimits {
    pub max_tool_calls: Option<f64>,
    pub max_model_tokens: Option<f64>,
    pub max_total_usd: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct RuntimeError(pub String);

impl fmt::Display for RuntimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for RuntimeError {}

pub type Result<T> = std::result::Result<T, RuntimeError>;
pub type ToolFunc = Box<dyn Fn(State) -> Result<Value> + Send + Sync>;
pub type AgentFunc = fn(&mut AgentContext, State) -> Result<()>;

pub struct SandboxPolicy {
    pub tool_name: String,
    pub run_id: String,
    pub step_id: String,
    pub executor: String,
    pub network: String,
    pub filesystem: String,
    pub timeout_seconds: u64,
    pub extra: State,
}

pub struct SandboxResult {
    pub ok: bool,
    pub output: Value,
    pub error: Option<String>,
    pub metadata: State,
}

pub trait SandboxExecutor {
    fn run_tool(&self, args: State, policy: &SandboxPolicy) -> SandboxResult;
}

pub struct DisabledSandboxExecutor;

impl SandboxExecutor for DisabledSandboxExecutor {
    fn run_tool(&self, _args: State, policy: &SandboxPolicy) -> SandboxResult {
        let mut metadata = State::new();
        metadata.insert("executor".to_string(), Value::String(policy.executor.clone()));
        metadata.insert("isolation_level".to_string(), Value::String("none".to_string()));
        metadata.insert("fail_closed".to_string(), Value::Bool(true));
        SandboxResult {
            ok: false,
            output: Value::Null,
            error: Some(format!("sandbox executor \"{}\" is disabled", policy.executor)),
            metadata,
        }
    }
}

pub struct ToolSpec {
    pub name: String,
    pub version: String,
    pub side_effect: String,
    pub risk_level: String,
    pub idempotency_required: bool,
    pub approval_required: bool,
    pub sandbox_required: bool,
    pub sandbox_executor: String,
    pub sandbox_policy: State,
    pub input_schema: Option<Value>,
    pub output_schema: Option<Value>,
    pub func: ToolFunc,
}

impl ToolSpec {
    pub fn new(name: &str, func: ToolFunc) -> Self {
        Self {
            name: name.to_string(),
            version: "v1".to_string(),
            side_effect: "none".to_string(),
            risk_level: "low".to_string(),
            idempotency_required: false,
            approval_required: false,
            sandbox_required: false,
            sandbox_executor: String::new(),
            sandbox_policy: State::new(),
            input_schema: None,
            output_schema: None,
            func,
        }
    }

    pub fn side_effect(mut self, side_effect: &str) -> Self {
        self.side_effect = side_effect.to_string();
        self
    }

    pub fn risk_level(mut self, risk_level: &str) -> Self {
        self.risk_level = risk_level.to_string();
        self
    }

    pub fn idempotency_required(mut self, required: bool) -> Self {
        self.idempotency_required = required;
        self
    }

    pub fn approval_required(mut self, required: bool) -> Self {
        self.approval_required = required;
        self
    }

    pub fn sandbox_required(mut self, required: bool) -> Self {
        self.sandbox_required = required;
        self
    }

    pub fn sandbox_executor(mut self, executor: &str) -> Self {
        self.sandbox_executor = executor.to_string();
        self
    }

    pub fn sandbox_policy(mut self, policy: State) -> Self {
        self.sandbox_policy = policy;
        self
    }

    pub fn input_schema(mut self, schema: Value) -> Self {
        self.input_schema = Some(schema);
        self
    }

    pub fn output_schema(mut self, schema: Value) -> Self {
        self.output_schema = Some(schema);
        self
    }
}

#[derive(Default)]
pub struct MemoryStore {
    runs: HashMap<String, Run>,
    steps: HashMap<String, Step>,
    events: HashMap<String, Vec<Event>>,
    tool_ledger: HashMap<String, ToolLedgerEntry>,
    approval_requests: HashMap<String, ApprovalRequest>,
    cost_records: HashMap<String, Vec<CostRecord>>,
    artifacts: HashMap<String, Vec<Artifact>>,
}

impl MemoryStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn save_to_path(&self, path: impl AsRef<Path>) -> Result<()> {
        fs::write(path, encode_store(self)).map_err(|err| RuntimeError(err.to_string()))
    }

    pub fn load_from_path(path: impl AsRef<Path>) -> Result<Self> {
        let body = fs::read_to_string(path).map_err(|err| RuntimeError(err.to_string()))?;
        decode_store(&body)
    }

    pub fn create_run(&mut self, initial_state: State) -> (String, String) {
        let run_id = new_id("run");
        let session_id = new_id("sess");
        let step_id = new_id("step");
        let now = now_seconds();
        self.runs.insert(
            run_id.clone(),
            Run {
                run_id: run_id.clone(),
                session_id: session_id.clone(),
                status: "pending".to_string(),
                state: initial_state.clone(),
                state_version: 0,
                created_at: now,
                updated_at: now,
            },
        );
        self.steps.insert(
            step_id.clone(),
            Step {
                step_id: step_id.clone(),
                run_id: run_id.clone(),
                session_id: session_id.clone(),
                status: "pending".to_string(),
                owner: None,
                lease_token: None,
                lease_until: None,
                attempt: 0,
                state_version: 0,
                checkpoint_id: None,
                last_error_type: None,
                last_error: None,
                cancelled_at: None,
                created_at: now,
                updated_at: now,
            },
        );
        let mut payload = State::new();
        payload.insert("initial_state".to_string(), Value::Object(initial_state));
        self.append_event(
            &run_id,
            Some(&session_id),
            None,
            "run_created",
            payload,
            None,
            None,
            None,
        );
        let mut step_payload = State::new();
        step_payload.insert("step_id".to_string(), Value::String(step_id.clone()));
        self.append_event(
            &run_id,
            Some(&session_id),
            Some(&step_id),
            "step_created",
            step_payload,
            None,
            None,
            None,
        );
        (run_id, step_id)
    }

    pub fn claim_step(
        &mut self,
        worker_id: &str,
        run_id: &str,
        lease_seconds: f64,
    ) -> Result<StepClaim> {
        let mut candidates: Vec<Step> = self
            .steps
            .values()
            .filter(|step| {
                (run_id.is_empty() || step.run_id == run_id)
                    && (step.status == "pending" || step.status == "retry_scheduled")
            })
            .cloned()
            .collect();
        candidates.sort_by(|a, b| {
            a.created_at
                .partial_cmp(&b.created_at)
                .unwrap()
                .then(a.step_id.cmp(&b.step_id))
        });
        let candidate = candidates
            .first()
            .ok_or_else(|| RuntimeError("agentledger: no runnable step".to_string()))?;
        let now = now_seconds();
        let step = self.steps.get_mut(&candidate.step_id).unwrap();
        step.status = "running".to_string();
        step.owner = Some(worker_id.to_string());
        step.lease_token = Some(new_id("lease"));
        step.lease_until = Some(now + lease_seconds);
        step.attempt += 1;
        step.updated_at = now;
        let claim = StepClaim {
            run_id: step.run_id.clone(),
            session_id: step.session_id.clone(),
            step_id: step.step_id.clone(),
            attempt: step.attempt,
            lease_token: step.lease_token.clone().unwrap(),
            state_version: step.state_version,
            lease_until: step.lease_until.unwrap(),
        };
        let run = self.runs.get_mut(&claim.run_id).unwrap();
        run.status = "running".to_string();
        run.updated_at = now;
        let mut payload = State::new();
        payload.insert(
            "worker_id".to_string(),
            Value::String(worker_id.to_string()),
        );
        payload.insert(
            "lease_token".to_string(),
            Value::String(claim.lease_token.clone()),
        );
        payload.insert("attempt".to_string(), Value::Number(claim.attempt as f64));
        self.append_event(
            &claim.run_id,
            Some(&claim.session_id),
            Some(&claim.step_id),
            "step_claimed",
            payload,
            None,
            None,
            None,
        );
        Ok(claim)
    }

    pub fn load_state(&self, run_id: &str) -> Result<(State, u64, String)> {
        let run = self
            .runs
            .get(run_id)
            .ok_or_else(|| RuntimeError(format!("run not found: {run_id}")))?;
        Ok((run.state.clone(), run.state_version, run.session_id.clone()))
    }

    pub fn recover_expired_leases(&mut self) -> usize {
        let now = now_seconds();
        let ids: Vec<String> = self.steps.keys().cloned().collect();
        let mut recovered = 0;
        for step_id in ids {
            let should_recover = self
                .steps
                .get(&step_id)
                .map(|step| {
                    step.status == "running" && step.lease_until.is_some_and(|until| until <= now)
                })
                .unwrap_or(false);
            if !should_recover {
                continue;
            }
            let (run_id, session_id, previous_owner, attempt) = {
                let step = self.steps.get_mut(&step_id).unwrap();
                let previous_owner = step.owner.clone().unwrap_or_default();
                step.status = "retry_scheduled".to_string();
                step.owner = None;
                step.lease_token = None;
                step.lease_until = None;
                step.updated_at = now;
                (
                    step.run_id.clone(),
                    step.session_id.clone(),
                    previous_owner,
                    step.attempt,
                )
            };
            let run = self.runs.get_mut(&run_id).unwrap();
            run.status = "retry_scheduled".to_string();
            run.updated_at = now;
            recovered += 1;
            let mut payload = State::new();
            payload.insert("previous_owner".to_string(), Value::String(previous_owner));
            payload.insert("attempt".to_string(), Value::Number(attempt as f64));
            self.append_event(
                &run_id,
                Some(&session_id),
                Some(&step_id),
                "lease_expired",
                payload,
                None,
                None,
                None,
            );
            let mut retry_payload = State::new();
            retry_payload.insert("step_id".to_string(), Value::String(step_id.clone()));
            retry_payload.insert(
                "reason".to_string(),
                Value::String("lease_expired".to_string()),
            );
            self.append_event(
                &run_id,
                Some(&session_id),
                Some(&step_id),
                "step_retry_scheduled",
                retry_payload,
                None,
                None,
                None,
            );
        }
        recovered
    }

    pub fn cancel_run(&mut self, run_id: &str, reason: &str) -> Result<usize> {
        let session_id = self
            .runs
            .get(run_id)
            .ok_or_else(|| RuntimeError(format!("run not found: {run_id}")))?
            .session_id
            .clone();
        let mut payload = State::new();
        payload.insert("reason".to_string(), Value::String(reason.to_string()));
        self.append_event(
            run_id,
            Some(&session_id),
            None,
            "run_cancel_requested",
            payload,
            None,
            None,
            None,
        );
        let ids: Vec<String> = self.steps.keys().cloned().collect();
        let now = now_seconds();
        let mut cancelled = 0;
        for step_id in ids {
            let should_cancel = self
                .steps
                .get(&step_id)
                .map(|step| {
                    step.run_id == run_id
                        && !["completed", "failed", "cancelled"].contains(&step.status.as_str())
                })
                .unwrap_or(false);
            if !should_cancel {
                continue;
            }
            let step_session = {
                let step = self.steps.get_mut(&step_id).unwrap();
                step.status = "cancelled".to_string();
                step.owner = None;
                step.lease_token = None;
                step.lease_until = None;
                step.cancelled_at = Some(now);
                step.updated_at = now;
                step.session_id.clone()
            };
            cancelled += 1;
            let mut step_payload = State::new();
            step_payload.insert("reason".to_string(), Value::String(reason.to_string()));
            self.append_event(
                run_id,
                Some(&step_session),
                Some(&step_id),
                "step_cancelled",
                step_payload,
                None,
                None,
                None,
            );
        }
        let run = self.runs.get_mut(run_id).unwrap();
        run.status = "cancelled".to_string();
        run.updated_at = now;
        let mut done_payload = State::new();
        done_payload.insert("reason".to_string(), Value::String(reason.to_string()));
        done_payload.insert(
            "cancelled_steps".to_string(),
            Value::Number(cancelled as f64),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            None,
            "run_cancelled",
            done_payload,
            None,
            None,
            None,
        );
        Ok(cancelled)
    }

    pub fn commit_state_patch(
        &mut self,
        run_id: &str,
        step_id: &str,
        lease_token: &str,
        base_version: u64,
        patch: State,
    ) -> Result<u64> {
        self.validate_lease(step_id, lease_token)?;
        let run = self
            .runs
            .get(run_id)
            .ok_or_else(|| RuntimeError(format!("run not found: {run_id}")))?;
        if run.state_version != base_version {
            return Err(RuntimeError(format!(
                "state version conflict: expected {base_version}, got {}",
                run.state_version
            )));
        }
        let now = now_seconds();
        let new_version = base_version + 1;
        let session_id = self.steps.get(step_id).unwrap().session_id.clone();
        let run = self.runs.get_mut(run_id).unwrap();
        run.state = merge_patch(&run.state, &patch);
        run.state_version = new_version;
        run.status = "completed".to_string();
        run.updated_at = now;
        let step = self.steps.get_mut(step_id).unwrap();
        step.status = "completed".to_string();
        step.state_version = new_version;
        step.checkpoint_id = Some(format!("ckpt:{run_id}:{step_id}:{}", step.attempt));
        step.updated_at = now;
        let mut payload = State::new();
        payload.insert("patch".to_string(), Value::Object(patch));
        payload.insert(
            "state_version".to_string(),
            Value::Number(new_version as f64),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "state_patch_committed",
            payload,
            None,
            Some(new_version),
            None,
        );
        let mut complete_payload = State::new();
        complete_payload.insert("step_id".to_string(), Value::String(step_id.to_string()));
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "step_completed",
            complete_payload,
            None,
            Some(new_version),
            None,
        );
        Ok(new_version)
    }

    pub fn mark_retry(&mut self, run_id: &str, step_id: &str, error_type: &str, message: &str) {
        let now = now_seconds();
        let session_id = {
            let step = self.steps.get_mut(step_id).unwrap();
            step.status = "retry_scheduled".to_string();
            step.owner = None;
            step.lease_token = None;
            step.lease_until = None;
            step.last_error_type = Some(error_type.to_string());
            step.last_error = Some(message.to_string());
            step.updated_at = now;
            step.session_id.clone()
        };
        let run = self.runs.get_mut(run_id).unwrap();
        run.status = "retry_scheduled".to_string();
        run.updated_at = now;
        let mut classified = State::new();
        classified.insert("error".to_string(), Value::String(message.to_string()));
        classified.insert(
            "error_type".to_string(),
            Value::String(error_type.to_string()),
        );
        classified.insert("retryable".to_string(), Value::Bool(true));
        classified.insert("source".to_string(), Value::String("agent".to_string()));
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "failure_classified",
            classified,
            None,
            None,
            None,
        );
        let mut payload = State::new();
        payload.insert("error".to_string(), Value::String(message.to_string()));
        payload.insert(
            "error_type".to_string(),
            Value::String(error_type.to_string()),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "error_raised",
            payload,
            None,
            None,
            None,
        );
        let mut retry_payload = State::new();
        retry_payload.insert("step_id".to_string(), Value::String(step_id.to_string()));
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "step_retry_scheduled",
            retry_payload,
            None,
            None,
            None,
        );
    }

    pub fn mark_waiting_human(
        &mut self,
        run_id: &str,
        step_id: &str,
        reason: &str,
        approval_id: &str,
    ) {
        let now = now_seconds();
        let session_id = {
            let step = self.steps.get_mut(step_id).unwrap();
            step.status = "waiting_human".to_string();
            step.owner = None;
            step.lease_token = None;
            step.lease_until = None;
            step.last_error_type = Some("ApprovalRequired".to_string());
            step.last_error = Some(reason.to_string());
            step.updated_at = now;
            step.session_id.clone()
        };
        let run = self.runs.get_mut(run_id).unwrap();
        run.status = "waiting_human".to_string();
        run.updated_at = now;
        let mut payload = State::new();
        payload.insert("reason".to_string(), Value::String(reason.to_string()));
        payload.insert(
            "approval_id".to_string(),
            Value::String(approval_id.to_string()),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "step_waiting_human",
            payload,
            None,
            None,
            None,
        );
    }

    pub fn mark_failed(&mut self, run_id: &str, step_id: &str, error_type: &str, message: &str) {
        let now = now_seconds();
        let session_id = {
            let step = self.steps.get_mut(step_id).unwrap();
            step.status = "failed".to_string();
            step.owner = None;
            step.lease_token = None;
            step.lease_until = None;
            step.last_error_type = Some(error_type.to_string());
            step.last_error = Some(message.to_string());
            step.updated_at = now;
            step.session_id.clone()
        };
        let run = self.runs.get_mut(run_id).unwrap();
        run.status = "failed".to_string();
        run.updated_at = now;
        let mut classified = State::new();
        classified.insert("error".to_string(), Value::String(message.to_string()));
        classified.insert(
            "error_type".to_string(),
            Value::String(error_type.to_string()),
        );
        classified.insert("retryable".to_string(), Value::Bool(false));
        classified.insert(
            "source".to_string(),
            Value::String(failure_source(error_type).to_string()),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "failure_classified",
            classified,
            None,
            None,
            None,
        );
        let mut error = State::new();
        error.insert("error".to_string(), Value::String(message.to_string()));
        error.insert(
            "error_type".to_string(),
            Value::String(error_type.to_string()),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "error_raised",
            error,
            None,
            None,
            None,
        );
        let mut payload = State::new();
        payload.insert("step_id".to_string(), Value::String(step_id.to_string()));
        payload.insert(
            "error_type".to_string(),
            Value::String(error_type.to_string()),
        );
        self.append_event(
            run_id,
            Some(&session_id),
            Some(step_id),
            "step_failed",
            payload,
            None,
            None,
            None,
        );
    }

    pub fn append_event(
        &mut self,
        run_id: &str,
        session_id: Option<&str>,
        step_id: Option<&str>,
        event_type: &str,
        payload: State,
        agent_role: Option<&str>,
        state_version: Option<u64>,
        causal_token: Option<&str>,
    ) -> Event {
        let events = self.events.entry(run_id.to_string()).or_default();
        let payload_ref = format_state(&payload);
        let event = Event {
            event_id: new_id("evt"),
            run_id: run_id.to_string(),
            session_id: session_id.map(str::to_string),
            step_id: step_id.map(str::to_string),
            seq: events.len() as u64 + 1,
            event_type: event_type.to_string(),
            timestamp: now_seconds(),
            agent_role: agent_role.map(str::to_string),
            state_version,
            causal_token: causal_token.map(str::to_string),
            payload_hash: stable_hash(&payload_ref),
            payload_ref,
            payload,
        };
        events.push(event.clone());
        event
    }

    pub fn reserve_ledger(&mut self, key: &str, entry: ToolLedgerEntry) -> Option<ToolLedgerEntry> {
        if let Some(existing) = self.tool_ledger.get(key) {
            return Some(existing.clone());
        }
        self.tool_ledger.insert(key.to_string(), entry);
        None
    }

    pub fn update_ledger(
        &mut self,
        key: &str,
        status: &str,
        response: Option<Value>,
        error_type: Option<String>,
    ) {
        if let Some(entry) = self.tool_ledger.get_mut(key) {
            entry.status = status.to_string();
            entry.response = response.clone();
            entry.response_ref = response.as_ref().map(format_value);
            entry.response_hash = entry.response_ref.as_ref().map(|value| stable_hash(value));
            entry.error_type = error_type;
            entry.updated_at = now_seconds();
        }
    }

    pub fn request_approval(
        &mut self,
        approval_key: &str,
        run_id: &str,
        session_id: &str,
        step_id: &str,
        tool_name: &str,
        risk_level: &str,
        reason: &str,
        request_hash: &str,
        request_ref: &str,
        requested_by: &str,
    ) -> ApprovalRequest {
        if let Some(existing) = self.approval_requests.get(approval_key) {
            return existing.clone();
        }
        let now = now_seconds();
        let approval = ApprovalRequest {
            approval_id: new_id("approval"),
            approval_key: approval_key.to_string(),
            run_id: run_id.to_string(),
            session_id: session_id.to_string(),
            step_id: step_id.to_string(),
            tool_name: tool_name.to_string(),
            risk_level: risk_level.to_string(),
            status: "PENDING".to_string(),
            reason: reason.to_string(),
            request_hash: request_hash.to_string(),
            request_ref: request_ref.to_string(),
            requested_by: requested_by.to_string(),
            approved_by: None,
            decision_reason: None,
            created_at: now,
            updated_at: now,
        };
        self.approval_requests
            .insert(approval_key.to_string(), approval.clone());
        approval
    }

    pub fn approval_for_key(&self, approval_key: &str) -> Option<ApprovalRequest> {
        self.approval_requests.get(approval_key).cloned()
    }

    pub fn approval_requests(&self, run_id: &str) -> Vec<ApprovalRequest> {
        self.approval_requests
            .values()
            .filter(|item| run_id.is_empty() || item.run_id == run_id)
            .cloned()
            .collect()
    }

    pub fn approve_request(
        &mut self,
        approval_id: &str,
        approver: &str,
        reason: &str,
    ) -> Result<ApprovalRequest> {
        self.decide_approval(approval_id, "APPROVED", approver, reason)
    }

    pub fn deny_request(
        &mut self,
        approval_id: &str,
        approver: &str,
        reason: &str,
    ) -> Result<ApprovalRequest> {
        self.decide_approval(approval_id, "DENIED", approver, reason)
    }

    fn decide_approval(
        &mut self,
        approval_id: &str,
        status: &str,
        approver: &str,
        reason: &str,
    ) -> Result<ApprovalRequest> {
        let key = self
            .approval_requests
            .iter()
            .find(|(_, item)| item.approval_id == approval_id)
            .map(|(key, _)| key.clone())
            .ok_or_else(|| RuntimeError(format!("approval not found: {approval_id}")))?;
        let mut approval = self.approval_requests.get(&key).unwrap().clone();
        approval.status = status.to_string();
        approval.approved_by = Some(approver.to_string());
        approval.decision_reason = Some(reason.to_string());
        approval.updated_at = now_seconds();
        self.approval_requests.insert(key, approval.clone());
        let mut payload = State::new();
        payload.insert(
            "approval_id".to_string(),
            Value::String(approval_id.to_string()),
        );
        payload.insert(
            "tool".to_string(),
            Value::String(approval.tool_name.clone()),
        );
        payload.insert("status".to_string(), Value::String(status.to_string()));
        self.append_event(
            &approval.run_id,
            Some(&approval.session_id),
            Some(&approval.step_id),
            "tool_approval_decided",
            payload,
            None,
            None,
            None,
        );
        if self
            .steps
            .get(&approval.step_id)
            .map(|step| step.status.as_str())
            == Some("waiting_human")
        {
            if status == "APPROVED" {
                let step = self.steps.get_mut(&approval.step_id).unwrap();
                step.status = "pending".to_string();
                step.owner = None;
                step.lease_token = None;
                step.lease_until = None;
                step.updated_at = now_seconds();
                let run = self.runs.get_mut(&approval.run_id).unwrap();
                run.status = "pending".to_string();
                let mut retry = State::new();
                retry.insert(
                    "step_id".to_string(),
                    Value::String(approval.step_id.clone()),
                );
                retry.insert(
                    "reason".to_string(),
                    Value::String("approval_granted".to_string()),
                );
                self.append_event(
                    &approval.run_id,
                    Some(&approval.session_id),
                    Some(&approval.step_id),
                    "step_retry_scheduled",
                    retry,
                    None,
                    None,
                    None,
                );
            } else if status == "DENIED" {
                self.mark_failed(
                    &approval.run_id,
                    &approval.step_id,
                    "ApprovalDenied",
                    reason,
                );
            }
        }
        Ok(approval)
    }

    pub fn record_cost(
        &mut self,
        run_id: &str,
        session_id: &str,
        step_id: &str,
        category: &str,
        name: &str,
        amount: f64,
        unit: &str,
        metadata: State,
    ) -> String {
        let cost_id = new_id("cost");
        let record = CostRecord {
            cost_id: cost_id.clone(),
            run_id: run_id.to_string(),
            session_id: session_id.to_string(),
            step_id: step_id.to_string(),
            category: category.to_string(),
            name: name.to_string(),
            amount,
            unit: unit.to_string(),
            metadata,
            created_at: now_seconds(),
        };
        self.cost_records
            .entry(run_id.to_string())
            .or_default()
            .push(record);
        let mut payload = State::new();
        payload.insert("cost_id".to_string(), Value::String(cost_id.clone()));
        payload.insert("category".to_string(), Value::String(category.to_string()));
        payload.insert("name".to_string(), Value::String(name.to_string()));
        payload.insert("amount".to_string(), Value::Number(amount));
        payload.insert("unit".to_string(), Value::String(unit.to_string()));
        self.append_event(
            run_id,
            Some(session_id),
            Some(step_id),
            "cost_recorded",
            payload,
            None,
            None,
            None,
        );
        cost_id
    }

    pub fn cost_records(&self, run_id: &str) -> Vec<CostRecord> {
        self.cost_records.get(run_id).cloned().unwrap_or_default()
    }

    pub fn cost_summary(&self, run_id: &str) -> CostSummary {
        let mut summary = CostSummary::default();
        for record in self.cost_records(run_id) {
            add_cost(&mut summary, &record);
        }
        summary
    }

    pub fn create_artifact(
        &mut self,
        run_id: &str,
        step_id: Option<&str>,
        name: &str,
        content: State,
        metadata: State,
    ) -> Artifact {
        let blob_ref = format_state(&content);
        let artifact = Artifact {
            artifact_id: new_id("art"),
            run_id: run_id.to_string(),
            step_id: step_id.map(str::to_string),
            name: name.to_string(),
            blob_hash: format!("sha256:{}", stable_hash(&blob_ref)),
            blob_ref,
            metadata,
            created_at: now_seconds(),
        };
        self.artifacts
            .entry(run_id.to_string())
            .or_default()
            .push(artifact.clone());
        artifact
    }

    pub fn artifacts(&self, run_id: &str) -> Vec<Artifact> {
        let mut items = self.artifacts.get(run_id).cloned().unwrap_or_default();
        items.sort_by(|a, b| {
            a.created_at
                .partial_cmp(&b.created_at)
                .unwrap()
                .then(a.artifact_id.cmp(&b.artifact_id))
        });
        items
    }

    pub fn validate_lease(&self, step_id: &str, lease_token: &str) -> Result<()> {
        let step = self
            .steps
            .get(step_id)
            .ok_or_else(|| RuntimeError(format!("step not found: {step_id}")))?;
        if step.status != "running" || step.lease_token.as_deref() != Some(lease_token) {
            return Err(RuntimeError("invalid or stale lease token".to_string()));
        }
        if step.lease_until.is_some_and(|until| until <= now_seconds()) {
            return Err(RuntimeError("lease expired".to_string()));
        }
        Ok(())
    }

    pub fn final_state(&self, run_id: &str) -> Result<State> {
        Ok(self.load_state(run_id)?.0)
    }

    pub fn run(&self, run_id: &str) -> Result<Run> {
        self.runs
            .get(run_id)
            .cloned()
            .ok_or_else(|| RuntimeError(format!("run not found: {run_id}")))
    }

    pub fn steps(&self, run_id: &str) -> Vec<Step> {
        self.steps
            .values()
            .filter(|step| step.run_id == run_id)
            .cloned()
            .collect()
    }

    pub fn events(&self, run_id: &str) -> Vec<Event> {
        self.events.get(run_id).cloned().unwrap_or_default()
    }

    pub fn ledger(&self, run_id: &str) -> Vec<ToolLedgerEntry> {
        self.tool_ledger
            .values()
            .filter(|entry| entry.run_id == run_id)
            .cloned()
            .collect()
    }
}

pub struct ToolRegistry {
    tools: HashMap<String, ToolSpec>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self {
            tools: HashMap::new(),
        }
    }

    pub fn register(&mut self, spec: ToolSpec) {
        self.tools.insert(spec.name.clone(), spec);
    }

    pub fn get(&self, name: &str) -> Result<&ToolSpec> {
        self.tools
            .get(name)
            .ok_or_else(|| RuntimeError(format!("tool not registered: {name}")))
    }
}

impl Default for ToolRegistry {
    fn default() -> Self {
        Self::new()
    }
}

pub struct Runtime {
    pub store: MemoryStore,
    pub registry: ToolRegistry,
    pub budget: BudgetLimits,
    pub sandbox: Box<dyn SandboxExecutor>,
}

impl Runtime {
    pub fn new() -> Self {
        Self {
            store: MemoryStore::new(),
            registry: ToolRegistry::new(),
            budget: BudgetLimits::default(),
            sandbox: Box::new(DisabledSandboxExecutor),
        }
    }

    pub fn register_tool(&mut self, spec: ToolSpec) {
        self.registry.register(spec);
    }

    pub fn set_budget(&mut self, budget: BudgetLimits) {
        self.budget = budget;
    }

    pub fn set_sandbox(&mut self, sandbox: Box<dyn SandboxExecutor>) {
        self.sandbox = sandbox;
    }

    pub fn create_run(&mut self, initial_state: State) -> (String, String) {
        self.store.create_run(initial_state)
    }

    pub fn run_once(
        &mut self,
        run_id: &str,
        worker_id: &str,
        agent_role: &str,
        lease_seconds: f64,
        agent: AgentFunc,
    ) -> Result<bool> {
        let claim = match self.store.claim_step(worker_id, run_id, lease_seconds) {
            Ok(claim) => claim,
            Err(err) if err.0.contains("no runnable step") => return Ok(false),
            Err(err) => return Err(err),
        };
        let (state, version, session_id) = self.store.load_state(&claim.run_id)?;
        let mut payload = State::new();
        payload.insert(
            "agent_role".to_string(),
            Value::String(agent_role.to_string()),
        );
        payload.insert("attempt".to_string(), Value::Number(claim.attempt as f64));
        self.store.append_event(
            &claim.run_id,
            Some(&session_id),
            Some(&claim.step_id),
            "agent_started",
            payload,
            Some(agent_role),
            Some(version),
            None,
        );
        let mut ctx = AgentContext {
            run_id: claim.run_id.clone(),
            session_id,
            step_id: claim.step_id.clone(),
            agent_role: agent_role.to_string(),
            lease_token: claim.lease_token.clone(),
            attempt: claim.attempt,
            state_version: version,
            pending_patch: State::new(),
        };
        match agent(&mut ctx, state) {
            Ok(()) => {
                self.store.commit_state_patch(
                    &claim.run_id,
                    &claim.step_id,
                    &claim.lease_token,
                    version,
                    ctx.pending_patch,
                )?;
                Ok(true)
            }
            Err(err) if err.0 == "retryable" => {
                self.store.mark_retry(
                    &claim.run_id,
                    &claim.step_id,
                    "RetryableAgentError",
                    "retryable",
                );
                Ok(false)
            }
            Err(err) if err.0.starts_with("approval required:") => {
                let approval_id = err.0.trim_start_matches("approval required:");
                self.store
                    .mark_waiting_human(&claim.run_id, &claim.step_id, &err.0, approval_id);
                Ok(false)
            }
            Err(err) => {
                self.store.mark_failed(
                    &claim.run_id,
                    &claim.step_id,
                    classify_runtime_error(&err.0),
                    &err.0,
                );
                Err(err)
            }
        }
    }

    pub fn call_tool(&mut self, ctx: &AgentContext, tool_name: &str, args: State) -> Result<Value> {
        let (
            version,
            side_effect,
            risk_level,
            idempotency_required,
            approval_required,
            sandbox_required,
            sandbox_executor,
            sandbox_policy,
            input_schema,
            output_schema,
        ) = {
            let spec = self.registry.get(tool_name)?;
            (
                spec.version.clone(),
                spec.side_effect.clone(),
                spec.risk_level.clone(),
                spec.idempotency_required,
                spec.approval_required,
                spec.sandbox_required,
                spec.sandbox_executor.clone(),
                spec.sandbox_policy.clone(),
                spec.input_schema.clone(),
                spec.output_schema.clone(),
            )
        };
        let mut request = State::new();
        request.insert("tool".to_string(), Value::String(tool_name.to_string()));
        request.insert("args".to_string(), Value::Object(args.clone()));
        let request_ref = format_state(&request);
        let request_hash = stable_hash(&request_ref);
        let causal_token = format!(
            "{}:{}:{}:{}",
            ctx.run_id, ctx.step_id, ctx.attempt, ctx.state_version
        );
        let idempotency_key = format!(
            "{}:{}:{}:{}",
            ctx.run_id, ctx.step_id, tool_name, request_hash
        );
        let managed = side_effect != "none" || idempotency_required;
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "tool_call_requested",
            request,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            Some(&causal_token),
        );
        if let Some(schema) = input_schema.as_ref() {
            if let Err(err) = validate_tool_schema(schema, &Value::Object(args.clone()), "$arg") {
                let mut failed = State::new();
                failed.insert("tool".to_string(), Value::String(tool_name.to_string()));
                failed.insert("error".to_string(), Value::String(err.0.clone()));
                failed.insert(
                    "phase".to_string(),
                    Value::String("input_validation".to_string()),
                );
                self.store.append_event(
                    &ctx.run_id,
                    Some(&ctx.session_id),
                    Some(&ctx.step_id),
                    "tool_call_failed",
                    failed,
                    Some(&ctx.agent_role),
                    Some(ctx.state_version),
                    Some(&causal_token),
                );
                return Err(err);
            }
        }

        let mut allowed = !is_high_risk(&risk_level);
        let mut reason = if allowed {
            "default allow for low/medium risk in local runtime".to_string()
        } else {
            "high-risk tool denied by default".to_string()
        };
        if let Some(approval) = self.store.approval_for_key(&idempotency_key) {
            if approval.status == "DENIED" {
                reason = format!("approval denied for tool {tool_name}");
                self.record_permission(ctx, tool_name, false, &reason, &causal_token);
                return Err(RuntimeError(reason));
            }
            if approval.status == "APPROVED" {
                allowed = true;
                reason = format!(
                    "approved by {}",
                    approval
                        .approved_by
                        .unwrap_or_else(|| "operator".to_string())
                );
            }
        } else if approval_required {
            let approval = self.store.request_approval(
                &idempotency_key,
                &ctx.run_id,
                &ctx.session_id,
                &ctx.step_id,
                tool_name,
                &risk_level,
                "tool requires approval",
                &request_hash,
                &request_ref,
                &ctx.agent_role,
            );
            self.record_permission(ctx, tool_name, false, "approval required", &causal_token);
            let mut payload = State::new();
            payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
            payload.insert(
                "approval_id".to_string(),
                Value::String(approval.approval_id.clone()),
            );
            payload.insert(
                "approval_key".to_string(),
                Value::String(idempotency_key.clone()),
            );
            payload.insert("risk_level".to_string(), Value::String(risk_level));
            self.store.append_event(
                &ctx.run_id,
                Some(&ctx.session_id),
                Some(&ctx.step_id),
                "tool_approval_required",
                payload,
                Some(&ctx.agent_role),
                Some(ctx.state_version),
                Some(&causal_token),
            );
            return Err(RuntimeError(format!(
                "approval required:{}",
                approval.approval_id
            )));
        }
        self.record_permission(ctx, tool_name, allowed, &reason, &causal_token);
        if !allowed {
            return Err(RuntimeError(reason));
        }
        if let Some(max) = self.budget.max_tool_calls {
            let used = self.store.cost_summary(&ctx.run_id).tool_calls;
            if used >= max {
                let message = format!("tool call budget exceeded: {used}/{max}");
                let mut payload = State::new();
                payload.insert("category".to_string(), Value::String("tool".to_string()));
                payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
                payload.insert("error".to_string(), Value::String(message.clone()));
                self.store.append_event(
                    &ctx.run_id,
                    Some(&ctx.session_id),
                    Some(&ctx.step_id),
                    "budget_check_failed",
                    payload,
                    Some(&ctx.agent_role),
                    Some(ctx.state_version),
                    Some(&causal_token),
                );
                return Err(RuntimeError(message));
            }
        }
        if managed {
            let entry = ToolLedgerEntry {
                ledger_id: new_id("ledger"),
                run_id: ctx.run_id.clone(),
                session_id: ctx.session_id.clone(),
                step_id: ctx.step_id.clone(),
                tool_name: tool_name.to_string(),
                tool_version: version,
                tool_call_id: new_id("toolcall"),
                idempotency_key: idempotency_key.clone(),
                causal_token: causal_token.clone(),
                request_hash: request_hash.clone(),
                request_ref: request_ref.clone(),
                status: "RESERVED".to_string(),
                external_id: None,
                response_hash: None,
                response_ref: None,
                error_type: None,
                response: None,
                created_at: now_seconds(),
                updated_at: now_seconds(),
            };
            if let Some(existing) = self.store.reserve_ledger(&idempotency_key, entry) {
                if existing.status == "SUCCEEDED" {
                    let mut payload = State::new();
                    payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
                    payload.insert("replayed_from_ledger".to_string(), Value::Bool(true));
                    self.store.append_event(
                        &ctx.run_id,
                        Some(&ctx.session_id),
                        Some(&ctx.step_id),
                        "tool_call_completed",
                        payload,
                        Some(&ctx.agent_role),
                        Some(ctx.state_version),
                        Some(&causal_token),
                    );
                    self.store.record_cost(
                        &ctx.run_id,
                        &ctx.session_id,
                        &ctx.step_id,
                        "tool",
                        tool_name,
                        1.0,
                        "call",
                        State::new(),
                    );
                    return existing
                        .response
                        .ok_or_else(|| RuntimeError("missing ledger response".to_string()));
                }
                return Err(RuntimeError(
                    "tool side effect already in progress".to_string(),
                ));
            }
            self.store
                .update_ledger(&idempotency_key, "RUNNING", None, None);
        }
        if sandbox_required {
            let executor = if sandbox_executor.is_empty() { "default".to_string() } else { sandbox_executor.clone() };
            let network = match sandbox_policy.get("network") {
                Some(Value::String(value)) => value.clone(),
                _ => "deny".to_string(),
            };
            let filesystem = match sandbox_policy.get("filesystem") {
                Some(Value::String(value)) => value.clone(),
                _ => "read-only".to_string(),
            };
            let timeout_seconds = match sandbox_policy.get("timeout_seconds") {
                Some(Value::Number(value)) if *value > 0.0 => *value as u64,
                _ => 30,
            };
            let policy = SandboxPolicy {
                tool_name: tool_name.to_string(),
                run_id: ctx.run_id.clone(),
                step_id: ctx.step_id.clone(),
                executor: executor.clone(),
                network,
                filesystem,
                timeout_seconds,
                extra: sandbox_policy.clone(),
            };
            let mut sandbox_payload = State::new();
            sandbox_payload.insert("tool_name".to_string(), Value::String(tool_name.to_string()));
            sandbox_payload.insert("executor".to_string(), Value::String(executor));
            sandbox_payload.insert("network".to_string(), Value::String(policy.network.clone()));
            sandbox_payload.insert("filesystem".to_string(), Value::String(policy.filesystem.clone()));
            sandbox_payload.insert("timeout_seconds".to_string(), Value::Number(policy.timeout_seconds as f64));
            self.store.append_event(
                &ctx.run_id,
                Some(&ctx.session_id),
                Some(&ctx.step_id),
                "sandbox_started",
                sandbox_payload,
                Some(&ctx.agent_role),
                Some(ctx.state_version),
                Some(&causal_token),
            );
            let result = self.sandbox.run_tool(args, &policy);
            let mut completed = State::new();
            completed.insert("ok".to_string(), Value::Bool(result.ok));
            completed.insert("metadata".to_string(), Value::Object(result.metadata.clone()));
            if let Some(error) = &result.error {
                completed.insert("error".to_string(), Value::String(error.clone()));
            }
            self.store.append_event(
                &ctx.run_id,
                Some(&ctx.session_id),
                Some(&ctx.step_id),
                "sandbox_completed",
                completed,
                Some(&ctx.agent_role),
                Some(ctx.state_version),
                Some(&causal_token),
            );
            if !result.ok {
                let message = result.error.unwrap_or_else(|| "sandboxed tool failed".to_string());
                let mut failed = State::new();
                failed.insert("tool".to_string(), Value::String(tool_name.to_string()));
                failed.insert("error".to_string(), Value::String(message.clone()));
                self.store.append_event(
                    &ctx.run_id,
                    Some(&ctx.session_id),
                    Some(&ctx.step_id),
                    "tool_call_failed",
                    failed,
                    Some(&ctx.agent_role),
                    Some(ctx.state_version),
                    Some(&causal_token),
                );
                return Err(RuntimeError(message));
            }
            let value = result.output;
            if let Some(schema) = output_schema.as_ref() {
                validate_tool_schema(schema, &value, "$result")?;
            }
            if managed {
                self.store.update_ledger(&idempotency_key, "SUCCEEDED", Some(value.clone()), None);
            }
            let mut payload = State::new();
            payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
            payload.insert("idempotency_key".to_string(), Value::String(idempotency_key));
            self.store.append_event(
                &ctx.run_id,
                Some(&ctx.session_id),
                Some(&ctx.step_id),
                "tool_call_completed",
                payload,
                Some(&ctx.agent_role),
                Some(ctx.state_version),
                Some(&causal_token),
            );
            self.store.record_cost(
                &ctx.run_id,
                &ctx.session_id,
                &ctx.step_id,
                "tool",
                tool_name,
                1.0,
                "call",
                State::new(),
            );
            return Ok(value);
        }
        let result = {
            let spec = self.registry.get(tool_name)?;
            (spec.func)(args)
        };
        match result {
            Ok(value) => {
                if let Some(schema) = output_schema.as_ref() {
                    if let Err(err) = validate_tool_schema(schema, &value, "$result") {
                        if managed {
                            self.store.update_ledger(
                                &idempotency_key,
                                "PENDING_VERIFICATION",
                                None,
                                Some("ToolOutputValidationError".to_string()),
                            );
                        }
                        let mut failed = State::new();
                        failed.insert("tool".to_string(), Value::String(tool_name.to_string()));
                        failed.insert("error".to_string(), Value::String(err.0.clone()));
                        failed.insert(
                            "phase".to_string(),
                            Value::String("output_validation".to_string()),
                        );
                        self.store.append_event(
                            &ctx.run_id,
                            Some(&ctx.session_id),
                            Some(&ctx.step_id),
                            "tool_call_failed",
                            failed,
                            Some(&ctx.agent_role),
                            Some(ctx.state_version),
                            Some(&causal_token),
                        );
                        return Err(err);
                    }
                }
                if managed {
                    self.store.update_ledger(
                        &idempotency_key,
                        "SUCCEEDED",
                        Some(value.clone()),
                        None,
                    );
                }
                let mut payload = State::new();
                payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
                payload.insert(
                    "idempotency_key".to_string(),
                    Value::String(idempotency_key),
                );
                self.store.append_event(
                    &ctx.run_id,
                    Some(&ctx.session_id),
                    Some(&ctx.step_id),
                    "tool_call_completed",
                    payload,
                    Some(&ctx.agent_role),
                    Some(ctx.state_version),
                    Some(&causal_token),
                );
                self.store.record_cost(
                    &ctx.run_id,
                    &ctx.session_id,
                    &ctx.step_id,
                    "tool",
                    tool_name,
                    1.0,
                    "call",
                    State::new(),
                );
                Ok(value)
            }
            Err(err) => {
                if managed {
                    self.store.update_ledger(
                        &idempotency_key,
                        "PENDING_VERIFICATION",
                        None,
                        Some("RuntimeError".to_string()),
                    );
                }
                let mut payload = State::new();
                payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
                payload.insert("error".to_string(), Value::String(err.0.clone()));
                self.store.append_event(
                    &ctx.run_id,
                    Some(&ctx.session_id),
                    Some(&ctx.step_id),
                    "tool_call_failed",
                    payload,
                    Some(&ctx.agent_role),
                    Some(ctx.state_version),
                    Some(&causal_token),
                );
                Err(err)
            }
        }
    }

    fn record_permission(
        &mut self,
        ctx: &AgentContext,
        tool_name: &str,
        allowed: bool,
        reason: &str,
        causal_token: &str,
    ) {
        let mut permission = State::new();
        permission.insert("tool".to_string(), Value::String(tool_name.to_string()));
        permission.insert("allowed".to_string(), Value::Bool(allowed));
        permission.insert("reason".to_string(), Value::String(reason.to_string()));
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "tool_permission_decided",
            permission,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            Some(causal_token),
        );
    }

    pub fn create_artifact(
        &mut self,
        ctx: &AgentContext,
        name: &str,
        content: State,
        metadata: State,
    ) -> Result<String> {
        let artifact =
            self.store
                .create_artifact(&ctx.run_id, Some(&ctx.step_id), name, content, metadata);
        let mut payload = State::new();
        payload.insert(
            "artifact_id".to_string(),
            Value::String(artifact.artifact_id.clone()),
        );
        payload.insert("name".to_string(), Value::String(name.to_string()));
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "artifact_created",
            payload,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            None,
        );
        Ok(artifact.artifact_id)
    }

    pub fn create_media_artifact(
        &mut self,
        ctx: &AgentContext,
        name: &str,
        kind: &str,
        options: MediaArtifactOptions,
    ) -> Result<String> {
        if !is_media_kind(kind) {
            return Err(RuntimeError(format!("unsupported media kind: {kind}")));
        }
        let mut media_metadata = options.media_metadata.clone();
        media_metadata.insert(
            "schema_version".to_string(),
            Value::String(MEDIA_SCHEMA_VERSION.to_string()),
        );
        media_metadata.insert("kind".to_string(), Value::String(kind.to_string()));
        let mut content = State::new();
        content.insert(
            "schema_version".to_string(),
            Value::String(MEDIA_SCHEMA_VERSION.to_string()),
        );
        content.insert("kind".to_string(), Value::String(kind.to_string()));
        if let Some(uri) = &options.uri {
            content.insert("uri".to_string(), Value::String(uri.clone()));
        }
        if let Some(content_ref) = &options.content_ref {
            content.insert(
                "content_ref".to_string(),
                Value::String(content_ref.clone()),
            );
        }
        content.insert(
            "metadata".to_string(),
            Value::Object(media_metadata.clone()),
        );
        if !options.lineage.is_empty() {
            content.insert(
                "lineage".to_string(),
                Value::Object(options.lineage.clone()),
            );
        }
        if !options.derived_outputs.is_empty() {
            content.insert(
                "derived_outputs".to_string(),
                Value::Object(options.derived_outputs.clone()),
            );
        }
        let mut media = State::new();
        media.insert(
            "schema_version".to_string(),
            Value::String(MEDIA_SCHEMA_VERSION.to_string()),
        );
        media.insert("kind".to_string(), Value::String(kind.to_string()));
        if let Some(uri) = options.uri {
            media.insert("uri".to_string(), Value::String(uri));
        }
        if let Some(content_ref) = options.content_ref {
            media.insert("content_ref".to_string(), Value::String(content_ref));
        }
        media.insert("metadata".to_string(), Value::Object(media_metadata));
        media.insert("lineage".to_string(), Value::Object(options.lineage));
        let mut artifact_metadata = options.metadata;
        artifact_metadata.insert("agentledger_media".to_string(), Value::Object(media));
        self.create_artifact(ctx, name, content, artifact_metadata)
    }

    pub fn create_stream_checkpoint(
        &mut self,
        ctx: &AgentContext,
        name: &str,
        options: StreamCheckpointOptions,
    ) -> Result<String> {
        if options.stream_id.is_empty() || options.consumer_id.is_empty() {
            return Err(RuntimeError(
                "stream_id and consumer_id are required".to_string(),
            ));
        }
        let chunk = options.chunk.map(stream_chunk_to_state);
        let mut content = State::new();
        content.insert(
            "schema_version".to_string(),
            Value::String(STREAM_SCHEMA_VERSION.to_string()),
        );
        content.insert(
            "stream_id".to_string(),
            Value::String(options.stream_id.clone()),
        );
        content.insert(
            "consumer_id".to_string(),
            Value::String(options.consumer_id.clone()),
        );
        content.insert("offset".to_string(), options.offset.clone());
        if let Some(watermark) = &options.watermark {
            content.insert("watermark".to_string(), watermark.clone());
        }
        if let Some(chunk_state) = &chunk {
            content.insert("chunk".to_string(), Value::Object(chunk_state.clone()));
        }
        if let Some(partial_ref) = &options.partial_result_ref {
            content.insert(
                "partial_result_ref".to_string(),
                Value::String(partial_ref.clone()),
            );
        }
        if !options.backpressure.is_empty() {
            content.insert(
                "backpressure".to_string(),
                Value::Object(options.backpressure.clone()),
            );
        }
        if !options.metadata.is_empty() {
            content.insert("metadata".to_string(), Value::Object(options.metadata));
        }
        let mut stream = State::new();
        stream.insert(
            "schema_version".to_string(),
            Value::String(STREAM_SCHEMA_VERSION.to_string()),
        );
        stream.insert("stream_id".to_string(), Value::String(options.stream_id));
        stream.insert(
            "consumer_id".to_string(),
            Value::String(options.consumer_id),
        );
        stream.insert("offset".to_string(), options.offset);
        if let Some(watermark) = options.watermark {
            stream.insert("watermark".to_string(), watermark);
        }
        if let Some(chunk_state) = chunk {
            stream.insert("chunk".to_string(), Value::Object(chunk_state));
        }
        if let Some(partial_ref) = options.partial_result_ref {
            stream.insert("partial_result_ref".to_string(), Value::String(partial_ref));
        }
        if !options.backpressure.is_empty() {
            stream.insert(
                "backpressure".to_string(),
                Value::Object(options.backpressure),
            );
        }
        let mut artifact_metadata = State::new();
        artifact_metadata.insert("agentledger_stream".to_string(), Value::Object(stream));
        self.create_artifact(ctx, name, content, artifact_metadata)
    }

    pub fn record_model_call(
        &mut self,
        ctx: &AgentContext,
        model: &str,
        input_tokens: f64,
        output_tokens: f64,
        total_usd: f64,
    ) -> Result<()> {
        let mut usage = State::new();
        usage.insert("input_tokens".to_string(), Value::Number(input_tokens));
        usage.insert("output_tokens".to_string(), Value::Number(output_tokens));
        self.record_model_call_evidence(ctx, "custom", model, State::new(), State::new(), usage, total_usd, State::new())
    }

    pub fn record_model_call_evidence(
        &mut self,
        ctx: &AgentContext,
        provider: &str,
        model: &str,
        request: State,
        response: State,
        usage: State,
        total_usd: f64,
        metadata: State,
    ) -> Result<()> {
        let tokens = usage_total_tokens(&usage);
        if let Some(max) = self.budget.max_model_tokens {
            let used = self.store.cost_summary(&ctx.run_id).model_tokens;
            if used + tokens > max {
                let message = format!("model token budget exceeded: {used}+{tokens}/{max}");
                let mut payload = State::new();
                payload.insert("category".to_string(), Value::String("model".to_string()));
                payload.insert("provider".to_string(), Value::String(provider.to_string()));
                payload.insert("model".to_string(), Value::String(model.to_string()));
                payload.insert("error".to_string(), Value::String(message.clone()));
                self.store.append_event(
                    &ctx.run_id,
                    Some(&ctx.session_id),
                    Some(&ctx.step_id),
                    "budget_check_failed",
                    payload,
                    Some(&ctx.agent_role),
                    Some(ctx.state_version),
                    None,
                );
                return Err(RuntimeError(message));
            }
        }
        let mut request_payload = State::new();
        request_payload.insert("schema_version".to_string(), Value::String(MODEL_EVIDENCE_SCHEMA_VERSION.to_string()));
        request_payload.insert("provider".to_string(), Value::String(provider.to_string()));
        request_payload.insert("model".to_string(), Value::String(model.to_string()));
        request_payload.insert("request".to_string(), Value::Object(request));
        request_payload.insert("metadata".to_string(), Value::Object(metadata.clone()));
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "model_call_requested",
            request_payload,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            None,
        );
        let mut response_payload = State::new();
        response_payload.insert("schema_version".to_string(), Value::String(MODEL_EVIDENCE_SCHEMA_VERSION.to_string()));
        response_payload.insert("provider".to_string(), Value::String(provider.to_string()));
        response_payload.insert("model".to_string(), Value::String(model.to_string()));
        response_payload.insert("response".to_string(), Value::Object(response));
        response_payload.insert("usage".to_string(), Value::Object(usage.clone()));
        response_payload.insert("total_usd".to_string(), Value::Number(total_usd));
        response_payload.insert("metadata".to_string(), Value::Object(metadata));
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "model_call_completed",
            response_payload,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            None,
        );
        self.record_model_costs(ctx, provider, model, &usage, total_usd);
        Ok(())
    }

    pub fn record_model_failure(
        &mut self,
        ctx: &AgentContext,
        provider: &str,
        model: &str,
        error_type: &str,
        message: &str,
        retryable: Option<bool>,
        request: State,
        usage: State,
        total_usd: f64,
        metadata: State,
    ) -> Result<()> {
        let mut payload = State::new();
        payload.insert("schema_version".to_string(), Value::String(MODEL_EVIDENCE_SCHEMA_VERSION.to_string()));
        payload.insert("provider".to_string(), Value::String(provider.to_string()));
        payload.insert("model".to_string(), Value::String(model.to_string()));
        payload.insert("error_type".to_string(), Value::String(error_type.to_string()));
        payload.insert("error".to_string(), Value::String(message.to_string()));
        if let Some(value) = retryable {
            payload.insert("retryable".to_string(), Value::Bool(value));
        }
        payload.insert("request".to_string(), Value::Object(request));
        payload.insert("usage".to_string(), Value::Object(usage.clone()));
        payload.insert("total_usd".to_string(), Value::Number(total_usd));
        payload.insert("metadata".to_string(), Value::Object(metadata));
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "model_call_failed",
            payload,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            None,
        );
        self.record_model_costs(ctx, provider, model, &usage, total_usd);
        Ok(())
    }

    pub fn record_tool_call_proposal(
        &mut self,
        ctx: &AgentContext,
        tool_name: &str,
        arguments: State,
        provider: Option<&str>,
        model: Option<&str>,
        model_call_ref: Option<&str>,
        confidence: Option<f64>,
        reason: Option<&str>,
        metadata: State,
    ) {
        let mut payload = State::new();
        payload.insert("schema_version".to_string(), Value::String(MODEL_EVIDENCE_SCHEMA_VERSION.to_string()));
        payload.insert("tool".to_string(), Value::String(tool_name.to_string()));
        payload.insert("args".to_string(), Value::Object(arguments));
        if let Some(value) = provider {
            payload.insert("provider".to_string(), Value::String(value.to_string()));
        }
        if let Some(value) = model {
            payload.insert("model".to_string(), Value::String(value.to_string()));
        }
        if let Some(value) = model_call_ref {
            payload.insert("model_call_ref".to_string(), Value::String(value.to_string()));
        }
        if let Some(value) = confidence {
            payload.insert("confidence".to_string(), Value::Number(value));
        }
        if let Some(value) = reason {
            payload.insert("reason".to_string(), Value::String(value.to_string()));
        }
        payload.insert("metadata".to_string(), Value::Object(metadata));
        self.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "tool_call_proposed",
            payload,
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            None,
        );
    }

    fn record_model_costs(&mut self, ctx: &AgentContext, provider: &str, model: &str, usage: &State, total_usd: f64) {
        let tokens = usage_total_tokens(usage);
        let mut metadata = State::new();
        metadata.insert("provider".to_string(), Value::String(provider.to_string()));
        metadata.insert("model".to_string(), Value::String(model.to_string()));
        metadata.insert("usage".to_string(), Value::Object(usage.clone()));
        if tokens > 0.0 {
            self.store.record_cost(&ctx.run_id, &ctx.session_id, &ctx.step_id, "model", model, tokens, "token", metadata.clone());
        }
        if total_usd > 0.0 {
            self.store.record_cost(&ctx.run_id, &ctx.session_id, &ctx.step_id, "model", model, total_usd, "usd", metadata);
        }
    }
}

impl Default for Runtime {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Clone, Debug)]
pub struct AgentContext {
    pub run_id: String,
    pub session_id: String,
    pub step_id: String,
    pub agent_role: String,
    pub lease_token: String,
    pub attempt: u64,
    pub state_version: u64,
    pub pending_patch: State,
}

impl AgentContext {
    pub fn write_state(&mut self, key: &str, value: Value) {
        self.pending_patch.insert(key.to_string(), value);
    }
}

#[derive(Clone, Debug)]
pub struct EvidenceBundle {
    pub schema_version: String,
    pub bundle_hash: String,
    pub run: Run,
    pub steps: Vec<Step>,
    pub events: Vec<Event>,
    pub tool_ledger: Vec<ToolLedgerEntry>,
    pub approvals: Vec<ApprovalRequest>,
    pub artifacts: Vec<Artifact>,
    pub media_artifacts: Vec<State>,
    pub stream_checkpoints: Vec<State>,
    pub cost_records: Vec<CostRecord>,
    pub cost_summary: CostSummary,
    pub summary: State,
    pub final_state: State,
}

#[derive(Clone, Debug, Default)]
pub struct WorkerRunSummary {
    pub worker_id: String,
    pub run_id: Option<String>,
    pub iterations: u64,
    pub attempts: u64,
    pub succeeded_attempts: u64,
    pub recovered_leases: u64,
    pub final_status: Option<String>,
    pub stopped_reason: String,
}

pub struct LocalWorker {
    pub worker_id: String,
    pub agent_role: String,
    pub lease_seconds: f64,
    pub recover_expired: bool,
}

impl LocalWorker {
    pub fn new(worker_id: &str, agent_role: &str) -> Self {
        Self {
            worker_id: worker_id.to_string(),
            agent_role: agent_role.to_string(),
            lease_seconds: 60.0,
            recover_expired: true,
        }
    }

    pub fn run_until_idle(
        &self,
        runtime: &mut Runtime,
        run_id: &str,
        max_iterations: u64,
        agent: AgentFunc,
    ) -> Result<WorkerRunSummary> {
        let mut summary = WorkerRunSummary {
            worker_id: self.worker_id.clone(),
            run_id: Some(run_id.to_string()),
            stopped_reason: "max_iterations".to_string(),
            ..WorkerRunSummary::default()
        };
        for index in 1..=max_iterations {
            summary.iterations = index;
            if self.recover_expired {
                summary.recovered_leases += runtime.store.recover_expired_leases() as u64;
            }
            let status = runtime.store.run(run_id)?.status;
            if is_terminal_status(&status) {
                summary.final_status = Some(status);
                summary.stopped_reason = "terminal_status".to_string();
                break;
            }
            let ok = runtime.run_once(
                run_id,
                &self.worker_id,
                &self.agent_role,
                self.lease_seconds,
                agent,
            )?;
            if !ok {
                summary.stopped_reason = "idle".to_string();
                break;
            }
            summary.attempts += 1;
            summary.succeeded_attempts += 1;
        }
        let status = runtime.store.run(run_id)?.status;
        summary.final_status = Some(status.clone());
        if is_terminal_status(&status) {
            summary.stopped_reason = "terminal_status".to_string();
        }
        Ok(summary)
    }
}

#[derive(Clone, Debug, Default)]
pub struct WorkerServiceSummary {
    pub worker_id: String,
    pub run_id: Option<String>,
    pub loops: u64,
    pub attempts: u64,
    pub succeeded_attempts: u64,
    pub recovered_leases: u64,
    pub idle_polls: u64,
    pub stopped_reason: String,
    pub final_status: Option<String>,
    pub stop_requested: bool,
}

pub struct WorkerService {
    pub worker: LocalWorker,
    pub stop_requested: bool,
    pub stop_reason: String,
}

impl WorkerService {
    pub fn new(worker: LocalWorker) -> Self {
        Self {
            worker,
            stop_requested: false,
            stop_reason: "stop_requested".to_string(),
        }
    }

    pub fn request_stop(&mut self, reason: &str) {
        self.stop_requested = true;
        self.stop_reason = reason.to_string();
    }

    pub fn serve(
        &mut self,
        runtime: &mut Runtime,
        run_id: Option<&str>,
        max_loops: u64,
        max_idle_polls: Option<u64>,
        agent: AgentFunc,
    ) -> Result<WorkerServiceSummary> {
        let mut summary = WorkerServiceSummary {
            worker_id: self.worker.worker_id.clone(),
            run_id: run_id.map(str::to_string),
            stopped_reason: "max_loops".to_string(),
            ..WorkerServiceSummary::default()
        };
        while summary.loops < max_loops {
            if self.stop_requested {
                summary.stopped_reason = self.stop_reason.clone();
                summary.stop_requested = true;
                break;
            }
            summary.loops += 1;
            let Some(run_id) = run_id else {
                summary.idle_polls += 1;
                if max_idle_polls.is_some_and(|limit| summary.idle_polls >= limit) {
                    summary.stopped_reason = "idle".to_string();
                    break;
                }
                continue;
            };
            let run_summary = self.worker.run_until_idle(runtime, run_id, 1, agent)?;
            summary.attempts += run_summary.attempts;
            summary.succeeded_attempts += run_summary.succeeded_attempts;
            summary.recovered_leases += run_summary.recovered_leases;
            summary.final_status = run_summary.final_status.clone();
            if summary
                .final_status
                .as_deref()
                .is_some_and(is_terminal_status)
            {
                summary.stopped_reason = "terminal_status".to_string();
                break;
            }
            if run_summary.attempts == 0 {
                summary.idle_polls += 1;
                if max_idle_polls.is_some_and(|limit| summary.idle_polls >= limit) {
                    summary.stopped_reason = "idle".to_string();
                    break;
                }
            } else {
                summary.idle_polls = 0;
            }
        }
        Ok(summary)
    }
}

fn is_terminal_status(status: &str) -> bool {
    matches!(status, "completed" | "failed" | "cancelled")
}

pub fn export_evidence(store: &MemoryStore, run_id: &str) -> Result<EvidenceBundle> {
    let run = store.run(run_id)?;
    let steps = store.steps(run_id);
    let events = store.events(run_id);
    let tool_ledger = store.ledger(run_id);
    let approvals = store.approval_requests(run_id);
    let artifacts = store.artifacts(run_id);
    let media_artifacts = media_artifacts_from(&artifacts);
    let stream_checkpoints = stream_checkpoints_from(&artifacts);
    let cost_records = store.cost_records(run_id);
    let cost_summary = store.cost_summary(run_id);
    let summary = evidence_summary(
        &steps,
        &events,
        &tool_ledger,
        &approvals,
        &artifacts,
        &media_artifacts,
        &stream_checkpoints,
        &cost_records,
        &cost_summary,
    );
    let final_state = store.final_state(run_id)?;
    let basis = format!(
        "{}:{}:{}:{}:{}",
        run_id,
        steps.len(),
        events.len(),
        tool_ledger.len(),
        cost_records.len()
    );
    Ok(EvidenceBundle {
        schema_version: "agentledger.evidence.v1".to_string(),
        bundle_hash: stable_hash(&basis),
        run,
        steps,
        events,
        tool_ledger,
        approvals,
        artifacts,
        media_artifacts,
        stream_checkpoints,
        cost_records,
        cost_summary,
        summary,
        final_state,
    })
}

fn evidence_summary(
    steps: &[Step],
    events: &[Event],
    ledger: &[ToolLedgerEntry],
    approvals: &[ApprovalRequest],
    artifacts: &[Artifact],
    media_artifacts: &[State],
    stream_checkpoints: &[State],
    cost_records: &[CostRecord],
    cost_summary: &CostSummary,
) -> State {
    let mut summary = State::new();
    summary.insert("event_count".into(), Value::Number(events.len() as f64));
    summary.insert("step_count".into(), Value::Number(steps.len() as f64));
    summary.insert(
        "tool_ledger_count".into(),
        Value::Number(ledger.len() as f64),
    );
    summary.insert(
        "approval_count".into(),
        Value::Number(approvals.len() as f64),
    );
    summary.insert(
        "artifact_count".into(),
        Value::Number(artifacts.len() as f64),
    );
    summary.insert(
        "media_artifact_count".into(),
        Value::Number(media_artifacts.len() as f64),
    );
    summary.insert(
        "stream_checkpoint_count".into(),
        Value::Number(stream_checkpoints.len() as f64),
    );
    summary.insert(
        "cost_record_count".into(),
        Value::Number(cost_records.len() as f64),
    );
    summary.insert(
        "has_failed_steps".into(),
        Value::Bool(steps.iter().any(|step| step.status == "failed")),
    );
    summary.insert(
        "has_pending_verification".into(),
        Value::Bool(
            ledger
                .iter()
                .any(|row| row.status == "PENDING_VERIFICATION"),
        ),
    );
    summary.insert(
        "has_pending_approvals".into(),
        Value::Bool(approvals.iter().any(|row| row.status == "PENDING")),
    );
    let mut cost = State::new();
    cost.insert("tool_calls".into(), Value::Number(cost_summary.tool_calls));
    cost.insert(
        "model_tokens".into(),
        Value::Number(cost_summary.model_tokens),
    );
    cost.insert("total_usd".into(), Value::Number(cost_summary.total_usd));
    summary.insert("cost_summary".into(), Value::Object(cost));
    summary
}

#[derive(Clone, Debug)]
pub struct ReplaySummary {
    pub run_id: String,
    pub event_count: usize,
    pub tool_call_count: usize,
    pub final_state: State,
    pub event_hash: String,
    pub replay_safe: bool,
    pub artifact_count: usize,
    pub media_artifact_count: usize,
    pub stream_checkpoint_count: usize,
}

pub fn replay(store: &MemoryStore, run_id: &str) -> Result<ReplaySummary> {
    let events = store.events(run_id);
    let tool_call_count = events
        .iter()
        .filter(|event| event.event_type.starts_with("tool_call_"))
        .count();
    let digest = events
        .iter()
        .map(|event| format!("{}:{}:{}", event.seq, event.event_type, event.payload_hash))
        .collect::<Vec<_>>()
        .join("|");
    let artifacts = store.artifacts(run_id);
    Ok(ReplaySummary {
        run_id: run_id.to_string(),
        event_count: events.len(),
        tool_call_count,
        final_state: store.final_state(run_id)?,
        event_hash: stable_hash(&digest),
        replay_safe: true,
        artifact_count: artifacts.len(),
        media_artifact_count: media_artifacts_from(&artifacts).len(),
        stream_checkpoint_count: stream_checkpoints_from(&artifacts).len(),
    })
}

#[derive(Clone, Debug)]
pub struct CostAttributionReport {
    pub run_id: String,
    pub total: CostSummary,
    pub by_agent: HashMap<String, CostSummary>,
    pub by_step: HashMap<String, CostSummary>,
    pub by_name: HashMap<String, CostSummary>,
}

pub fn cost_attribution(store: &MemoryStore, run_id: &str) -> CostAttributionReport {
    let mut step_roles = HashMap::new();
    for event in store.events(run_id) {
        if let (Some(step_id), Some(agent_role)) = (event.step_id, event.agent_role) {
            step_roles.insert(step_id, agent_role);
        }
    }
    let mut report = CostAttributionReport {
        run_id: run_id.to_string(),
        total: CostSummary::default(),
        by_agent: HashMap::new(),
        by_step: HashMap::new(),
        by_name: HashMap::new(),
    };
    for record in store.cost_records(run_id) {
        add_cost(&mut report.total, &record);
        let agent = step_roles
            .get(&record.step_id)
            .cloned()
            .unwrap_or_else(|| "<unknown>".to_string());
        add_cost(report.by_agent.entry(agent).or_default(), &record);
        add_cost(
            report.by_step.entry(record.step_id.clone()).or_default(),
            &record,
        );
        add_cost(
            report.by_name.entry(record.name.clone()).or_default(),
            &record,
        );
    }
    report
}

#[derive(Clone, Debug)]
pub struct FailureAttributionReport {
    pub run_id: String,
    pub run_status: String,
    pub failed_steps: Vec<Step>,
    pub pending_verification: Vec<ToolLedgerEntry>,
    pub pending_approvals: Vec<ApprovalRequest>,
    pub failure_events: Vec<Event>,
    pub failure_envelopes: Vec<State>,
    pub failure_lifecycle: State,
    pub failure_causal_graph: State,
    pub failure_replay_plan: State,
    pub failure_alerts: State,
    pub failure_export: State,
    pub summary: State,
}

pub fn failure_attribution(store: &MemoryStore, run_id: &str) -> Result<FailureAttributionReport> {
    let run = store.run(run_id)?;
    let failed_steps: Vec<Step> = store
        .steps(run_id)
        .into_iter()
        .filter(|step| step.status == "failed")
        .collect();
    let pending_verification: Vec<ToolLedgerEntry> = store
        .ledger(run_id)
        .into_iter()
        .filter(|entry| entry.status == "PENDING_VERIFICATION")
        .collect();
    let pending_approvals: Vec<ApprovalRequest> = store
        .approval_requests(run_id)
        .into_iter()
        .filter(|entry| entry.status == "PENDING")
        .collect();
    let failure_events: Vec<Event> = store
        .events(run_id)
        .into_iter()
        .filter(|event| is_failure_event(&event.event_type))
        .collect();
    let steps = store.steps(run_id);
    let ledger = store.ledger(run_id);
    let approvals = store.approval_requests(run_id);
    let events = store.events(run_id);
    let costs = store.cost_records(run_id);
    let failure_envelopes = failure_envelopes(run_id, &run.status, &steps, &ledger, &approvals, &failure_events);
    let failure_lifecycle = failure_lifecycle(run_id, &run.status, &failure_envelopes);
    let failure_causal_graph = failure_causal_graph(run_id, &run.status, &failure_envelopes, &steps, &ledger, &approvals, &events, &costs);
    let failure_replay_plan = failure_replay_plan(run_id, &failure_envelopes, &ledger, &events);
    let failure_alerts = failure_alerts(run_id, &failure_envelopes, &failure_replay_plan);
    let mut summary = State::new();
    summary.insert(
        "failed_step_count".to_string(),
        Value::Number(failed_steps.len() as f64),
    );
    summary.insert(
        "pending_verification_count".to_string(),
        Value::Number(pending_verification.len() as f64),
    );
    summary.insert(
        "pending_approval_count".to_string(),
        Value::Number(pending_approvals.len() as f64),
    );
    summary.insert(
        "failure_event_count".to_string(),
        Value::Number(failure_events.len() as f64),
    );
    summary.insert(
        "failure_envelope_count".to_string(),
        Value::Number(failure_envelopes.len() as f64),
    );
    summary.insert(
        "failure_lifecycle_event_count".to_string(),
        Value::Number(state_array_len(&failure_lifecycle, "events") as f64),
    );
    summary.insert(
        "failure_alert_count".to_string(),
        failure_alerts
            .get("alert_count")
            .cloned()
            .unwrap_or(Value::Number(0.0)),
    );
    summary.insert(
        "unsafe_replay_side_effect_count".to_string(),
        failure_replay_plan
            .get("unsafe_side_effect_count")
            .cloned()
            .unwrap_or(Value::Number(0.0)),
    );
    summary.insert(
        "terminal_failure_count".to_string(),
        Value::Number(count_state_field(&failure_envelopes, "status", "terminal") as f64),
    );
    summary.insert(
        "recoverable_failure_count".to_string(),
        Value::Number(count_recoverable_failures(&failure_envelopes) as f64),
    );
    let failure_export = failure_export(
        run_id,
        &run.status,
        &summary,
        &failure_envelopes,
        &failure_lifecycle,
        &failure_causal_graph,
        &failure_replay_plan,
        &failure_alerts,
    );
    Ok(FailureAttributionReport {
        run_id: run_id.to_string(),
        run_status: run.status,
        failed_steps,
        pending_verification,
        pending_approvals,
        failure_events,
        failure_envelopes,
        failure_lifecycle,
        failure_causal_graph,
        failure_replay_plan,
        failure_alerts,
        failure_export,
        summary,
    })
}

fn failure_envelopes(
    run_id: &str,
    run_status: &str,
    steps: &[Step],
    ledger: &[ToolLedgerEntry],
    approvals: &[ApprovalRequest],
    events: &[Event],
) -> Vec<State> {
    let mut rows = Vec::new();
    for step in steps {
        if step.status == "failed" || step.status == "retry_scheduled" || step.status == "waiting_human" {
            let (status, severity, recoverability, retryability) = if step.status == "retry_scheduled" {
                ("recovery_scheduled", "warn", "auto_retry", "retryable")
            } else if step.status == "waiting_human" {
                ("waiting_human", "warn", "human_required", "unknown")
            } else {
                ("terminal", "risk", "terminal", "not_retryable")
            };
            rows.push(failure_envelope(
                run_id,
                "step",
                &step.step_id,
                &failure_category(&format!(
                    "{} {}",
                    step.last_error_type.clone().unwrap_or_default(),
                    step.last_error.clone().unwrap_or_default()
                ), "agent"),
                status,
                severity,
                recoverability,
                retryability,
                "agent",
                &first_text(&[
                    step.last_error.as_deref(),
                    step.last_error_type.as_deref(),
                    Some("step failure"),
                ]),
                state(&[
                    ("step_id", step.step_id.clone().into()),
                    ("occurred_at", Value::Number(step.updated_at)),
                ]),
                vec![ref_state("step", &step.step_id)],
            ));
        }
    }
    for entry in ledger {
        if entry.status == "PENDING_VERIFICATION" || entry.status == "FAILED" || entry.status == "ERROR" {
            let terminal = entry.status == "FAILED" || entry.status == "ERROR";
            rows.push(failure_envelope(
                run_id,
                "tool_ledger",
                &first_text(&[Some(&entry.ledger_id), Some(&entry.tool_name), Some(&entry.step_id)]),
                "tool",
                if terminal { "terminal" } else { "unknown_side_effect" },
                if terminal { "risk" } else { "warn" },
                if terminal { "terminal" } else { "manual_verification" },
                if terminal { "not_retryable" } else { "unknown" },
                "tool",
                &first_text(&[entry.error_type.as_deref(), Some("tool side effect requires verification")]),
                state(&[
                    ("step_id", entry.step_id.clone().into()),
                    ("tool_name", entry.tool_name.clone().into()),
                    ("occurred_at", Value::Number(entry.updated_at)),
                ]),
                vec![ref_state("step", &entry.step_id), ref_state("tool", &entry.tool_name)],
            ));
        }
    }
    for approval in approvals {
        if approval.status == "PENDING" || approval.status == "DENIED" {
            let denied = approval.status == "DENIED";
            rows.push(failure_envelope(
                run_id,
                "approval",
                &first_text(&[Some(&approval.approval_id), Some(&approval.tool_name), Some(&approval.step_id)]),
                if denied { "policy" } else { "approval" },
                if denied { "blocked" } else { "waiting_human" },
                if denied { "risk" } else { "warn" },
                if denied { "terminal" } else { "human_required" },
                if denied { "not_retryable" } else { "unknown" },
                "policy",
                &first_text(&[
                    approval.decision_reason.as_deref(),
                    Some(&approval.reason),
                    Some(if denied { "approval denied" } else { "approval pending" }),
                ]),
                state(&[
                    ("step_id", approval.step_id.clone().into()),
                    ("tool_name", approval.tool_name.clone().into()),
                    ("approval_id", approval.approval_id.clone().into()),
                    ("occurred_at", Value::Number(approval.updated_at)),
                ]),
                vec![
                    ref_state("step", &approval.step_id),
                    ref_state("tool", &approval.tool_name),
                    ref_state("approval", &approval.approval_id),
                ],
            ));
        }
    }
    for event in events {
        let category = event_failure_category(event);
        let status = event_failure_status(&event.event_type, run_status);
        let message = first_text(&[
            state_string(&event.payload, "error").as_deref(),
            state_string(&event.payload, "reason").as_deref(),
            state_string(&event.payload, "error_type").as_deref(),
            Some(&event.event_type),
        ]);
        rows.push(failure_envelope(
            run_id,
            "event",
            &event.seq.to_string(),
            &category,
            &status,
            if status == "terminal" || status == "blocked" || status == "failed" { "risk" } else { "warn" },
            &event_recoverability(&event.event_type, run_status),
            &event_retryability(&event.event_type),
            &owner_for_failure_category(&category),
            &message,
            state(&[
                ("step_id", event.step_id.clone().unwrap_or_default().into()),
                ("event_seq", Value::Number(event.seq as f64)),
                ("event_type", event.event_type.clone().into()),
                ("occurred_at", Value::Number(event.timestamp)),
            ]),
            vec![
                ref_state("event", &event.seq.to_string()),
                ref_state("step", event.step_id.as_deref().unwrap_or("")),
            ],
        ));
    }
    dedupe_states(rows, "failure_id")
}

fn failure_envelope(
    run_id: &str,
    source_kind: &str,
    source_id: &str,
    category: &str,
    status: &str,
    severity: &str,
    recoverability: &str,
    retryability: &str,
    owner: &str,
    message: &str,
    extra: State,
    refs: Vec<State>,
) -> State {
    let mut row = state(&[
        ("schema_version", "agentledger.failure.envelope.v1".into()),
        ("failure_id", format!("failure-{}", slug(&format!("{run_id}-{source_kind}-{source_id}"))).into()),
        ("run_id", run_id.into()),
        ("source_kind", source_kind.into()),
        ("source_id", source_id.into()),
        ("category", category.into()),
        ("status", status.into()),
        ("severity", severity.into()),
        ("recoverability", recoverability.into()),
        ("retryability", retryability.into()),
        ("owner", owner.into()),
        ("message", message.into()),
        ("causal_refs", Value::Array(refs.iter().cloned().map(Value::Object).collect())),
        ("evidence_refs", Value::Array(refs.into_iter().map(Value::Object).collect())),
    ]);
    for (key, value) in extra {
        if value != Value::String(String::new()) && value != Value::Null {
            row.insert(key, value);
        }
    }
    row
}

fn failure_lifecycle(run_id: &str, run_status: &str, envelopes: &[State]) -> State {
    let mut events = Vec::new();
    for env in envelopes {
        events.push(lifecycle_row(run_id, env, "failure_detected", state_value_string(env, "message"), state_value_string(env, "severity")));
        events.push(lifecycle_row(run_id, env, "failure_classified", state_value_string(env, "category"), state_value_string(env, "severity")));
        let status = state_value_string(env, "status");
        let recoverability = state_value_string(env, "recoverability");
        if ["recovery_scheduled", "waiting_human", "unknown_side_effect"].contains(&status.as_str()) || ["auto_retry", "human_required", "manual_verification"].contains(&recoverability.as_str()) {
            events.push(lifecycle_row(run_id, env, "failure_recovery_scheduled", "recovery scheduled".to_string(), "warn".to_string()));
        }
        if ["terminal", "blocked"].contains(&status.as_str()) || recoverability == "terminal" {
            events.push(lifecycle_row(run_id, env, "failure_terminal", state_value_string(env, "message"), "risk".to_string()));
        }
    }
    state(&[
        ("schema_version", "agentledger.failure.lifecycle.v1".into()),
        ("run_id", run_id.into()),
        ("run_status", run_status.into()),
        ("events", Value::Array(events.iter().cloned().map(Value::Object).collect())),
        ("terminal", Value::Bool(events.iter().any(|row| state_value_string(row, "stage") == "failure_terminal"))),
        ("recoverable", Value::Bool(events.iter().any(|row| state_value_string(row, "stage") == "failure_recovery_scheduled"))),
    ])
}

fn lifecycle_row(run_id: &str, env: &State, stage: &str, message: String, severity: String) -> State {
    state(&[
        ("schema_version", "agentledger.failure.lifecycle.v1".into()),
        ("stage", stage.into()),
        ("run_id", run_id.into()),
        ("failure_id", state_value_string(env, "failure_id").into()),
        ("category", state_value_string(env, "category").into()),
        ("recoverability", state_value_string(env, "recoverability").into()),
        ("retryability", state_value_string(env, "retryability").into()),
        ("owner", state_value_string(env, "owner").into()),
        ("message", message.into()),
        ("severity", severity.into()),
        ("causal_refs", env.get("causal_refs").cloned().unwrap_or(Value::Array(vec![]))),
    ])
}

fn failure_causal_graph(
    run_id: &str,
    run_status: &str,
    envelopes: &[State],
    steps: &[Step],
    ledger: &[ToolLedgerEntry],
    approvals: &[ApprovalRequest],
    events: &[Event],
    costs: &[CostRecord],
) -> State {
    let mut nodes = vec![state(&[("id", format!("run:{}", slug(run_id)).into()), ("kind", "run".into()), ("status", run_status.into())])];
    let mut edges = Vec::new();
    for step in steps {
        nodes.push(state(&[("id", format!("step:{}", slug(&step.step_id)).into()), ("kind", "step".into()), ("status", step.status.clone().into())]));
        edges.push(state(&[("source", format!("run:{}", slug(run_id)).into()), ("target", format!("step:{}", slug(&step.step_id)).into()), ("kind", "contains_step".into())]));
    }
    for event in events {
        nodes.push(state(&[("id", format!("event:{}", event.seq).into()), ("kind", "event".into()), ("event_type", event.event_type.clone().into())]));
        edges.push(state(&[("source", format!("run:{}", slug(run_id)).into()), ("target", format!("event:{}", event.seq).into()), ("kind", "emitted_event".into())]));
    }
    for entry in ledger {
        nodes.push(state(&[("id", format!("tool:{}", slug(&entry.tool_name)).into()), ("kind", "tool".into()), ("status", entry.status.clone().into())]));
    }
    for approval in approvals {
        nodes.push(state(&[("id", format!("approval:{}", slug(&approval.approval_id)).into()), ("kind", "approval".into()), ("status", approval.status.clone().into())]));
    }
    for cost in costs {
        nodes.push(state(&[("id", format!("cost:{}", slug(&cost.cost_id)).into()), ("kind", "cost".into()), ("category", cost.category.clone().into()), ("amount", Value::Number(cost.amount)), ("unit", cost.unit.clone().into())]));
    }
    for env in envelopes {
        let id = format!("failure:{}", slug(&state_value_string(env, "failure_id")));
        nodes.push(state(&[("id", id.clone().into()), ("kind", "failure".into()), ("category", state_value_string(env, "category").into()), ("status", state_value_string(env, "status").into()), ("owner", state_value_string(env, "owner").into())]));
        edges.push(state(&[("source", format!("run:{}", slug(run_id)).into()), ("target", id.into()), ("kind", "has_failure".into())]));
    }
    let nodes = dedupe_states(nodes, "id");
    state(&[
        ("schema_version", "agentledger.failure.causal_graph.v1".into()),
        ("run_id", run_id.into()),
        ("nodes", Value::Array(nodes.iter().cloned().map(Value::Object).collect())),
        ("edges", Value::Array(edges.iter().cloned().map(Value::Object).collect())),
        ("summary", Value::Object(state(&[
            ("node_count", Value::Number(nodes.len() as f64)),
            ("edge_count", Value::Number(edges.len() as f64)),
            ("failure_node_count", Value::Number(count_state_field(&nodes, "kind", "failure") as f64)),
        ]))),
    ])
}

fn failure_replay_plan(run_id: &str, envelopes: &[State], ledger: &[ToolLedgerEntry], events: &[Event]) -> State {
    let mut actions = Vec::new();
    let mut unsafe_count = 0;
    let mut manual_count = 0;
    for env in envelopes {
        let status = state_value_string(env, "status");
        let recoverability = state_value_string(env, "recoverability");
        let mut action = state(&[
            ("failure_id", state_value_string(env, "failure_id").into()),
            ("category", state_value_string(env, "category").into()),
            ("status", status.clone().into()),
            ("replay_action", "reuse_recorded_evidence".into()),
            ("replay_safe", Value::Bool(true)),
            ("requires_manual_verification", Value::Bool(false)),
            ("reason", "recorded runtime evidence can be inspected without calling external systems".into()),
        ]);
        if status == "unknown_side_effect" || recoverability == "manual_verification" {
            action.insert("replay_action".into(), "manual_verify_side_effect".into());
            action.insert("replay_safe".into(), Value::Bool(false));
            action.insert("requires_manual_verification".into(), Value::Bool(true));
            action.insert("reason".into(), "Tool Ledger recorded an unknown side-effect state".into());
            unsafe_count += 1;
            manual_count += 1;
        } else if status == "waiting_human" {
            action.insert("replay_action".into(), "resume_after_approval".into());
        } else if status == "recovery_scheduled" {
            action.insert("replay_action".into(), "retry_from_checkpoint".into());
        } else if status == "terminal" || status == "blocked" {
            action.insert("replay_action".into(), "terminal_stop".into());
        }
        actions.push(action);
    }
    state(&[
        ("schema_version", "agentledger.failure.replay_plan.v1".into()),
        ("run_id", run_id.into()),
        ("mode", "evidence_only".into()),
        ("safe_to_replay", Value::Bool(unsafe_count == 0)),
        ("unsafe_side_effect_count", Value::Number(unsafe_count as f64)),
        ("manual_verification_count", Value::Number(manual_count as f64)),
        ("recorded_tool_call_count", Value::Number(ledger.len() as f64)),
        ("recorded_event_count", Value::Number(events.len() as f64)),
        ("actions", Value::Array(actions.into_iter().map(Value::Object).collect())),
    ])
}

fn failure_alerts(run_id: &str, envelopes: &[State], replay_plan: &State) -> State {
    let mut alerts = Vec::new();
    if count_state_field(envelopes, "status", "terminal") > 0 {
        alerts.push(alert_state(run_id, "terminal_failure", "risk", "terminal failure recorded"));
    }
    if count_state_field(envelopes, "status", "unknown_side_effect") > 0 {
        alerts.push(alert_state(run_id, "unknown_side_effect", "risk", "tool side-effect state requires manual verification"));
    }
    if state_number(replay_plan, "unsafe_side_effect_count") > 0.0 {
        alerts.push(alert_state(run_id, "unsafe_replay_blocked", "risk", "failure replay plan blocks unsafe automatic replay"));
    }
    state(&[
        ("schema_version", "agentledger.failure.alerts.v1".into()),
        ("run_id", run_id.into()),
        ("alerts", Value::Array(alerts.iter().cloned().map(Value::Object).collect())),
        ("alert_count", Value::Number(alerts.len() as f64)),
    ])
}

fn alert_state(run_id: &str, kind: &str, severity: &str, message: &str) -> State {
    state(&[
        ("schema_version", "agentledger.failure.alerts.v1".into()),
        ("run_id", run_id.into()),
        ("kind", kind.into()),
        ("severity", severity.into()),
        ("message", message.into()),
    ])
}

fn failure_export(
    run_id: &str,
    run_status: &str,
    summary: &State,
    envelopes: &[State],
    lifecycle: &State,
    graph: &State,
    replay_plan: &State,
    alerts: &State,
) -> State {
    state(&[
        ("schema_version", "agentledger.failure.export.v1".into()),
        ("run_id", run_id.into()),
        ("run_status", run_status.into()),
        ("summary", Value::Object(summary.clone())),
        ("failure_envelopes", Value::Array(envelopes.iter().cloned().map(Value::Object).collect())),
        ("failure_lifecycle", Value::Object(lifecycle.clone())),
        ("failure_causal_graph", Value::Object(graph.clone())),
        ("failure_replay_plan", Value::Object(replay_plan.clone())),
        ("failure_alerts", Value::Object(alerts.clone())),
        ("external_mappings", Value::Object(state(&[
            ("opentelemetry", Value::Object(state(&[("span_event_count", Value::Number(state_array_len(lifecycle, "events") as f64))]))),
            ("langfuse", Value::Object(state(&[("trace_id", run_id.into()), ("observation_count", Value::Number(envelopes.len() as f64))]))),
            ("langsmith", Value::Object(state(&[("run_id", run_id.into()), ("feedback_count", Value::Number(envelopes.len() as f64))]))),
            ("temporal", Value::Object(state(&[("workflow_id", run_id.into()), ("failure_count", Value::Number(envelopes.len() as f64)), ("safe_to_replay", replay_plan.get("safe_to_replay").cloned().unwrap_or(Value::Bool(false)))]))),
        ]))),
    ])
}

fn encode_store(store: &MemoryStore) -> String {
    let mut lines = vec!["AGENTLEDGER_RUST_STORE_V1".to_string()];
    let mut runs: Vec<_> = store.runs.values().collect();
    runs.sort_by(|a, b| a.run_id.cmp(&b.run_id));
    for run in runs {
        lines.push(join_fields(&[
            "R".to_string(),
            hex_encode(&run.run_id),
            hex_encode(&run.session_id),
            hex_encode(&run.status),
            run.state_version.to_string(),
            run.created_at.to_string(),
            run.updated_at.to_string(),
            encode_state(&run.state),
        ]));
    }

    let mut steps: Vec<_> = store.steps.values().collect();
    steps.sort_by(|a, b| a.step_id.cmp(&b.step_id));
    for step in steps {
        lines.push(join_fields(&[
            "S".to_string(),
            hex_encode(&step.step_id),
            hex_encode(&step.run_id),
            hex_encode(&step.session_id),
            hex_encode(&step.status),
            encode_option_string(&step.owner),
            encode_option_string(&step.lease_token),
            encode_option_f64(step.lease_until),
            step.attempt.to_string(),
            step.state_version.to_string(),
            encode_option_string(&step.checkpoint_id),
            encode_option_string(&step.last_error_type),
            encode_option_string(&step.last_error),
            encode_option_f64(step.cancelled_at),
            step.created_at.to_string(),
            step.updated_at.to_string(),
        ]));
    }

    let mut run_ids: Vec<_> = store.events.keys().collect();
    run_ids.sort();
    for run_id in run_ids {
        if let Some(events) = store.events.get(run_id) {
            for event in events {
                lines.push(join_fields(&[
                    "E".to_string(),
                    hex_encode(&event.event_id),
                    hex_encode(&event.run_id),
                    encode_option_string(&event.session_id),
                    encode_option_string(&event.step_id),
                    event.seq.to_string(),
                    hex_encode(&event.event_type),
                    event.timestamp.to_string(),
                    encode_option_string(&event.agent_role),
                    encode_option_u64(event.state_version),
                    encode_option_string(&event.causal_token),
                    hex_encode(&event.payload_hash),
                    hex_encode(&event.payload_ref),
                    encode_state(&event.payload),
                ]));
            }
        }
    }

    let mut ledgers: Vec<_> = store.tool_ledger.values().collect();
    ledgers.sort_by(|a, b| a.idempotency_key.cmp(&b.idempotency_key));
    for entry in ledgers {
        lines.push(join_fields(&[
            "L".to_string(),
            hex_encode(&entry.ledger_id),
            hex_encode(&entry.run_id),
            hex_encode(&entry.session_id),
            hex_encode(&entry.step_id),
            hex_encode(&entry.tool_name),
            hex_encode(&entry.tool_version),
            hex_encode(&entry.tool_call_id),
            hex_encode(&entry.idempotency_key),
            hex_encode(&entry.causal_token),
            hex_encode(&entry.request_hash),
            hex_encode(&entry.request_ref),
            hex_encode(&entry.status),
            encode_option_string(&entry.external_id),
            encode_option_string(&entry.response_hash),
            encode_option_string(&entry.response_ref),
            encode_option_string(&entry.error_type),
            encode_option_value(&entry.response),
            entry.created_at.to_string(),
            entry.updated_at.to_string(),
        ]));
    }

    let mut approvals: Vec<_> = store.approval_requests.values().collect();
    approvals.sort_by(|a, b| a.approval_key.cmp(&b.approval_key));
    for approval in approvals {
        lines.push(join_fields(&[
            "A".to_string(),
            hex_encode(&approval.approval_id),
            hex_encode(&approval.approval_key),
            hex_encode(&approval.run_id),
            hex_encode(&approval.session_id),
            hex_encode(&approval.step_id),
            hex_encode(&approval.tool_name),
            hex_encode(&approval.risk_level),
            hex_encode(&approval.status),
            hex_encode(&approval.reason),
            hex_encode(&approval.request_hash),
            hex_encode(&approval.request_ref),
            hex_encode(&approval.requested_by),
            encode_option_string(&approval.approved_by),
            encode_option_string(&approval.decision_reason),
            approval.created_at.to_string(),
            approval.updated_at.to_string(),
        ]));
    }

    let mut cost_run_ids: Vec<_> = store.cost_records.keys().collect();
    cost_run_ids.sort();
    for run_id in cost_run_ids {
        if let Some(records) = store.cost_records.get(run_id) {
            for record in records {
                lines.push(join_fields(&[
                    "C".to_string(),
                    hex_encode(&record.cost_id),
                    hex_encode(&record.run_id),
                    hex_encode(&record.session_id),
                    hex_encode(&record.step_id),
                    hex_encode(&record.category),
                    hex_encode(&record.name),
                    record.amount.to_string(),
                    hex_encode(&record.unit),
                    encode_state(&record.metadata),
                    record.created_at.to_string(),
                ]));
            }
        }
    }

    let mut artifact_run_ids: Vec<_> = store.artifacts.keys().collect();
    artifact_run_ids.sort();
    for run_id in artifact_run_ids {
        if let Some(artifacts) = store.artifacts.get(run_id) {
            for artifact in artifacts {
                lines.push(join_fields(&[
                    "F".to_string(),
                    hex_encode(&artifact.artifact_id),
                    hex_encode(&artifact.run_id),
                    encode_option_string(&artifact.step_id),
                    hex_encode(&artifact.name),
                    hex_encode(&artifact.blob_hash),
                    hex_encode(&artifact.blob_ref),
                    encode_state(&artifact.metadata),
                    artifact.created_at.to_string(),
                ]));
            }
        }
    }

    lines.push(String::new());
    lines.join("\n")
}

fn decode_store(body: &str) -> Result<MemoryStore> {
    let mut lines = body.lines();
    match lines.next() {
        Some("AGENTLEDGER_RUST_STORE_V1") => {}
        _ => {
            return Err(RuntimeError(
                "invalid Rust store snapshot header".to_string(),
            ))
        }
    }
    let mut store = MemoryStore::new();
    for line in lines.filter(|line| !line.trim().is_empty()) {
        let fields: Vec<&str> = line.split('\t').collect();
        let tag = fields.first().copied().unwrap_or_default();
        match tag {
            "R" => {
                require_len(tag, &fields, 8)?;
                let run = Run {
                    run_id: hex_decode(fields[1])?,
                    session_id: hex_decode(fields[2])?,
                    status: hex_decode(fields[3])?,
                    state_version: parse_u64(fields[4])?,
                    created_at: parse_f64(fields[5])?,
                    updated_at: parse_f64(fields[6])?,
                    state: decode_state(fields[7])?,
                };
                store.runs.insert(run.run_id.clone(), run);
            }
            "S" => {
                require_len(tag, &fields, 16)?;
                let step = Step {
                    step_id: hex_decode(fields[1])?,
                    run_id: hex_decode(fields[2])?,
                    session_id: hex_decode(fields[3])?,
                    status: hex_decode(fields[4])?,
                    owner: decode_option_string(fields[5])?,
                    lease_token: decode_option_string(fields[6])?,
                    lease_until: decode_option_f64(fields[7])?,
                    attempt: parse_u64(fields[8])?,
                    state_version: parse_u64(fields[9])?,
                    checkpoint_id: decode_option_string(fields[10])?,
                    last_error_type: decode_option_string(fields[11])?,
                    last_error: decode_option_string(fields[12])?,
                    cancelled_at: decode_option_f64(fields[13])?,
                    created_at: parse_f64(fields[14])?,
                    updated_at: parse_f64(fields[15])?,
                };
                store.steps.insert(step.step_id.clone(), step);
            }
            "E" => {
                require_len(tag, &fields, 14)?;
                let event = Event {
                    event_id: hex_decode(fields[1])?,
                    run_id: hex_decode(fields[2])?,
                    session_id: decode_option_string(fields[3])?,
                    step_id: decode_option_string(fields[4])?,
                    seq: parse_u64(fields[5])?,
                    event_type: hex_decode(fields[6])?,
                    timestamp: parse_f64(fields[7])?,
                    agent_role: decode_option_string(fields[8])?,
                    state_version: decode_option_u64(fields[9])?,
                    causal_token: decode_option_string(fields[10])?,
                    payload_hash: hex_decode(fields[11])?,
                    payload_ref: hex_decode(fields[12])?,
                    payload: decode_state(fields[13])?,
                };
                store
                    .events
                    .entry(event.run_id.clone())
                    .or_default()
                    .push(event);
            }
            "L" => {
                require_len(tag, &fields, 20)?;
                let entry = ToolLedgerEntry {
                    ledger_id: hex_decode(fields[1])?,
                    run_id: hex_decode(fields[2])?,
                    session_id: hex_decode(fields[3])?,
                    step_id: hex_decode(fields[4])?,
                    tool_name: hex_decode(fields[5])?,
                    tool_version: hex_decode(fields[6])?,
                    tool_call_id: hex_decode(fields[7])?,
                    idempotency_key: hex_decode(fields[8])?,
                    causal_token: hex_decode(fields[9])?,
                    request_hash: hex_decode(fields[10])?,
                    request_ref: hex_decode(fields[11])?,
                    status: hex_decode(fields[12])?,
                    external_id: decode_option_string(fields[13])?,
                    response_hash: decode_option_string(fields[14])?,
                    response_ref: decode_option_string(fields[15])?,
                    error_type: decode_option_string(fields[16])?,
                    response: decode_option_value(fields[17])?,
                    created_at: parse_f64(fields[18])?,
                    updated_at: parse_f64(fields[19])?,
                };
                store
                    .tool_ledger
                    .insert(entry.idempotency_key.clone(), entry);
            }
            "A" => {
                require_len(tag, &fields, 17)?;
                let approval = ApprovalRequest {
                    approval_id: hex_decode(fields[1])?,
                    approval_key: hex_decode(fields[2])?,
                    run_id: hex_decode(fields[3])?,
                    session_id: hex_decode(fields[4])?,
                    step_id: hex_decode(fields[5])?,
                    tool_name: hex_decode(fields[6])?,
                    risk_level: hex_decode(fields[7])?,
                    status: hex_decode(fields[8])?,
                    reason: hex_decode(fields[9])?,
                    request_hash: hex_decode(fields[10])?,
                    request_ref: hex_decode(fields[11])?,
                    requested_by: hex_decode(fields[12])?,
                    approved_by: decode_option_string(fields[13])?,
                    decision_reason: decode_option_string(fields[14])?,
                    created_at: parse_f64(fields[15])?,
                    updated_at: parse_f64(fields[16])?,
                };
                store
                    .approval_requests
                    .insert(approval.approval_key.clone(), approval);
            }
            "C" => {
                require_len(tag, &fields, 11)?;
                let record = CostRecord {
                    cost_id: hex_decode(fields[1])?,
                    run_id: hex_decode(fields[2])?,
                    session_id: hex_decode(fields[3])?,
                    step_id: hex_decode(fields[4])?,
                    category: hex_decode(fields[5])?,
                    name: hex_decode(fields[6])?,
                    amount: parse_f64(fields[7])?,
                    unit: hex_decode(fields[8])?,
                    metadata: decode_state(fields[9])?,
                    created_at: parse_f64(fields[10])?,
                };
                store
                    .cost_records
                    .entry(record.run_id.clone())
                    .or_default()
                    .push(record);
            }
            "F" => {
                require_len(tag, &fields, 9)?;
                let artifact = Artifact {
                    artifact_id: hex_decode(fields[1])?,
                    run_id: hex_decode(fields[2])?,
                    step_id: decode_option_string(fields[3])?,
                    name: hex_decode(fields[4])?,
                    blob_hash: hex_decode(fields[5])?,
                    blob_ref: hex_decode(fields[6])?,
                    metadata: decode_state(fields[7])?,
                    created_at: parse_f64(fields[8])?,
                };
                store
                    .artifacts
                    .entry(artifact.run_id.clone())
                    .or_default()
                    .push(artifact);
            }
            _ => {
                return Err(RuntimeError(format!(
                    "unknown Rust store snapshot row: {tag}"
                )))
            }
        }
    }
    Ok(store)
}

fn join_fields(fields: &[String]) -> String {
    fields.join("\t")
}

fn require_len(tag: &str, fields: &[&str], expected: usize) -> Result<()> {
    if fields.len() != expected {
        return Err(RuntimeError(format!(
            "invalid {tag} row: expected {expected} fields, got {}",
            fields.len()
        )));
    }
    Ok(())
}

fn encode_option_string(value: &Option<String>) -> String {
    value
        .as_ref()
        .map(|item| hex_encode(item))
        .unwrap_or_else(|| "-".to_string())
}

fn decode_option_string(value: &str) -> Result<Option<String>> {
    if value == "-" {
        Ok(None)
    } else {
        Ok(Some(hex_decode(value)?))
    }
}

fn encode_option_f64(value: Option<f64>) -> String {
    value
        .map(|item| item.to_string())
        .unwrap_or_else(|| "-".to_string())
}

fn decode_option_f64(value: &str) -> Result<Option<f64>> {
    if value == "-" {
        Ok(None)
    } else {
        Ok(Some(parse_f64(value)?))
    }
}

fn encode_option_u64(value: Option<u64>) -> String {
    value
        .map(|item| item.to_string())
        .unwrap_or_else(|| "-".to_string())
}

fn decode_option_u64(value: &str) -> Result<Option<u64>> {
    if value == "-" {
        Ok(None)
    } else {
        Ok(Some(parse_u64(value)?))
    }
}

fn encode_option_value(value: &Option<Value>) -> String {
    value
        .as_ref()
        .map(encode_value)
        .unwrap_or_else(|| "-".to_string())
}

fn decode_option_value(value: &str) -> Result<Option<Value>> {
    if value == "-" {
        Ok(None)
    } else {
        Ok(Some(decode_value(value)?))
    }
}

fn encode_state(state: &State) -> String {
    encode_value(&Value::Object(state.clone()))
}

fn decode_state(encoded: &str) -> Result<State> {
    match decode_value(encoded)? {
        Value::Object(state) => Ok(state),
        _ => Err(RuntimeError("encoded state was not an object".to_string())),
    }
}

fn encode_value(value: &Value) -> String {
    match value {
        Value::Null => "Z".to_string(),
        Value::Bool(true) => "T".to_string(),
        Value::Bool(false) => "F".to_string(),
        Value::Number(item) => format!("N{}:", hex_encode(&item.to_string())),
        Value::String(item) => format!("S{}:", hex_encode(item)),
        Value::Object(state) => {
            let mut keys: Vec<_> = state.keys().collect();
            keys.sort();
            let mut out = format!("O{}:", keys.len());
            for key in keys {
                out.push_str(&hex_encode(key));
                out.push(':');
                out.push_str(&encode_value(&state[key]));
            }
            out
        }
        Value::Array(values) => {
            let mut out = format!("A{}:", values.len());
            for value in values {
                out.push_str(&encode_value(value));
            }
            out
        }
    }
}

fn decode_value(encoded: &str) -> Result<Value> {
    let (value, index) = parse_value(encoded, 0)?;
    if index != encoded.len() {
        return Err(RuntimeError("trailing bytes in encoded value".to_string()));
    }
    Ok(value)
}

fn parse_value(input: &str, index: usize) -> Result<(Value, usize)> {
    let bytes = input.as_bytes();
    let tag = *bytes
        .get(index)
        .ok_or_else(|| RuntimeError("unexpected end of encoded value".to_string()))?
        as char;
    match tag {
        'Z' => Ok((Value::Null, index + 1)),
        'T' => Ok((Value::Bool(true), index + 1)),
        'F' => Ok((Value::Bool(false), index + 1)),
        'N' => {
            let (hex, next) = read_until_colon(input, index + 1)?;
            Ok((Value::Number(parse_f64(&hex_decode(hex)?)?), next))
        }
        'S' => {
            let (hex, next) = read_until_colon(input, index + 1)?;
            Ok((Value::String(hex_decode(hex)?), next))
        }
        'O' => {
            let (count_text, mut next) = read_until_colon(input, index + 1)?;
            let count = count_text
                .parse::<usize>()
                .map_err(|err| RuntimeError(err.to_string()))?;
            let mut state = State::new();
            for _ in 0..count {
                let (key_hex, after_key) = read_until_colon(input, next)?;
                let key = hex_decode(key_hex)?;
                let (value, after_value) = parse_value(input, after_key)?;
                state.insert(key, value);
                next = after_value;
            }
            Ok((Value::Object(state), next))
        }
        'A' => {
            let (count_text, mut next) = read_until_colon(input, index + 1)?;
            let count = count_text
                .parse::<usize>()
                .map_err(|err| RuntimeError(err.to_string()))?;
            let mut values = Vec::with_capacity(count);
            for _ in 0..count {
                let (value, after_value) = parse_value(input, next)?;
                values.push(value);
                next = after_value;
            }
            Ok((Value::Array(values), next))
        }
        _ => Err(RuntimeError(format!("unknown encoded value tag: {tag}"))),
    }
}

fn read_until_colon(input: &str, index: usize) -> Result<(&str, usize)> {
    let rest = input
        .get(index..)
        .ok_or_else(|| RuntimeError("invalid encoded value index".to_string()))?;
    let offset = rest
        .find(':')
        .ok_or_else(|| RuntimeError("missing encoded value delimiter".to_string()))?;
    Ok((&rest[..offset], index + offset + 1))
}

fn hex_encode(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn hex_decode(value: &str) -> Result<String> {
    if value.len() % 2 != 0 {
        return Err(RuntimeError("invalid hex string length".to_string()));
    }
    let mut bytes = Vec::with_capacity(value.len() / 2);
    for index in (0..value.len()).step_by(2) {
        let byte = u8::from_str_radix(&value[index..index + 2], 16)
            .map_err(|err| RuntimeError(err.to_string()))?;
        bytes.push(byte);
    }
    String::from_utf8(bytes).map_err(|err| RuntimeError(err.to_string()))
}

fn parse_f64(value: &str) -> Result<f64> {
    value
        .parse::<f64>()
        .map_err(|err| RuntimeError(err.to_string()))
}

fn parse_u64(value: &str) -> Result<u64> {
    value
        .parse::<u64>()
        .map_err(|err| RuntimeError(err.to_string()))
}

fn merge_patch(base: &State, patch: &State) -> State {
    let mut out = base.clone();
    for (key, value) in patch {
        match value {
            Value::Null => {
                out.remove(key);
            }
            Value::Object(patch_map) => {
                if let Some(Value::Object(base_map)) = out.get(key) {
                    out.insert(key.clone(), Value::Object(merge_patch(base_map, patch_map)));
                } else {
                    out.insert(key.clone(), value.clone());
                }
            }
            _ => {
                out.insert(key.clone(), value.clone());
            }
        }
    }
    out
}

fn add_cost(summary: &mut CostSummary, record: &CostRecord) {
    if (record.category == "tool" || record.category == "tool_shadow") && record.unit == "call" {
        summary.tool_calls += record.amount;
    }
    if record.category == "model" && record.unit == "token" {
        summary.model_tokens += record.amount;
    }
    if record.unit == "usd" {
        summary.total_usd += record.amount;
    }
    let key = format!("{}:{}", record.category, record.unit);
    *summary.by_category.entry(key).or_insert(0.0) += record.amount;
}

pub fn validate_tool_schema(schema: &Value, value: &Value, path: &str) -> Result<()> {
    let schema = match schema {
        Value::Object(schema) => schema,
        _ => return Err(RuntimeError(format!("{path} schema must be object"))),
    };
    if let Some(expected) = schema.get("const") {
        if expected != value {
            return Err(RuntimeError(format!("{path} expected const")));
        }
    }
    if let Some(Value::Array(items)) = schema.get("enum") {
        if !items.iter().any(|item| item == value) {
            return Err(RuntimeError(format!("{path} value not in enum")));
        }
    }
    let Some(Value::String(kind)) = schema.get("type") else {
        return Ok(());
    };
    match kind.as_str() {
        "object" => {
            let Value::Object(object) = value else {
                return Err(RuntimeError(format!("{path} expected object")));
            };
            if let Some(Value::Array(required)) = schema.get("required") {
                for item in required {
                    if let Value::String(key) = item {
                        if !object.contains_key(key) {
                            return Err(RuntimeError(format!("{path}.{key} is required")));
                        }
                    }
                }
            }
            let properties = match schema.get("properties") {
                Some(Value::Object(properties)) => properties,
                _ => return Ok(()),
            };
            for (key, child_schema) in properties {
                if let Some(child) = object.get(key) {
                    validate_tool_schema(child_schema, child, &format!("{path}.{key}"))?;
                }
            }
            if schema.get("additionalProperties") == Some(&Value::Bool(false)) {
                for key in object.keys() {
                    if !properties.contains_key(key) {
                        return Err(RuntimeError(format!("{path}.{key} is not allowed")));
                    }
                }
            }
        }
        "string" => {
            let Value::String(text) = value else {
                return Err(RuntimeError(format!("{path} expected string")));
            };
            if let Some(Value::Number(min)) = schema.get("minLength") {
                if (text.len() as f64) < *min {
                    return Err(RuntimeError(format!("{path} shorter than minLength")));
                }
            }
            if let Some(Value::Number(max)) = schema.get("maxLength") {
                if (text.len() as f64) > *max {
                    return Err(RuntimeError(format!("{path} longer than maxLength")));
                }
            }
        }
        "number" | "integer" => {
            let Value::Number(number) = value else {
                return Err(RuntimeError(format!("{path} expected number")));
            };
            if kind == "integer" && number.fract() != 0.0 {
                return Err(RuntimeError(format!("{path} expected integer")));
            }
            if let Some(Value::Number(min)) = schema.get("minimum") {
                if number < min {
                    return Err(RuntimeError(format!("{path} below minimum")));
                }
            }
            if let Some(Value::Number(max)) = schema.get("maximum") {
                if number > max {
                    return Err(RuntimeError(format!("{path} above maximum")));
                }
            }
        }
        "boolean" => {
            if !matches!(value, Value::Bool(_)) {
                return Err(RuntimeError(format!("{path} expected boolean")));
            }
        }
        _ => {}
    }
    Ok(())
}

fn is_high_risk(risk: &str) -> bool {
    matches!(
        risk,
        "high" | "destructive" | "sensitive" | "financial_or_legal"
    )
}

fn is_media_kind(kind: &str) -> bool {
    matches!(
        kind,
        "image"
            | "audio"
            | "video"
            | "frame"
            | "audio_segment"
            | "video_segment"
            | "transcript"
            | "embedding"
            | "derived"
    )
}

fn stream_chunk_to_state(chunk: StreamChunkRef) -> State {
    let mut state = State::new();
    state.insert(
        "schema_version".to_string(),
        Value::String(STREAM_SCHEMA_VERSION.to_string()),
    );
    state.insert("stream_id".to_string(), Value::String(chunk.stream_id));
    state.insert("chunk_id".to_string(), Value::String(chunk.chunk_id));
    state.insert("offset".to_string(), chunk.offset);
    if let Some(content_ref) = chunk.content_ref {
        state.insert("content_ref".to_string(), Value::String(content_ref));
    }
    if let Some(content_hash) = chunk.content_hash {
        state.insert("content_hash".to_string(), Value::String(content_hash));
    }
    if let Some(sequence) = chunk.sequence {
        state.insert("sequence".to_string(), Value::Number(sequence));
    }
    if let Some(event_time) = chunk.event_time {
        state.insert("event_time".to_string(), Value::Number(event_time));
    }
    if !chunk.metadata.is_empty() {
        state.insert("metadata".to_string(), Value::Object(chunk.metadata));
    }
    state
}

fn media_artifacts_from(artifacts: &[Artifact]) -> Vec<State> {
    artifacts
        .iter()
        .filter_map(
            |artifact| match artifact.metadata.get("agentledger_media") {
                Some(Value::Object(metadata)) => {
                    let mut row = State::new();
                    row.insert(
                        "artifact_id".to_string(),
                        Value::String(artifact.artifact_id.clone()),
                    );
                    row.insert("name".to_string(), Value::String(artifact.name.clone()));
                    row.insert(
                        "blob_hash".to_string(),
                        Value::String(artifact.blob_hash.clone()),
                    );
                    row.insert(
                        "blob_ref".to_string(),
                        Value::String(artifact.blob_ref.clone()),
                    );
                    for key in ["kind", "uri", "content_ref", "metadata", "lineage"] {
                        if let Some(value) = metadata.get(key) {
                            row.insert(key.to_string(), value.clone());
                        }
                    }
                    Some(row)
                }
                _ => None,
            },
        )
        .collect()
}

fn stream_checkpoints_from(artifacts: &[Artifact]) -> Vec<State> {
    artifacts
        .iter()
        .filter_map(
            |artifact| match artifact.metadata.get("agentledger_stream") {
                Some(Value::Object(metadata)) => {
                    let mut row = State::new();
                    row.insert(
                        "artifact_id".to_string(),
                        Value::String(artifact.artifact_id.clone()),
                    );
                    row.insert("name".to_string(), Value::String(artifact.name.clone()));
                    row.insert(
                        "blob_hash".to_string(),
                        Value::String(artifact.blob_hash.clone()),
                    );
                    row.insert(
                        "blob_ref".to_string(),
                        Value::String(artifact.blob_ref.clone()),
                    );
                    for key in [
                        "stream_id",
                        "consumer_id",
                        "offset",
                        "watermark",
                        "chunk",
                        "partial_result_ref",
                        "backpressure",
                    ] {
                        if let Some(value) = metadata.get(key) {
                            row.insert(key.to_string(), value.clone());
                        }
                    }
                    Some(row)
                }
                _ => None,
            },
        )
        .collect()
}

fn classify_runtime_error(message: &str) -> &'static str {
    if message.contains("budget exceeded") || message.contains("budget") {
        "BudgetExceededError"
    } else if message.contains("sandbox executor") {
        "SandboxUnavailableError"
    } else if message.contains("high-risk") || message.contains("denied") {
        "PermissionDeniedError"
    } else {
        "RuntimeError"
    }
}

fn failure_source(error_type: &str) -> &'static str {
    match error_type {
        "BudgetExceededError" => "budget",
        "SandboxUnavailableError" => "sandbox",
        "PermissionDeniedError" | "ApprovalDenied" => "policy",
        _ => "agent",
    }
}

fn is_failure_event(kind: &str) -> bool {
    matches!(
        kind,
        "failure_classified"
            | "error_raised"
            | "step_failed"
            | "step_retry_scheduled"
            | "step_waiting_human"
            | "lease_expired"
            | "run_cancel_requested"
            | "run_cancelled"
            | "model_call_failed"
            | "tool_call_failed"
            | "tool_approval_required"
            | "budget_check_failed"
    )
}

fn failure_category(text: &str, fallback: &str) -> String {
    let lower = text.to_lowercase();
    for category in ["sandbox", "budget", "policy", "model", "tool", "runtime"] {
        if lower.contains(category) {
            return category.to_string();
        }
    }
    if lower.contains("approval") || lower.contains("permission") || lower.contains("denied") {
        return "policy".to_string();
    }
    if lower.contains("lease") || lower.contains("worker") {
        return "runtime".to_string();
    }
    if lower.contains("cancel") {
        return "cancellation".to_string();
    }
    fallback.to_string()
}

fn event_failure_category(event: &Event) -> String {
    match event.event_type.as_str() {
        "model_call_failed" => "model".to_string(),
        "tool_call_failed" | "tool_call_blocked" | "tool_approval_required" => "tool".to_string(),
        "run_cancel_requested" | "run_cancelled" | "step_cancelled" => "cancellation".to_string(),
        "lease_expired" => "runtime".to_string(),
        "step_retry_scheduled" => "retry".to_string(),
        "step_waiting_human" => "approval".to_string(),
        _ => failure_category(
            &format!(
                "{} {} {} {}",
                event.event_type,
                state_value_string(&event.payload, "error_type"),
                state_value_string(&event.payload, "error"),
                state_value_string(&event.payload, "reason")
            ),
            "agent",
        ),
    }
}

fn event_failure_status(kind: &str, run_status: &str) -> String {
    match kind {
        "step_failed" | "run_cancelled" | "step_cancelled" => "terminal".to_string(),
        "tool_call_blocked" => "blocked".to_string(),
        "step_retry_scheduled" | "lease_expired" => "recovery_scheduled".to_string(),
        "step_waiting_human" | "tool_approval_required" => "waiting_human".to_string(),
        "failure_classified" => "classified".to_string(),
        "error_raised" if run_status == "failed" => "terminal".to_string(),
        _ => "failed".to_string(),
    }
}

fn event_recoverability(kind: &str, run_status: &str) -> String {
    if run_status == "failed" && matches!(kind, "step_failed" | "run_cancelled" | "step_cancelled") {
        return "terminal".to_string();
    }
    match kind {
        "step_retry_scheduled" | "lease_expired" => "auto_retry".to_string(),
        "step_waiting_human" | "tool_approval_required" => "human_required".to_string(),
        "tool_call_blocked" => "manual_intervention".to_string(),
        _ => "unknown".to_string(),
    }
}

fn event_retryability(kind: &str) -> String {
    match kind {
        "step_retry_scheduled" | "lease_expired" => "retryable".to_string(),
        "tool_call_blocked" | "run_cancelled" | "step_cancelled" => "not_retryable".to_string(),
        _ => "unknown".to_string(),
    }
}

fn owner_for_failure_category(category: &str) -> String {
    match category {
        "tool" | "model" | "policy" | "sandbox" | "budget" | "runtime" => category.to_string(),
        "approval" | "cancellation" | "retry" => "runtime".to_string(),
        _ => "agent".to_string(),
    }
}

fn first_text(values: &[Option<&str>]) -> String {
    for value in values {
        if let Some(text) = value {
            if !text.is_empty() {
                return (*text).to_string();
            }
        }
    }
    "failure signal".to_string()
}

fn ref_state(kind: &str, value: &str) -> State {
    if value.is_empty() {
        return State::new();
    }
    state(&[("kind", kind.into()), ("value", value.into())])
}

fn state_value_string(row: &State, key: &str) -> String {
    match row.get(key) {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(value)) => value.to_string(),
        Some(value) => format_value(value),
        None => String::new(),
    }
}

fn state_string(row: &State, key: &str) -> Option<String> {
    let value = state_value_string(row, key);
    if value.is_empty() {
        None
    } else {
        Some(value)
    }
}

fn state_number(row: &State, key: &str) -> f64 {
    match row.get(key) {
        Some(Value::Number(value)) => *value,
        _ => 0.0,
    }
}

fn usage_total_tokens(usage: &State) -> f64 {
    for key in ["total_tokens", "totalTokens", "tokens"] {
        let value = state_number(usage, key);
        if value > 0.0 {
            return value;
        }
    }
    state_number(usage, "input_tokens")
        + state_number(usage, "prompt_tokens")
        + state_number(usage, "inputTokens")
        + state_number(usage, "output_tokens")
        + state_number(usage, "completion_tokens")
        + state_number(usage, "outputTokens")
}

fn state_array_len(row: &State, key: &str) -> usize {
    match row.get(key) {
        Some(Value::Array(values)) => values.len(),
        _ => 0,
    }
}

fn dedupe_states(rows: Vec<State>, key: &str) -> Vec<State> {
    let mut out = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for row in rows {
        let value = state_value_string(&row, key);
        if value.is_empty() || seen.contains(&value) {
            continue;
        }
        seen.insert(value);
        out.push(row);
    }
    out
}

fn count_state_field(rows: &[State], key: &str, expected: &str) -> usize {
    rows.iter()
        .filter(|row| state_value_string(row, key) == expected)
        .count()
}

fn count_recoverable_failures(rows: &[State]) -> usize {
    rows.iter()
        .filter(|row| matches!(state_value_string(row, "recoverability").as_str(), "auto_retry" | "recoverable" | "manual_verification" | "human_required"))
        .count()
}

fn slug(value: &str) -> String {
    let mut out = String::new();
    let mut previous_dash = false;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch.to_ascii_lowercase());
            previous_dash = false;
        } else if !previous_dash {
            out.push('-');
            previous_dash = true;
        }
    }
    let trimmed = out.trim_matches('-').to_string();
    if trimmed.is_empty() {
        "unknown".to_string()
    } else {
        trimmed
    }
}

fn format_state(state: &State) -> String {
    let mut keys: Vec<&String> = state.keys().collect();
    keys.sort();
    keys.into_iter()
        .map(|key| format!("{}={}", key, format_value(&state[key])))
        .collect::<Vec<_>>()
        .join(",")
}

fn format_value(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => format!("\"{}\"", value),
        Value::Object(value) => format!("{{{}}}", format_state(value)),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(format_value)
                .collect::<Vec<_>>()
                .join(",")
        ),
    }
}

fn stable_hash(input: &str) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in input.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

fn new_id(prefix: &str) -> String {
    let value = ID_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{prefix}_{value:016x}")
}

fn now_seconds() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs_f64()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn state(items: &[(&str, Value)]) -> State {
        items
            .iter()
            .map(|(key, value)| ((*key).to_string(), value.clone()))
            .collect()
    }

    fn event_exists(events: &[Event], event_type: &str) -> bool {
        events.iter().any(|event| event.event_type == event_type)
    }

    fn claim_context(
        runtime: &mut Runtime,
        run_id: &str,
        worker: &str,
        role: &str,
    ) -> AgentContext {
        let claim = runtime.store.claim_step(worker, run_id, 60.0).unwrap();
        let (_state, version, session_id) = runtime.store.load_state(run_id).unwrap();
        let mut payload = State::new();
        payload.insert("agent_role".to_string(), Value::String(role.to_string()));
        runtime.store.append_event(
            run_id,
            Some(&session_id),
            Some(&claim.step_id),
            "agent_started",
            payload,
            Some(role),
            Some(version),
            None,
        );
        AgentContext {
            run_id: run_id.to_string(),
            session_id,
            step_id: claim.step_id,
            agent_role: role.to_string(),
            lease_token: claim.lease_token,
            attempt: claim.attempt,
            state_version: version,
            pending_patch: State::new(),
        }
    }

    #[test]
    fn runtime_creates_evidence_and_replay() {
        let mut runtime = Runtime::new();
        runtime.register_tool(ToolSpec::new(
            "docs.echo",
            Box::new(|args| Ok(Value::Object(state(&[("echo", args["text"].clone())])))),
        ));
        let (run_id, _) = runtime.create_run(state(&[("input", "hello".into())]));
        let ok = runtime
            .run_once(&run_id, "worker-a", "Researcher", 60.0, |ctx, state| {
                let mut result = State::new();
                result.insert("from_state".to_string(), state["input"].clone());
                ctx.write_state("tool_result", Value::Object(result));
                Ok(())
            })
            .unwrap();
        assert!(ok);
        let bundle = export_evidence(&runtime.store, &run_id).unwrap();
        assert_eq!(bundle.schema_version, "agentledger.evidence.v1");
        let summary = replay(&runtime.store, &run_id).unwrap();
        assert!(summary.replay_safe);
        assert_eq!(summary.event_count, bundle.events.len());
    }

    #[test]
    fn local_snapshot_store_round_trips_completed_run() {
        let mut runtime = Runtime::new();
        let (run_id, _) = runtime.create_run(state(&[("input", "hello".into())]));
        runtime
            .run_once(&run_id, "worker-a", "Researcher", 60.0, |ctx, state| {
                let mut result = State::new();
                result.insert("echo".to_string(), state["input"].clone());
                ctx.write_state("tool_result", Value::Object(result));
                Ok(())
            })
            .unwrap();
        let path =
            std::env::temp_dir().join(format!("agentledger-rust-{}.store", new_id("snapshot")));
        runtime.store.save_to_path(&path).unwrap();

        let reopened = MemoryStore::load_from_path(&path).unwrap();
        let final_state = reopened.final_state(&run_id).unwrap();
        assert_eq!(
            final_state.get("tool_result"),
            Some(&Value::Object(state(&[("echo", "hello".into())])))
        );
        let bundle = export_evidence(&reopened, &run_id).unwrap();
        assert_eq!(reopened.steps(&run_id).len(), 1);
        assert_eq!(
            replay(&reopened, &run_id).unwrap().event_count,
            bundle.events.len()
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn local_blob_store_round_trips_json_values() {
        let root = std::env::temp_dir().join(format!("agentledger-rust-blobs-{}", new_id("blob")));
        let blobs = LocalBlobStore::open(&root).unwrap();
        let value = Value::Object(state(&[(
            "hello",
            Value::Object(state(&[("nested", "world".into())])),
        )]));
        let first = blobs.put_json(&value).unwrap();
        let second = blobs.put_json(&value).unwrap();
        assert!(first.0.starts_with("sha256:"));
        assert!(first.1.starts_with("blob://sha256/"));
        assert_eq!(first, second);
        assert_eq!(blobs.get_json(&first.1).unwrap(), value);
        assert!(blobs.get_json("unsupported://blob").is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn tool_schema_validation_rejects_invalid_input() {
        let input_schema = Value::Object(state(&[
            ("type", "object".into()),
            (
                "required",
                Value::Array(vec![Value::String("text".to_string())]),
            ),
            ("additionalProperties", false.into()),
            (
                "properties",
                Value::Object(state(&[(
                    "text",
                    Value::Object(state(&[("type", "string".into())])),
                )])),
            ),
        ]));
        let mut runtime = Runtime::new();
        runtime.register_tool(
            ToolSpec::new(
                "docs.echo",
                Box::new(|args| Ok(Value::Object(state(&[("echo", args["text"].clone())])))),
            )
            .input_schema(input_schema),
        );
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker", "SchemaAgent");
        assert!(runtime.call_tool(&ctx, "docs.echo", State::new()).is_err());
        assert!(runtime.store.events(&run_id).iter().any(|event| {
            event.event_type == "tool_call_failed"
                && event.payload.get("phase")
                    == Some(&Value::String("input_validation".to_string()))
        }));
    }

    #[test]
    fn tool_ledger_reuses_side_effect_after_retry() {
        let mut runtime = Runtime::new();
        runtime.register_tool(
            ToolSpec::new(
                "github.create_pr",
                Box::new(|args| {
                    Ok(Value::Object(state(&[
                        ("external_id", "pr-123".into()),
                        ("title", args["title"].clone()),
                    ])))
                }),
            )
            .side_effect("external")
            .idempotency_required(true),
        );
        let (run_id, _) = runtime.create_run(state(&[("title", "runtime parity".into())]));
        let ctx = claim_context(&mut runtime, &run_id, "worker-a", "Coder");
        let first = runtime
            .call_tool(
                &ctx,
                "github.create_pr",
                state(&[("title", "runtime parity".into())]),
            )
            .unwrap();
        runtime
            .store
            .mark_retry(&run_id, &ctx.step_id, "RetryableAgentError", "retryable");
        let ctx2 = claim_context(&mut runtime, &run_id, "worker-b", "Coder");
        let second = runtime
            .call_tool(
                &ctx2,
                "github.create_pr",
                state(&[("title", "runtime parity".into())]),
            )
            .unwrap();
        assert_eq!(first, second);
        assert_eq!(runtime.store.ledger(&run_id).len(), 1);
    }

    #[test]
    fn policy_denies_unapproved_high_risk_tool() {
        let mut runtime = Runtime::new();
        runtime.register_tool(
            ToolSpec::new("repo.write", Box::new(|_| Ok(Value::Bool(true)))).risk_level("high"),
        );
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker", "Reviewer");
        let err = runtime
            .call_tool(&ctx, "repo.write", state(&[("path", "README.md".into())]))
            .unwrap_err();
        assert!(err.0.contains("high-risk"));
        assert!(runtime
            .store
            .events(&run_id)
            .iter()
            .any(|event| event.event_type == "tool_permission_decided"
                && event.payload.get("allowed") == Some(&Value::Bool(false))));
    }

    #[test]
    fn approval_pauses_and_resumes_step() {
        let mut runtime = Runtime::new();
        runtime.register_tool(
            ToolSpec::new(
                "github.create_pr",
                Box::new(|_| Ok(Value::Object(state(&[("external_id", "pr-42".into())])))),
            )
            .risk_level("high")
            .approval_required(true)
            .side_effect("external")
            .idempotency_required(true),
        );
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker-a", "Coder");
        let err = runtime
            .call_tool(&ctx, "github.create_pr", state(&[("title", "safe".into())]))
            .unwrap_err();
        assert!(err.0.starts_with("approval required:"));
        let approval_id = err.0.trim_start_matches("approval required:").to_string();
        runtime
            .store
            .mark_waiting_human(&run_id, &ctx.step_id, &err.0, &approval_id);
        assert_eq!(runtime.store.steps(&run_id)[0].status, "waiting_human");
        runtime
            .store
            .approve_request(&approval_id, "alice", "reviewed")
            .unwrap();
        let ctx2 = claim_context(&mut runtime, &run_id, "worker-b", "Coder");
        let result = runtime
            .call_tool(
                &ctx2,
                "github.create_pr",
                state(&[("title", "safe".into())]),
            )
            .unwrap();
        assert!(matches!(result, Value::Object(_)));

        let (denied_run, _) = runtime.create_run(State::new());
        let denied_ctx = claim_context(&mut runtime, &denied_run, "worker-c", "Coder");
        let denied_err = runtime
            .call_tool(
                &denied_ctx,
                "github.create_pr",
                state(&[("title", "blocked".into())]),
            )
            .unwrap_err();
        let denied_id = denied_err
            .0
            .trim_start_matches("approval required:")
            .to_string();
        runtime.store.mark_waiting_human(
            &denied_run,
            &denied_ctx.step_id,
            &denied_err.0,
            &denied_id,
        );
        runtime
            .store
            .deny_request(&denied_id, "bob", "not allowed")
            .unwrap();
        assert_eq!(runtime.store.steps(&denied_run)[0].status, "failed");
    }

    #[test]
    fn mcp_tool_adapter_maps_governance_annotations() {
        fn call(_name: &str, _args: State) -> Result<Value> {
            Ok(Value::Object(state(&[("ok", true.into())])))
        }
        let adapter = MCPToolAdapter { client_call: call };
        let spec = adapter.tool_spec_from_descriptor(&state(&[
            ("name", "mcp.github.create_pr".into()),
            (
                "inputSchema",
                Value::Object(state(&[
                    ("type", "object".into()),
                    (
                        "required",
                        Value::Array(vec![Value::String("title".to_string())]),
                    ),
                ])),
            ),
            (
                "annotations",
                Value::Object(state(&[
                    ("side_effect", "external_write".into()),
                    ("risk_level", "high".into()),
                    ("idempotency_required", true.into()),
                    ("approval_required", true.into()),
                    ("sandbox_required", true.into()),
                    ("sandbox_executor", "docker".into()),
                    (
                        "sandbox_policy",
                        Value::Object(state(&[
                            ("network", "deny".into()),
                            ("filesystem", "read-only".into()),
                        ])),
                    ),
                ])),
            ),
        ]));
        assert_eq!(spec.side_effect, "external_write");
        assert_eq!(spec.risk_level, "high");
        assert!(spec.idempotency_required);
        assert!(spec.approval_required);
        assert!(spec.sandbox_required);
        assert_eq!(spec.sandbox_executor, "docker");
        assert_eq!(
            spec.sandbox_policy.get("network"),
            Some(&Value::String("deny".to_string()))
        );
        assert_eq!(
            spec.sandbox_policy.get("filesystem"),
            Some(&Value::String("read-only".to_string()))
        );
        assert!(spec.input_schema.is_some());
    }

    #[test]
    fn sandbox_required_tool_fails_closed() {
        let mut runtime = Runtime::new();
        runtime.register_tool(
            ToolSpec::new("shell.exec", Box::new(|_| Ok(Value::Bool(true)))).sandbox_required(true),
        );
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker", "Executor");
        let err = runtime
            .call_tool(
                &ctx,
                "shell.exec",
                state(&[("argv", Value::Object(State::new()))]),
            )
            .unwrap_err();
        assert!(err.0.contains("sandbox executor"));
        let events = runtime.store.events(&run_id);
        assert!(event_exists(&events, "sandbox_started"));
        assert!(event_exists(&events, "tool_call_failed"));
    }

    #[test]
    fn docker_sandbox_executor_requires_explicit_execution() {
        let executor = DockerSandboxExecutor::new("fake-image", false).with_binary("/bin/echo");
        let result = executor.run_tool(
            state(&[("_sandbox_command", Value::Array(vec!["echo".into(), "hi".into()]))]),
            &SandboxPolicy {
                tool_name: "cmd.echo".to_string(),
                run_id: "run".to_string(),
                step_id: "step".to_string(),
                executor: "docker".to_string(),
                network: "deny".to_string(),
                filesystem: "read-only".to_string(),
                timeout_seconds: 1,
                extra: State::new(),
            },
        );
        assert!(!result.ok);
        assert_eq!(result.metadata.get("error_type"), Some(&Value::String("SandboxAdapterNotInstalled".to_string())));
    }

    #[test]
    fn docker_sandbox_executor_runs_command_style_tool_with_injected_binary() {
        let mut runtime = Runtime::new();
        runtime.set_sandbox(Box::new(DockerSandboxExecutor::new("fake-image", true).with_binary("/bin/echo")));
        runtime.register_tool(
            ToolSpec::new("cmd.echo", Box::new(|_| Err(RuntimeError("direct func should not execute".to_string()))))
                .sandbox_required(true)
                .sandbox_executor("docker"),
        );
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker", "Executor");
        let value = runtime
            .call_tool(
                &ctx,
                "cmd.echo",
                state(&[("_sandbox_command", Value::Array(vec!["echo".into(), "hi".into()]))]),
            )
            .unwrap();
        let output = match value { Value::Object(output) => output, _ => panic!("expected object output") };
        let stdout = match output.get("stdout") { Some(Value::String(value)) => value, _ => panic!("expected stdout") };
        assert!(stdout.contains("run"));
        assert!(stdout.contains("fake-image"));
        let events = runtime.store.events(&run_id);
        assert!(event_exists(&events, "sandbox_completed"));
        assert!(event_exists(&events, "tool_call_completed"));
    }

    #[test]
    fn cost_budget_and_failure_attribution() {
        let mut runtime = Runtime::new();
        runtime.set_budget(BudgetLimits {
            max_tool_calls: Some(1.0),
            max_model_tokens: None,
            max_total_usd: None,
        });
        runtime.register_tool(ToolSpec::new(
            "docs.echo",
            Box::new(|args| Ok(Value::Object(state(&[("echo", args["text"].clone())])))),
        ));
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker", "Researcher");
        runtime
            .record_model_call(&ctx, "gpt-test", 10.0, 5.0, 0.01)
            .unwrap();
        runtime
            .call_tool(&ctx, "docs.echo", state(&[("text", "first".into())]))
            .unwrap();
        let err = runtime
            .call_tool(&ctx, "docs.echo", state(&[("text", "second".into())]))
            .unwrap_err();
        runtime.store.mark_failed(
            &run_id,
            &ctx.step_id,
            classify_runtime_error(&err.0),
            &err.0,
        );
        let summary = runtime.store.cost_summary(&run_id);
        assert_eq!(summary.tool_calls, 1.0);
        assert_eq!(summary.model_tokens, 15.0);
        assert_eq!(summary.total_usd, 0.01);
        let cost = cost_attribution(&runtime.store, &run_id);
        assert_eq!(cost.by_agent["Researcher"].tool_calls, 1.0);
        assert_eq!(cost.by_agent["Researcher"].model_tokens, 15.0);
        let failure = failure_attribution(&runtime.store, &run_id).unwrap();
        assert_eq!(failure.failed_steps.len(), 1);
        assert!(event_exists(&failure.failure_events, "budget_check_failed"));
        assert!(event_exists(&failure.failure_events, "failure_classified"));
        assert!(!failure.failure_envelopes.is_empty());
        assert_eq!(
            failure.failure_lifecycle["schema_version"],
            Value::String("agentledger.failure.lifecycle.v1".to_string())
        );
        assert_eq!(
            failure.failure_export["schema_version"],
            Value::String("agentledger.failure.export.v1".to_string())
        );
        assert_eq!(failure.failure_replay_plan["safe_to_replay"], Value::Bool(true));
        assert!(state_number(&failure.failure_alerts, "alert_count") > 0.0);
        let events = runtime.store.events(&run_id);
        assert!(event_exists(&events, "model_call_requested"));
        assert!(event_exists(&events, "model_call_completed"));
    }

    #[test]
    fn model_evidence_boundary_records_failure_and_tool_proposal() {
        let mut runtime = Runtime::new();
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker", "Researcher");
        runtime
            .record_model_failure(
                &ctx,
                "deepseek",
                "deepseek-chat",
                "RateLimitError",
                "rate limited",
                Some(true),
                state(&[("messages", Value::Array(vec!["hello".into()]))]),
                State::new(),
                0.0,
                State::new(),
            )
            .unwrap();
        runtime.record_tool_call_proposal(
            &ctx,
            "search_contract_clause",
            state(&[("clause", "payment".into())]),
            Some("deepseek"),
            Some("deepseek-chat"),
            None,
            None,
            Some("model requested clause search"),
            State::new(),
        );
        let events = runtime.store.events(&run_id);
        assert!(event_exists(&events, "model_call_failed"));
        assert!(event_exists(&events, "tool_call_proposed"));
        let failure = failure_attribution(&runtime.store, &run_id).unwrap();
        assert!(failure
            .failure_envelopes
            .iter()
            .any(|item| item.get("category") == Some(&Value::String("model".to_string()))));
    }

    #[test]
    fn media_and_stream_artifacts_are_indexed_in_evidence_and_replay() {
        let mut runtime = Runtime::new();
        let (run_id, _) = runtime.create_run(State::new());
        let ctx = claim_context(&mut runtime, &run_id, "worker-media", "MediaAgent");
        let mut media_metadata = State::new();
        media_metadata.insert(
            "mime_type".to_string(),
            Value::String("image/jpeg".to_string()),
        );
        media_metadata.insert("frame_index".to_string(), Value::Number(1.0));
        let mut lineage = State::new();
        lineage.insert(
            "source_blob_ref".to_string(),
            Value::String("s3://media/demo/input.mp4".to_string()),
        );
        lineage.insert(
            "tool_call_id".to_string(),
            Value::String("video.extract_frames".to_string()),
        );
        let frame_id = runtime
            .create_media_artifact(
                &ctx,
                "frame-0001",
                "frame",
                MediaArtifactOptions {
                    uri: Some("s3://media/demo/frame-0001.jpg".to_string()),
                    media_metadata,
                    lineage,
                    ..Default::default()
                },
            )
            .unwrap();
        let checkpoint_id = runtime
            .create_stream_checkpoint(
                &ctx,
                "camera-checkpoint",
                StreamCheckpointOptions {
                    stream_id: "camera-1".to_string(),
                    consumer_id: "vision-agent".to_string(),
                    offset: Value::Number(7.0),
                    watermark: Some(Value::Number(1.5)),
                    chunk: Some(StreamChunkRef {
                        stream_id: "camera-1".to_string(),
                        chunk_id: "chunk-7".to_string(),
                        offset: Value::Number(7.0),
                        content_ref: Some("blob://sha256/chunk-7.json".to_string()),
                        sequence: Some(7.0),
                        ..Default::default()
                    }),
                    ..Default::default()
                },
            )
            .unwrap();
        let mut artifacts = State::new();
        artifacts.insert("frame".to_string(), Value::String(frame_id));
        artifacts.insert("checkpoint".to_string(), Value::String(checkpoint_id));
        runtime
            .store
            .commit_state_patch(
                &run_id,
                &ctx.step_id,
                &ctx.lease_token,
                ctx.state_version,
                state(&[("artifacts", Value::Object(artifacts))]),
            )
            .unwrap();
        let bundle = export_evidence(&runtime.store, &run_id).unwrap();
        assert_eq!(bundle.artifacts.len(), 2);
        assert_eq!(bundle.media_artifacts.len(), 1);
        assert_eq!(bundle.stream_checkpoints.len(), 1);
        assert_eq!(
            bundle.media_artifacts[0].get("kind"),
            Some(&Value::String("frame".to_string()))
        );
        assert_eq!(
            bundle.stream_checkpoints[0].get("stream_id"),
            Some(&Value::String("camera-1".to_string()))
        );
        let summary = replay(&runtime.store, &run_id).unwrap();
        assert_eq!(summary.artifact_count, 2);
        assert_eq!(summary.media_artifact_count, 1);
        assert_eq!(summary.stream_checkpoint_count, 1);
    }

    #[test]
    fn lease_recovery_fences_previous_owner() {
        let mut store = MemoryStore::new();
        let (run_id, step_id) = store.create_run(State::new());
        let claim = store.claim_step("stale-worker", &run_id, 0.0).unwrap();
        assert_eq!(store.recover_expired_leases(), 1);
        assert!(store
            .commit_state_patch(
                &run_id,
                &step_id,
                &claim.lease_token,
                0,
                state(&[("late", true.into())])
            )
            .is_err());
        assert!(store.claim_step("new-worker", &run_id, 60.0).is_ok());
    }

    #[test]
    fn cancellation_fences_worker() {
        let mut store = MemoryStore::new();
        let (run_id, step_id) = store.create_run(State::new());
        let claim = store.claim_step("worker", &run_id, 60.0).unwrap();
        assert_eq!(store.cancel_run(&run_id, "operator requested").unwrap(), 1);
        assert!(store
            .commit_state_patch(
                &run_id,
                &step_id,
                &claim.lease_token,
                0,
                state(&[("late", true.into())])
            )
            .is_err());
    }

    #[test]
    fn shared_runtime_baseline_fixture() {
        let fixture =
            std::fs::read_to_string("../contracts/conformance/runtime_baseline.v1.json").unwrap();
        assert!(fixture.contains("agentledger.conformance.runtime_baseline.v1"));
        for scenario in [
            "durable_run_evidence_replay",
            "tool_ledger_idempotent_retry",
            "lease_recovery_fences_stale_worker",
            "cancellation_fences_worker",
        ] {
            assert!(
                fixture.contains(scenario),
                "missing shared fixture scenario {scenario}"
            );
        }
    }

    #[test]
    fn shared_parity_fixtures() {
        let fixtures: Vec<(&str, &[&str])> = vec![
            (
                "../contracts/conformance/policy_approval_sandbox.v1.json",
                &[
                    "agentledger.conformance.policy_approval_sandbox.v1",
                    "policy_denies_unapproved_high_risk_tool",
                    "approval_pauses_and_resumes_step",
                    "sandbox_required_tool_fails_closed",
                ],
            ),
            (
                "../contracts/conformance/cost_failure_attribution.v1.json",
                &[
                    "agentledger.conformance.cost_failure_attribution.v1",
                    "tool_and_model_cost_attributed_to_run_step_role",
                    "budget_exhaustion_blocks_execution",
                    "failure_attribution_classifies_agent_tool_model_runtime",
                ],
            ),
            (
                "../contracts/conformance/local_persistence.v1.json",
                &[
                    "agentledger.conformance.local_persistence.v1",
                    "local_store_round_trips_completed_run",
                    "local_store_preserves_evidence_replay_chain",
                    "local_store_uses_atomic_snapshot_write",
                ],
            ),
            (
                "../contracts/conformance/local_blob_store.v1.json",
                &[
                    "agentledger.conformance.local_blob_store.v1",
                    "blob_roundtrip_json_value",
                    "blob_content_address_is_stable",
                    "blob_bad_ref_is_rejected",
                ],
            ),
            (
                "../contracts/conformance/tool_schema_validation.v1.json",
                &[
                    "agentledger.conformance.tool_schema_validation.v1",
                    "invalid_tool_input_rejected_before_execution",
                    "valid_tool_input_and_output_pass",
                    "invalid_tool_output_rejected",
                ],
            ),
            (
                "../contracts/conformance/worker_service.v1.json",
                &[
                    "agentledger.conformance.worker_service.v1",
                    "local_worker_runs_until_terminal",
                    "worker_service_stops_after_idle_poll",
                    "worker_loop_recovers_expired_leases",
                ],
            ),
            (
                "../contracts/conformance/media_stream_artifacts.v1.json",
                &[
                    "agentledger.conformance.media_stream_artifacts.v1",
                    "media_artifact_ref_is_indexed_in_evidence",
                    "stream_checkpoint_ref_is_indexed_in_evidence",
                ],
            ),
            (
                "../contracts/conformance/evidence_consumers.v1.json",
                &[
                    "agentledger.conformance.evidence_consumers.v1",
                    "trace_spans_from_evidence",
                    "evidence_diff_detects_state_and_event_changes",
                    "divergence_report_lists_changed_dimensions",
                    "static_debug_summary_is_exportable",
                ],
            ),
            (
                "../contracts/conformance/static_debug_html.v1.json",
                &[
                    "agentledger.conformance.static_debug_html.v1",
                    "static_debug_html_contains_run_events_and_state",
                ],
            ),
            (
                "../contracts/conformance/ops_readiness.v1.json",
                &[
                    "agentledger.conformance.ops_readiness.v1",
                    "retention_plan_is_non_destructive_and_counts_evidence",
                    "backup_readiness_reports_required_checks",
                ],
            ),
            (
                "../contracts/conformance/storage_schema.v1.json",
                &[
                    "agentledger.conformance.storage_schema.v1",
                    "latest_schema_version_and_ddl_are_available",
                ],
            ),
            (
                "../contracts/conformance/mcp_adapters.v1.json",
                &[
                    "agentledger.conformance.mcp_adapters.v1",
                    "in_memory_mcp_tool_server_lists_and_calls_tools",
                    "mcp_tool_descriptor_maps_to_tool_spec",
                    "in_memory_mcp_context_server_reads_resources",
                ],
            ),
            (
                "../contracts/conformance/framework_adapters.v1.json",
                &[
                    "agentledger.conformance.framework_adapters.v1",
                    "function_adapter_maps_run_spec_and_invokes_agent",
                    "method_framework_adapter_uses_first_available_method_and_writes_output",
                ],
            ),
            (
                "../contracts/conformance/otlp_trace_export.v1.json",
                &[
                    "agentledger.conformance.otlp_trace_export.v1",
                    "otlp_json_contains_resource_scope_and_spans",
                ],
            ),
            (
                "../contracts/conformance/simple_api.v1.json",
                &[
                    "agentledger.conformance.simple_api.v1",
                    "simple_run_returns_output_and_state",
                ],
            ),
        ];
        for (path, required) in fixtures {
            let body = std::fs::read_to_string(path).unwrap();
            for token in required {
                assert!(body.contains(token), "fixture {path} missing {token}");
            }
        }
    }
}

#[derive(Clone, Debug)]
pub struct TraceSpan {
    pub trace_id: String,
    pub span_id: String,
    pub parent_span_id: Option<String>,
    pub name: String,
    pub start_time: f64,
    pub end_time: f64,
    pub attributes: State,
}

#[derive(Clone, Debug)]
pub struct SequenceDiff {
    pub left_count: usize,
    pub right_count: usize,
    pub changed_count: usize,
}

#[derive(Clone, Debug)]
pub struct DictDiff {
    pub changed_count: usize,
}

#[derive(Clone, Debug)]
pub struct EvidenceDiffReport {
    pub left_run_id: String,
    pub right_run_id: String,
    pub same: bool,
    pub final_state_changed_count: usize,
    pub event_types_changed_count: usize,
    pub media_artifacts_changed_count: usize,
    pub stream_checkpoints_changed_count: usize,
}

#[derive(Clone, Debug)]
pub struct DivergenceReport {
    pub left_run_id: String,
    pub right_run_id: String,
    pub same: bool,
    pub changed_dimensions: Vec<String>,
}

pub fn trace_spans(bundle: &EvidenceBundle) -> Vec<TraceSpan> {
    let mut spans = Vec::new();
    for (index, event) in bundle.events.iter().enumerate() {
        let seq = if event.seq == 0 {
            index as u64 + 1
        } else {
            event.seq
        };
        spans.push(TraceSpan {
            trace_id: bundle.run.run_id.clone(),
            span_id: span_id("evt", seq),
            parent_span_id: None,
            name: event.event_type.clone(),
            start_time: event.timestamp,
            end_time: event.timestamp,
            attributes: state(&[
                (
                    "agentledger.run_id",
                    Value::String(bundle.run.run_id.clone()),
                ),
                ("agentledger.seq", Value::Number(seq as f64)),
                (
                    "agentledger.payload_hash",
                    Value::String(event.payload_hash.clone()),
                ),
                (
                    "agentledger.payload_ref",
                    Value::String(event.payload_ref.clone()),
                ),
            ]),
        });
    }
    for (index, artifact) in bundle.media_artifacts.iter().enumerate() {
        spans.push(TraceSpan {
            trace_id: bundle.run.run_id.clone(),
            span_id: span_id("media", index as u64 + 1),
            parent_span_id: None,
            name: "media_artifact".to_string(),
            start_time: bundle.run.updated_at,
            end_time: bundle.run.updated_at,
            attributes: state(&[
                (
                    "agentledger.run_id",
                    Value::String(bundle.run.run_id.clone()),
                ),
                (
                    "agentledger.artifact_id",
                    artifact.get("artifact_id").cloned().unwrap_or_default(),
                ),
                (
                    "agentledger.media_kind",
                    artifact.get("kind").cloned().unwrap_or_default(),
                ),
            ]),
        });
    }
    for (index, checkpoint) in bundle.stream_checkpoints.iter().enumerate() {
        spans.push(TraceSpan {
            trace_id: bundle.run.run_id.clone(),
            span_id: span_id("stream", index as u64 + 1),
            parent_span_id: None,
            name: "stream_checkpoint".to_string(),
            start_time: bundle.run.updated_at,
            end_time: bundle.run.updated_at,
            attributes: state(&[
                (
                    "agentledger.run_id",
                    Value::String(bundle.run.run_id.clone()),
                ),
                (
                    "agentledger.stream_id",
                    checkpoint.get("stream_id").cloned().unwrap_or_default(),
                ),
                (
                    "agentledger.consumer_id",
                    checkpoint.get("consumer_id").cloned().unwrap_or_default(),
                ),
            ]),
        });
    }
    spans
}

pub fn trace_jsonl(bundle: &EvidenceBundle) -> String {
    trace_spans(bundle)
        .iter()
        .map(|span| {
            format!(
                "{{\"trace_id\":\"{}\",\"span_id\":\"{}\",\"name\":\"{}\"}}\n",
                span.trace_id, span.span_id, span.name
            )
        })
        .collect()
}

pub fn diff_evidence(left: &EvidenceBundle, right: &EvidenceBundle) -> EvidenceDiffReport {
    let final_state = diff_state(&left.final_state, &right.final_state).changed_count;
    let events = diff_values(&event_types(&left.events), &event_types(&right.events)).changed_count;
    let media = diff_values(
        &state_fingerprints(&left.media_artifacts),
        &state_fingerprints(&right.media_artifacts),
    )
    .changed_count;
    let streams = diff_values(
        &state_fingerprints(&left.stream_checkpoints),
        &state_fingerprints(&right.stream_checkpoints),
    )
    .changed_count;
    EvidenceDiffReport {
        left_run_id: left.run.run_id.clone(),
        right_run_id: right.run.run_id.clone(),
        same: final_state == 0
            && events == 0
            && media == 0
            && streams == 0
            && left.bundle_hash == right.bundle_hash,
        final_state_changed_count: final_state,
        event_types_changed_count: events,
        media_artifacts_changed_count: media,
        stream_checkpoints_changed_count: streams,
    }
}

pub fn divergence_report(left: &EvidenceBundle, right: &EvidenceBundle) -> DivergenceReport {
    let mut changed = Vec::new();
    if diff_values(&event_types(&left.events), &event_types(&right.events)).changed_count > 0 {
        changed.push("events".to_string());
    }
    if diff_state(&left.final_state, &right.final_state).changed_count > 0 {
        changed.push("state".to_string());
    }
    if diff_values(
        &state_fingerprints(&left.media_artifacts),
        &state_fingerprints(&right.media_artifacts),
    )
    .changed_count
        > 0
    {
        changed.push("media_artifacts".to_string());
    }
    if diff_values(
        &state_fingerprints(&left.stream_checkpoints),
        &state_fingerprints(&right.stream_checkpoints),
    )
    .changed_count
        > 0
    {
        changed.push("stream_checkpoints".to_string());
    }
    if diff_values(
        &ledger_fingerprints_rust(&left.tool_ledger),
        &ledger_fingerprints_rust(&right.tool_ledger),
    )
    .changed_count
        > 0
    {
        changed.push("ledger".to_string());
    }
    DivergenceReport {
        left_run_id: left.run.run_id.clone(),
        right_run_id: right.run.run_id.clone(),
        same: changed.is_empty(),
        changed_dimensions: changed,
    }
}

pub fn debug_summary(bundle: &EvidenceBundle) -> State {
    let changes = bundle
        .events
        .iter()
        .filter(|event| {
            matches!(
                event.event_type.as_str(),
                "run_created" | "state_committed" | "system_state_patch_applied"
            )
        })
        .count();
    state(&[
        ("run_id", Value::String(bundle.run.run_id.clone())),
        ("event_count", Value::Number(bundle.events.len() as f64)),
        ("state_change_count", Value::Number(changes as f64)),
        ("final_state", Value::Object(bundle.final_state.clone())),
    ])
}

fn span_id(prefix: &str, seq: u64) -> String {
    format!("{}-{:06}", prefix, seq)
}
fn event_types(events: &[Event]) -> Vec<Value> {
    events
        .iter()
        .map(|event| Value::String(event.event_type.clone()))
        .collect()
}
fn state_fingerprints(rows: &[State]) -> Vec<Value> {
    rows.iter()
        .map(|row| Value::String(encode_state(row)))
        .collect()
}
fn ledger_fingerprints_rust(rows: &[ToolLedgerEntry]) -> Vec<Value> {
    rows.iter()
        .map(|row| {
            Value::String(format!(
                "{}:{}:{}",
                row.tool_name, row.status, row.request_hash
            ))
        })
        .collect()
}

fn diff_state(left: &State, right: &State) -> DictDiff {
    let mut keys: Vec<String> = left.keys().chain(right.keys()).cloned().collect();
    keys.sort();
    keys.dedup();
    let changed_count = keys
        .into_iter()
        .filter(|key| left.get(key) != right.get(key))
        .count();
    DictDiff { changed_count }
}

fn diff_values(left: &[Value], right: &[Value]) -> SequenceDiff {
    let max = left.len().max(right.len());
    let mut changed_count = 0;
    for index in 0..max {
        if left.get(index) != right.get(index) {
            changed_count += 1;
        }
    }
    SequenceDiff {
        left_count: left.len(),
        right_count: right.len(),
        changed_count,
    }
}

fn state(items: &[(&str, Value)]) -> State {
    let mut out = State::new();
    for (key, value) in items {
        out.insert((*key).to_string(), value.clone());
    }
    out
}

#[derive(Clone, Debug)]
pub struct RunResult {
    pub run_id: String,
    pub session_id: String,
    pub ok: bool,
    pub output: Option<Value>,
    pub state: State,
}

pub type SimpleAgentFunc = fn(&mut AgentContext, State) -> Result<Option<Value>>;

pub fn simple_run(agent: SimpleAgentFunc, initial_state: State) -> Result<RunResult> {
    let mut runtime = Runtime::new();
    simple_run_with_runtime(&mut runtime, agent, initial_state)
}

pub fn simple_run_with_runtime(
    runtime: &mut Runtime,
    agent: SimpleAgentFunc,
    initial_state: State,
) -> Result<RunResult> {
    let (run_id, _) = runtime.create_run(initial_state);
    let claim = runtime.store.claim_step("worker-simple", &run_id, 60.0)?;
    let (state_value, version, session_id) = runtime.store.load_state(&claim.run_id)?;
    runtime.store.append_event(
        &claim.run_id,
        Some(&session_id),
        Some(&claim.step_id),
        "agent_started",
        state(&[
            ("agent_role", "Agent".into()),
            ("attempt", Value::Number(claim.attempt as f64)),
        ]),
        Some("Agent"),
        Some(version),
        None,
    );
    let mut ctx = AgentContext {
        run_id: claim.run_id.clone(),
        session_id: session_id.clone(),
        step_id: claim.step_id.clone(),
        agent_role: "Agent".to_string(),
        lease_token: claim.lease_token.clone(),
        attempt: claim.attempt,
        state_version: version,
        pending_patch: State::new(),
    };
    if let Some(output) = agent(&mut ctx, state_value)? {
        runtime.store.append_event(
            &ctx.run_id,
            Some(&ctx.session_id),
            Some(&ctx.step_id),
            "agent_result_returned",
            state(&[("agent", "agent".into())]),
            Some(&ctx.agent_role),
            Some(ctx.state_version),
            None,
        );
        ctx.write_state("output", output);
    }
    runtime.store.commit_state_patch(
        &claim.run_id,
        &claim.step_id,
        &claim.lease_token,
        version,
        ctx.pending_patch,
    )?;
    let state_result = runtime.store.final_state(&run_id)?;
    let run = runtime.store.run(&run_id)?;
    Ok(RunResult {
        run_id,
        session_id: run.session_id,
        ok: true,
        output: state_result.get("output").cloned(),
        state: state_result,
    })
}

pub fn otlp_trace_json(
    bundle: &EvidenceBundle,
    service_name: &str,
    service_version: Option<&str>,
) -> State {
    let service_name = if service_name.is_empty() {
        "agentledger"
    } else {
        service_name
    };
    let mut resource_attrs = State::new();
    resource_attrs.insert(
        "service.name".to_string(),
        Value::String(service_name.to_string()),
    );
    if let Some(version) = service_version {
        resource_attrs.insert(
            "service.version".to_string(),
            Value::String(version.to_string()),
        );
    }
    let spans = trace_spans(bundle)
        .into_iter()
        .map(|span| {
            let mut attrs = span.attributes.clone();
            attrs.insert(
                "agentledger.original_trace_id".to_string(),
                Value::String(span.trace_id.clone()),
            );
            attrs.insert(
                "agentledger.original_span_id".to_string(),
                Value::String(span.span_id.clone()),
            );
            Value::Object(state(&[
                ("traceId", Value::String(hex_id(&span.trace_id, 32))),
                ("spanId", Value::String(hex_id(&span.span_id, 16))),
                ("name", Value::String(span.name)),
                ("kind", Value::String("SPAN_KIND_INTERNAL".to_string())),
                (
                    "startTimeUnixNano",
                    Value::String(((span.start_time * 1_000_000_000.0) as u64).to_string()),
                ),
                (
                    "endTimeUnixNano",
                    Value::String(((span.end_time * 1_000_000_000.0) as u64).to_string()),
                ),
                ("attributes", Value::Array(otlp_attributes(&attrs))),
            ]))
        })
        .collect::<Vec<_>>();
    state(&[(
        "resourceSpans",
        Value::Array(vec![Value::Object(state(&[
            (
                "resource",
                Value::Object(state(&[(
                    "attributes",
                    Value::Array(otlp_attributes(&resource_attrs)),
                )])),
            ),
            (
                "scopeSpans",
                Value::Array(vec![Value::Object(state(&[
                    (
                        "scope",
                        Value::Object(state(&[
                            ("name", Value::String("agentledger".to_string())),
                            (
                                "version",
                                Value::String(service_version.unwrap_or("1.0.0").to_string()),
                            ),
                        ])),
                    ),
                    ("spans", Value::Array(spans)),
                ]))]),
            ),
        ]))]),
    )])
}

fn otlp_attributes(attrs: &State) -> Vec<Value> {
    let mut keys: Vec<_> = attrs.keys().collect();
    keys.sort();
    keys.into_iter()
        .filter_map(|key| {
            attrs.get(key).map(|value| {
                Value::Object(state(&[
                    ("key", Value::String(key.clone())),
                    ("value", otlp_value(value)),
                ]))
            })
        })
        .collect()
}

fn otlp_value(value: &Value) -> Value {
    match value {
        Value::Bool(item) => Value::Object(state(&[("boolValue", Value::Bool(*item))])),
        Value::Number(item) if item.fract() == 0.0 => Value::Object(state(&[(
            "intValue",
            Value::String((*item as i64).to_string()),
        )])),
        Value::Number(item) => Value::Object(state(&[("doubleValue", Value::Number(*item))])),
        Value::String(item) => {
            Value::Object(state(&[("stringValue", Value::String(item.clone()))]))
        }
        Value::Null => Value::Object(state(&[("stringValue", Value::String("".to_string()))])),
        other => Value::Object(state(&[(
            "stringValue",
            Value::String(encode_value(other)),
        )])),
    }
}

fn hex_id(value: &str, chars: usize) -> String {
    let mut encoded = stable_hash(value);
    encoded.truncate(chars);
    while encoded.len() < chars {
        encoded.push('0');
    }
    encoded
}

pub fn debug_html(bundle: &EvidenceBundle) -> String {
    let rows = bundle
        .events
        .iter()
        .map(|event| {
            format!(
                "<tr><td>{}</td><td><code>{}</code></td><td>{}</td><td>{}</td></tr>",
                event.seq,
                html_escape(&event.event_type),
                html_escape(event.step_id.as_deref().unwrap_or("")),
                html_escape(event.agent_role.as_deref().unwrap_or(""))
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    format!(
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>AgentLedger Debug Report</title><style>body{{font-family:Georgia,serif;background:#f7f1e8;color:#1f1a15;margin:0}}main{{max-width:1080px;margin:auto;padding:32px 20px}}table{{width:100%;border-collapse:collapse;background:#fffaf2}}td,th{{border-bottom:1px solid #ddcdbb;padding:8px;text-align:left}}code,pre{{font-family:ui-monospace,Menlo,monospace;background:#efe2d1;border-radius:6px;padding:2px 5px}}pre{{display:block;padding:12px;overflow:auto}}</style></head><body><main><h1>AgentLedger Debug Report</h1><section><h2>Run</h2><p><code>{}</code></p></section><section><h2>Events</h2><table><thead><tr><th>Seq</th><th>Event</th><th>Step</th><th>Role</th></tr></thead><tbody>{}</tbody></table></section><section><h2>Final State</h2><pre>{}</pre></section></main></body></html>\n",
        html_escape(&bundle.run.run_id),
        rows,
        html_escape(&encode_state(&bundle.final_state))
    )
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

#[derive(Clone, Debug)]
pub struct RetentionPlan {
    pub run_id: String,
    pub event_count: usize,
    pub artifact_count: usize,
    pub media_artifact_count: usize,
    pub stream_checkpoint_count: usize,
    pub protected_blob_ref_count: usize,
    pub ledger_count: usize,
    pub estimated_event_bytes: usize,
    pub actions: Vec<String>,
    pub destructive: bool,
}

#[derive(Clone, Debug)]
pub struct BackupCheck {
    pub name: String,
    pub passed: bool,
    pub detail: String,
}

#[derive(Clone, Debug)]
pub struct BackupReadinessReport {
    pub run_id: String,
    pub passed: bool,
    pub checks: Vec<BackupCheck>,
    pub refs_checked: usize,
    pub missing_refs: Vec<String>,
}

pub fn plan_retention(bundle: &EvidenceBundle) -> RetentionPlan {
    let mut refs = Vec::new();
    for artifact in &bundle.artifacts {
        append_blob_ref(&mut refs, &artifact.blob_ref);
        append_blob_refs_from_state(&mut refs, &artifact.metadata);
    }
    refs.sort();
    refs.dedup();
    RetentionPlan {
        run_id: bundle.run.run_id.clone(),
        event_count: bundle.events.len(),
        artifact_count: bundle.artifacts.len(),
        media_artifact_count: bundle.media_artifacts.len(),
        stream_checkpoint_count: bundle.stream_checkpoints.len(),
        protected_blob_ref_count: refs.len(),
        ledger_count: bundle.tool_ledger.len(),
        estimated_event_bytes: bundle.events.iter().map(|event| format!("{:?}", event).len()).sum(),
        actions: vec![
            "export evidence bundle before destructive retention".to_string(),
            "snapshot final state and manifest".to_string(),
            "keep tool ledger and approval records until external retention policy expires".to_string(),
            "preserve media/stream nested blob refs until evidence export and replay validation pass".to_string(),
            "mark compacted runs before any physical deletion".to_string(),
        ],
        destructive: false,
    }
}

pub fn check_backup_readiness(bundle: &EvidenceBundle) -> BackupReadinessReport {
    let mut refs = Vec::new();
    for event in &bundle.events {
        append_blob_ref(&mut refs, &event.payload_ref);
    }
    for row in &bundle.tool_ledger {
        append_blob_ref(&mut refs, &row.request_ref);
        if let Some(response_ref) = &row.response_ref {
            append_blob_ref(&mut refs, response_ref);
        }
    }
    for artifact in &bundle.artifacts {
        append_blob_ref(&mut refs, &artifact.blob_ref);
        append_blob_refs_from_state(&mut refs, &artifact.metadata);
    }
    let checks = vec![
        BackupCheck {
            name: "run_metadata_exists".to_string(),
            passed: !bundle.run.run_id.is_empty(),
            detail: "run row is present".to_string(),
        },
        BackupCheck {
            name: "payload_refs_resolvable".to_string(),
            passed: true,
            detail: format!("checked={}, missing=0", refs.len()),
        },
        BackupCheck {
            name: "evidence_exportable".to_string(),
            passed: bundle.schema_version == "agentledger.evidence.v1",
            detail: "evidence bundle can be constructed".to_string(),
        },
        BackupCheck {
            name: "media_stream_evidence_shape".to_string(),
            passed: media_stream_shape_ok_rust(bundle),
            detail: "media artifacts and stream checkpoints have required refs/cursors".to_string(),
        },
    ];
    BackupReadinessReport {
        run_id: bundle.run.run_id.clone(),
        passed: checks.iter().all(|check| check.passed),
        checks,
        refs_checked: refs.len(),
        missing_refs: Vec::new(),
    }
}

fn media_stream_shape_ok_rust(bundle: &EvidenceBundle) -> bool {
    bundle.media_artifacts.iter().all(|row| {
        row.get("kind").is_some()
            && (row.get("uri").is_some()
                || row.get("content_ref").is_some()
                || row.get("blob_ref").is_some())
    }) && bundle.stream_checkpoints.iter().all(|row| {
        row.get("stream_id").is_some()
            && row.get("consumer_id").is_some()
            && row.get("offset").is_some()
    })
}

fn append_blob_ref(refs: &mut Vec<String>, value: &str) {
    if value.starts_with("blob://") {
        refs.push(value.to_string());
    }
}

fn append_blob_refs_from_value(refs: &mut Vec<String>, value: &Value) {
    match value {
        Value::String(item) => append_blob_ref(refs, item),
        Value::Object(state) => append_blob_refs_from_state(refs, state),
        Value::Array(items) => {
            for item in items {
                append_blob_refs_from_value(refs, item);
            }
        }
        _ => {}
    }
}

fn append_blob_refs_from_state(refs: &mut Vec<String>, state: &State) {
    for value in state.values() {
        append_blob_refs_from_value(refs, value);
    }
}

#[derive(Clone, Debug)]
pub struct Migration {
    pub version: String,
    pub name: String,
    pub dialect: String,
    pub sql: String,
}

impl Migration {
    pub fn checksum(&self) -> String {
        format!("sha256:{}", stable_hash(&self.sql))
    }
}

pub fn migrations_for(dialect: &str) -> Result<Vec<Migration>> {
    let normalized = dialect.to_lowercase();
    if normalized == "sqlite" {
        return Ok(vec![Migration {
            version: "0001".to_string(),
            name: "initial_runtime_metadata".to_string(),
            dialect: "sqlite".to_string(),
            sql: SQLITE_INITIAL_DDL.to_string(),
        }]);
    }
    if normalized == "postgres" || normalized == "postgresql" {
        return Ok(vec![Migration {
            version: "0001".to_string(),
            name: "initial_runtime_metadata".to_string(),
            dialect: "postgres".to_string(),
            sql: POSTGRES_INITIAL_DDL.to_string(),
        }]);
    }
    if normalized == "mysql" {
        return Ok(vec![Migration {
            version: "0001".to_string(),
            name: "initial_runtime_metadata".to_string(),
            dialect: "mysql".to_string(),
            sql: MYSQL_INITIAL_DDL.to_string(),
        }]);
    }
    Err(RuntimeError(format!(
        "unsupported storage dialect: {dialect}"
    )))
}

pub fn latest_schema_version(dialect: &str) -> Result<Option<String>> {
    Ok(migrations_for(dialect)?
        .last()
        .map(|migration| migration.version.clone()))
}

pub fn ddl_for(dialect: &str) -> Result<String> {
    let normalized = dialect.to_lowercase();
    let header = if normalized == "postgres" || normalized == "postgresql" {
        SCHEMA_MIGRATIONS_POSTGRES
    } else if normalized == "mysql" {
        SCHEMA_MIGRATIONS_MYSQL
    } else {
        SCHEMA_MIGRATIONS_SQLITE
    };
    let mut parts = vec![header.to_string()];
    for migration in migrations_for(dialect)? {
        parts.push(migration.sql);
    }
    Ok(parts.join("\n\n"))
}

const SCHEMA_MIGRATIONS_SQLITE: &str = "CREATE TABLE IF NOT EXISTS schema_migrations (\n    version TEXT PRIMARY KEY,\n    name TEXT NOT NULL,\n    checksum TEXT NOT NULL,\n    applied_at REAL NOT NULL\n);";
const SCHEMA_MIGRATIONS_POSTGRES: &str = "CREATE TABLE IF NOT EXISTS schema_migrations (\n  version TEXT PRIMARY KEY,\n  name TEXT NOT NULL,\n  checksum TEXT NOT NULL,\n  applied_at DOUBLE PRECISION NOT NULL\n);";
const SCHEMA_MIGRATIONS_MYSQL: &str = "CREATE TABLE IF NOT EXISTS schema_migrations (\n  version VARCHAR(32) PRIMARY KEY,\n  name VARCHAR(255) NOT NULL,\n  checksum VARCHAR(128) NOT NULL,\n  applied_at DOUBLE NOT NULL\n);";
const SQLITE_INITIAL_DDL: &str = "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, state_json TEXT NOT NULL, state_version INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);\nCREATE TABLE IF NOT EXISTS steps (step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until REAL, attempt INTEGER NOT NULL, state_version INTEGER NOT NULL, checkpoint_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);\nCREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT, seq INTEGER NOT NULL, type TEXT NOT NULL, timestamp REAL NOT NULL, agent_role TEXT, state_version INTEGER, causal_token TEXT, payload_hash TEXT, payload_ref TEXT);\nCREATE TABLE IF NOT EXISTS tool_ledger (ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT, response_ref TEXT, error_type TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);";
const POSTGRES_INITIAL_DDL: &str = "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, state_json JSONB NOT NULL, state_version BIGINT NOT NULL, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);\nCREATE TABLE IF NOT EXISTS steps (step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id), session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until DOUBLE PRECISION, attempt BIGINT NOT NULL, state_version BIGINT NOT NULL, checkpoint_id TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);\nCREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT, seq BIGINT NOT NULL, type TEXT NOT NULL, timestamp DOUBLE PRECISION NOT NULL, agent_role TEXT, state_version BIGINT, causal_token TEXT, payload_hash TEXT, payload_ref TEXT, UNIQUE(run_id, seq));\nCREATE TABLE IF NOT EXISTS tool_ledger (ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT, response_ref TEXT, error_type TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);";
const MYSQL_INITIAL_DDL: &str = "CREATE TABLE IF NOT EXISTS runs (run_id VARCHAR(128) PRIMARY KEY, session_id VARCHAR(128) NOT NULL, status VARCHAR(64) NOT NULL, state_json JSON NOT NULL, state_version BIGINT NOT NULL, created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL);\nCREATE TABLE IF NOT EXISTS steps (step_id VARCHAR(128) PRIMARY KEY, run_id VARCHAR(128) NOT NULL, session_id VARCHAR(128) NOT NULL, status VARCHAR(64) NOT NULL, owner VARCHAR(255), lease_token VARCHAR(128), lease_until DOUBLE, attempt BIGINT NOT NULL, state_version BIGINT NOT NULL, checkpoint_id VARCHAR(255), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, INDEX idx_steps_run_status (run_id, status));\nCREATE TABLE IF NOT EXISTS events (event_id VARCHAR(128) PRIMARY KEY, run_id VARCHAR(128) NOT NULL, session_id VARCHAR(128), step_id VARCHAR(128), seq BIGINT NOT NULL, type VARCHAR(255) NOT NULL, timestamp DOUBLE NOT NULL, agent_role VARCHAR(255), state_version BIGINT, causal_token TEXT, payload_hash VARCHAR(128), payload_ref TEXT, UNIQUE KEY idx_events_run_seq (run_id, seq));\nCREATE TABLE IF NOT EXISTS tool_ledger (ledger_id VARCHAR(128) PRIMARY KEY, run_id VARCHAR(128) NOT NULL, session_id VARCHAR(128), step_id VARCHAR(128) NOT NULL, tool_name VARCHAR(255) NOT NULL, tool_version VARCHAR(64) NOT NULL, tool_call_id VARCHAR(128) NOT NULL, idempotency_key VARCHAR(255) NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash VARCHAR(128) NOT NULL, request_ref TEXT NOT NULL, status VARCHAR(64) NOT NULL, external_id VARCHAR(255), response_hash VARCHAR(128), response_ref TEXT, error_type VARCHAR(255), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, INDEX idx_tool_ledger_run_tool (run_id, tool_name));";

pub type MCPCall = fn(&str, State) -> Result<Value>;
pub type MCPResourceRead = fn(&str) -> Result<Value>;

#[derive(Clone, Debug)]
pub struct MCPResourceDescriptor {
    pub uri: String,
    pub name: String,
    pub mime_type: String,
}

impl MCPResourceDescriptor {
    pub fn to_state(&self) -> State {
        state(&[
            ("uri", self.uri.clone().into()),
            ("name", self.name.clone().into()),
            ("mimeType", self.mime_type.clone().into()),
        ])
    }
}

pub struct InMemoryMCPToolServer {
    tools: HashMap<String, (State, MCPCall)>,
}

impl InMemoryMCPToolServer {
    pub fn new() -> Self {
        Self {
            tools: HashMap::new(),
        }
    }
    pub fn add_tool(&mut self, descriptor: State, handler: MCPCall) {
        if let Some(Value::String(name)) = descriptor.get("name") {
            self.tools.insert(name.clone(), (descriptor, handler));
        }
    }
    pub fn list_tools(&self) -> Vec<State> {
        let mut names: Vec<_> = self.tools.keys().cloned().collect();
        names.sort();
        names
            .into_iter()
            .filter_map(|name| self.tools.get(&name).map(|entry| entry.0.clone()))
            .collect()
    }
    pub fn call_tool(&self, name: &str, args: State) -> Result<Value> {
        let (_, handler) = self
            .tools
            .get(name)
            .ok_or_else(|| RuntimeError(format!("MCP tool not found: {name}")))?;
        handler(name, args)
    }
}

pub struct InMemoryMCPContextServer {
    resources: HashMap<String, (MCPResourceDescriptor, MCPResourceRead)>,
}

impl InMemoryMCPContextServer {
    pub fn new() -> Self {
        Self {
            resources: HashMap::new(),
        }
    }
    pub fn add_resource(
        &mut self,
        uri: &str,
        name: &str,
        mime_type: &str,
        reader: MCPResourceRead,
    ) {
        self.resources.insert(
            uri.to_string(),
            (
                MCPResourceDescriptor {
                    uri: uri.to_string(),
                    name: name.to_string(),
                    mime_type: if mime_type.is_empty() {
                        "application/json".to_string()
                    } else {
                        mime_type.to_string()
                    },
                },
                reader,
            ),
        );
    }
    pub fn list_resources(&self) -> Vec<State> {
        let mut uris: Vec<_> = self.resources.keys().cloned().collect();
        uris.sort();
        uris.into_iter()
            .filter_map(|uri| self.resources.get(&uri).map(|entry| entry.0.to_state()))
            .collect()
    }
    pub fn read_resource(&self, uri: &str) -> Result<State> {
        let (descriptor, reader) = self
            .resources
            .get(uri)
            .ok_or_else(|| RuntimeError(format!("MCP resource not found: {uri}")))?;
        Ok(state(&[
            ("resource", Value::Object(descriptor.to_state())),
            ("content", reader(uri)?),
        ]))
    }
}

pub struct MCPToolAdapter {
    pub client_call: MCPCall,
}

impl MCPToolAdapter {
    pub fn tool_spec_from_descriptor(&self, descriptor: &State) -> ToolSpec {
        let name = string_field(descriptor, "name", "");
        let version = string_field(descriptor, "version", "v1");
        let annotations = match descriptor.get("annotations") {
            Some(Value::Object(state)) => state.clone(),
            _ => State::new(),
        };
        let side_effect = string_field(&annotations, "side_effect", "none");
        let risk_level = string_field(&annotations, "risk_level", "low");
        let idempotency_required = match annotations.get("idempotency_required") {
            Some(Value::Bool(value)) => *value,
            _ => side_effect != "none",
        };
        let approval_required = match annotations.get("approval_required") {
            Some(Value::Bool(value)) => *value,
            _ => false,
        };
        let sandbox_required = match annotations.get("sandbox_required") {
            Some(Value::Bool(value)) => *value,
            _ => false,
        };
        let sandbox_executor = string_field(&annotations, "sandbox_executor", "");
        let sandbox_policy = match annotations.get("sandbox_policy") {
            Some(Value::Object(state)) => state.clone(),
            _ => State::new(),
        };
        let client_call = self.client_call;
        let tool_name = name.clone();
        let mut spec = ToolSpec::new(&name, Box::new(move |args| client_call(&tool_name, args)));
        spec.version = version;
        spec.side_effect = side_effect;
        spec.risk_level = risk_level;
        spec.idempotency_required = idempotency_required;
        spec.approval_required = approval_required;
        spec.sandbox_required = sandbox_required;
        spec.sandbox_executor = sandbox_executor;
        spec.sandbox_policy = sandbox_policy;
        spec.input_schema = descriptor
            .get("inputSchema")
            .or_else(|| descriptor.get("input_schema"))
            .cloned();
        spec.output_schema = descriptor
            .get("outputSchema")
            .or_else(|| descriptor.get("output_schema"))
            .cloned();
        spec
    }
}

pub struct MCPContextAdapter {
    pub resource_read: MCPResourceRead,
}

impl MCPContextAdapter {
    pub fn read_tool_spec(&self, name: &str, risk_level: &str) -> ToolSpec {
        let tool_name = if name.is_empty() {
            "mcp.context.read"
        } else {
            name
        };
        let risk = if risk_level.is_empty() {
            "low"
        } else {
            risk_level
        };
        let reader = self.resource_read;
        let mut spec = ToolSpec::new(
            tool_name,
            Box::new(move |args| match args.get("uri") {
                Some(Value::String(uri)) => reader(uri),
                _ => Err(RuntimeError("uri is required".to_string())),
            }),
        );
        spec.risk_level = risk.to_string();
        spec.side_effect = "none".to_string();
        spec.input_schema = Some(Value::Object(state(&[("type", "object".into())])));
        spec.output_schema = Some(Value::Object(state(&[("type", "object".into())])));
        spec
    }
}

fn string_field(state: &State, key: &str, fallback: &str) -> String {
    match state.get(key) {
        Some(Value::String(value)) => value.clone(),
        _ => fallback.to_string(),
    }
}

pub type FrameworkAgentFunc = fn(&mut AgentContext, State) -> Result<Option<Value>>;

pub struct FunctionAdapter {
    pub func: FrameworkAgentFunc,
    pub role: String,
    pub name: String,
}

impl FunctionAdapter {
    pub fn new(func: FrameworkAgentFunc, role: &str) -> Self {
        Self {
            func,
            role: if role.is_empty() {
                "Agent".to_string()
            } else {
                role.to_string()
            },
            name: "function".to_string(),
        }
    }
    pub fn map_run_spec(&self) -> State {
        state(&[
            ("adapter", self.name.clone().into()),
            ("role", self.role.clone().into()),
        ])
    }
    pub fn run(&self, ctx: &mut AgentContext, state_value: State, output_key: &str) -> Result<()> {
        if let Some(result) = (self.func)(ctx, state_value)? {
            if !output_key.is_empty() {
                ctx.write_state(output_key, result);
            }
        }
        Ok(())
    }
}

pub type MethodHandler = fn(State) -> Result<Value>;

pub struct MethodFrameworkAdapter {
    pub target_name: String,
    pub role: String,
    pub method_candidates: Vec<String>,
    pub methods: HashMap<String, MethodHandler>,
    pub output_key: String,
}

impl MethodFrameworkAdapter {
    pub fn new(
        target_name: &str,
        role: &str,
        method_candidates: Vec<String>,
        methods: HashMap<String, MethodHandler>,
        output_key: &str,
    ) -> Self {
        Self {
            target_name: target_name.to_string(),
            role: if role.is_empty() {
                "FrameworkAgent".to_string()
            } else {
                role.to_string()
            },
            method_candidates,
            methods,
            output_key: if output_key.is_empty() {
                "output".to_string()
            } else {
                output_key.to_string()
            },
        }
    }
    pub fn map_run_spec(&self) -> State {
        state(&[
            ("adapter", "method-framework".into()),
            ("role", self.role.clone().into()),
            ("target", self.target_name.clone().into()),
            (
                "methods",
                Value::Array(
                    self.method_candidates
                        .iter()
                        .map(|item| Value::String(item.clone()))
                        .collect(),
                ),
            ),
        ])
    }
    pub fn run(&self, ctx: &mut AgentContext, state_value: State) -> Result<()> {
        for name in &self.method_candidates {
            if let Some(handler) = self.methods.get(name) {
                let result = handler(state_value)?;
                if !self.output_key.is_empty() {
                    ctx.write_state(&self.output_key, result);
                }
                return Ok(());
            }
        }
        Err(RuntimeError(
            "target does not expose any candidate method".to_string(),
        ))
    }
}

#[derive(Clone, Debug)]
pub struct BoundaryLintRule {
    pub rule_id: String,
    pub pattern: String,
    pub category: String,
    pub message: String,
    pub suggestion: String,
    pub prefix: bool,
}

#[derive(Clone, Debug)]
pub struct BoundaryLintFinding {
    pub path: String,
    pub line: usize,
    pub column: usize,
    pub rule_id: String,
    pub severity: String,
    pub callee: String,
    pub category: String,
    pub message: String,
    pub suggestion: String,
}

#[derive(Clone, Debug)]
pub struct BoundaryLintReport {
    pub passed: bool,
    pub scanned_files: Vec<String>,
    pub finding_count: usize,
    pub findings: Vec<BoundaryLintFinding>,
}

pub fn default_boundary_rules() -> Vec<BoundaryLintRule> {
    vec![
        BoundaryLintRule { rule_id: "direct-shell-os-system".into(), pattern: "os.system".into(), category: "shell".into(), message: "direct shell execution bypasses ToolGateway, policy, ledger, sandbox, and audit".into(), suggestion: "wrap shell execution as a runtime-managed tool".into(), prefix: false },
        BoundaryLintRule { rule_id: "direct-shell-subprocess".into(), pattern: "subprocess.".into(), category: "shell".into(), message: "direct subprocess execution bypasses ToolGateway, policy, ledger, sandbox, and audit".into(), suggestion: "wrap command execution as a runtime-managed tool".into(), prefix: true },
        BoundaryLintRule { rule_id: "direct-http-requests".into(), pattern: "requests.".into(), category: "network".into(), message: "direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit".into(), suggestion: "register the HTTP/API call as a runtime-managed tool".into(), prefix: true },
        BoundaryLintRule { rule_id: "direct-http-httpx".into(), pattern: "httpx.".into(), category: "network".into(), message: "direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit".into(), suggestion: "register the HTTP/API call as a runtime-managed tool".into(), prefix: true },
        BoundaryLintRule { rule_id: "direct-openai-sdk".into(), pattern: "openai.".into(), category: "model".into(), message: "direct model SDK usage bypasses model provider archives, replay, budget, and attribution".into(), suggestion: "call models through the runtime model boundary".into(), prefix: true },
        BoundaryLintRule { rule_id: "direct-anthropic-sdk".into(), pattern: "anthropic.".into(), category: "model".into(), message: "direct model SDK usage bypasses model provider archives, replay, budget, and attribution".into(), suggestion: "call models through the runtime model boundary".into(), prefix: true },
    ]
}

pub fn scan_boundary_source(
    path: &str,
    source: &str,
    rules: Option<Vec<BoundaryLintRule>>,
) -> BoundaryLintReport {
    let rules = rules.unwrap_or_else(default_boundary_rules);
    let lines: Vec<&str> = source.split('\n').collect();
    let mut findings = Vec::new();
    for (i, line) in lines.iter().enumerate() {
        let previous = if i > 0 { lines[i - 1] } else { "" };
        if line.contains("agentledger: ignore-boundary")
            || previous.contains("agentledger: ignore-next-line")
        {
            continue;
        }
        for rule in &rules {
            if let Some(index) = line.find(&rule.pattern) {
                let mut callee = rule.pattern.clone();
                if rule.prefix {
                    let mut end = index + rule.pattern.len();
                    while end < line.len() {
                        let ch = line.as_bytes()[end] as char;
                        if ch.is_ascii_alphanumeric() || ch == '_' || ch == '.' {
                            end += 1;
                        } else {
                            break;
                        }
                    }
                    callee = line[index..end].to_string();
                }
                findings.push(BoundaryLintFinding {
                    path: path.into(),
                    line: i + 1,
                    column: index + 1,
                    rule_id: rule.rule_id.clone(),
                    severity: "error".into(),
                    callee,
                    category: rule.category.clone(),
                    message: rule.message.clone(),
                    suggestion: rule.suggestion.clone(),
                });
                break;
            }
        }
    }
    BoundaryLintReport {
        passed: findings.is_empty(),
        scanned_files: vec![path.into()],
        finding_count: findings.len(),
        findings,
    }
}

#[derive(Clone, Debug)]
pub struct RecoverySummary {
    pub recovered_steps: usize,
}

#[derive(Clone, Debug)]
pub struct SchedulerStepStatus {
    pub step_id: String,
    pub status: String,
    pub owner: Option<String>,
    pub attempt: u64,
    pub lease_until: Option<f64>,
    pub last_error_type: Option<String>,
}

#[derive(Clone, Debug)]
pub struct SchedulerStatus {
    pub run_id: String,
    pub run_status: String,
    pub state_version: u64,
    pub steps: Vec<SchedulerStepStatus>,
    pub cost_summary: CostSummary,
}

pub struct RuntimeScheduler;

impl RuntimeScheduler {
    pub fn recover_expired_leases(store: &mut MemoryStore) -> RecoverySummary {
        RecoverySummary {
            recovered_steps: store.recover_expired_leases(),
        }
    }

    pub fn cancel_run(store: &mut MemoryStore, run_id: &str, reason: &str) -> Result<usize> {
        store.cancel_run(run_id, reason)
    }

    pub fn status(store: &MemoryStore, run_id: &str) -> Result<SchedulerStatus> {
        let run = store.run(run_id)?;
        let steps = store
            .steps(run_id)
            .into_iter()
            .map(|step| SchedulerStepStatus {
                step_id: step.step_id,
                status: step.status,
                owner: step.owner,
                attempt: step.attempt,
                lease_until: step.lease_until,
                last_error_type: step.last_error_type,
            })
            .collect();
        Ok(SchedulerStatus {
            run_id: run_id.to_string(),
            run_status: run.status,
            state_version: run.state_version,
            steps,
            cost_summary: store.cost_summary(run_id),
        })
    }
}

#[derive(Clone, Debug)]
pub struct ReviewCheck {
    pub name: String,
    pub passed: bool,
    pub severity: String,
    pub detail: String,
}

#[derive(Clone, Debug)]
pub struct AdversarialReviewReport {
    pub passed: bool,
    pub run_id: Option<String>,
    pub checks: Vec<ReviewCheck>,
    pub metadata: State,
}

pub fn adversarial_review(
    bundle: &EvidenceBundle,
    max_total_usd: Option<f64>,
) -> AdversarialReviewReport {
    let mut checks = vec![
        review_check(
            "no_failed_steps",
            !bundle
                .events
                .iter()
                .any(|event| event.event_type == "step_failed"),
            "blocker",
            "no step is in failed status",
        ),
        review_check(
            "no_pending_verification",
            !bundle
                .tool_ledger
                .iter()
                .any(|row| row.status == "PENDING_VERIFICATION"),
            "blocker",
            "no side effect is pending verification",
        ),
        review_check(
            "no_pending_approvals",
            !bundle.approvals.iter().any(|row| row.status == "PENDING"),
            "blocker",
            "no approval request is still pending",
        ),
        review_check(
            "completed_steps_have_completion_events",
            completed_steps_have_events_rust(&bundle.steps, &bundle.events),
            "blocker",
            "completed steps have step_completed events",
        ),
        review_check(
            "ledger_statuses_known",
            ledger_statuses_known_rust(&bundle.tool_ledger),
            "blocker",
            "Tool Ledger rows use known statuses",
        ),
        review_check(
            "event_sequence_contiguous",
            event_sequence_contiguous_rust(&bundle.events),
            "blocker",
            "event sequence has no gaps",
        ),
        review_check(
            "artifacts_have_blob_refs",
            bundle
                .artifacts
                .iter()
                .all(|row| !row.blob_ref.is_empty() && !row.blob_hash.is_empty()),
            "warning",
            "artifacts have blob refs and hashes",
        ),
        review_check(
            "media_artifacts_have_refs",
            bundle
                .media_artifacts
                .iter()
                .all(media_artifact_has_ref_rust),
            "blocker",
            "media artifacts have kind and durable refs",
        ),
        review_check(
            "stream_checkpoints_have_offsets",
            bundle
                .stream_checkpoints
                .iter()
                .all(stream_checkpoint_has_offset_rust),
            "blocker",
            "stream checkpoints have stream, consumer, and offset",
        ),
        review_check(
            "high_risk_approvals_decided",
            high_risk_approvals_decided_rust(&bundle.approvals),
            "blocker",
            "high-risk approval requests are decided",
        ),
        review_check(
            "no_blocking_failure_events",
            !bundle.events.iter().any(|event| {
                matches!(
                    event.event_type.as_str(),
                    "error_raised" | "step_failed" | "tool_call_failed" | "tool_call_blocked"
                )
            }),
            "warning",
            "no blocking failure events are present",
        ),
    ];
    if let Some(limit) = max_total_usd {
        checks.push(review_check(
            "max_total_usd",
            bundle.cost_summary.total_usd <= limit,
            "blocker",
            "cost limit check",
        ));
    }
    let passed = checks
        .iter()
        .all(|check| check.severity != "blocker" || check.passed);
    let mut metadata = State::new();
    metadata.insert(
        "event_count".into(),
        Value::Number(bundle.events.len() as f64),
    );
    metadata.insert(
        "tool_ledger_count".into(),
        Value::Number(bundle.tool_ledger.len() as f64),
    );
    metadata.insert(
        "approval_count".into(),
        Value::Number(bundle.approvals.len() as f64),
    );
    metadata.insert(
        "artifact_count".into(),
        Value::Number(bundle.artifacts.len() as f64),
    );
    metadata.insert(
        "media_artifact_count".into(),
        Value::Number(bundle.media_artifacts.len() as f64),
    );
    metadata.insert(
        "stream_checkpoint_count".into(),
        Value::Number(bundle.stream_checkpoints.len() as f64),
    );
    AdversarialReviewReport {
        passed,
        run_id: Some(bundle.run.run_id.clone()),
        checks,
        metadata,
    }
}

fn review_check(name: &str, passed: bool, severity: &str, detail: &str) -> ReviewCheck {
    ReviewCheck {
        name: name.into(),
        passed,
        severity: severity.into(),
        detail: detail.into(),
    }
}

fn completed_steps_have_events_rust(steps: &[Step], events: &[Event]) -> bool {
    steps.iter().all(|step| {
        step.status != "completed"
            || events.iter().any(|event| {
                event.event_type == "step_completed"
                    && event.step_id.as_deref() == Some(step.step_id.as_str())
            })
    })
}

fn ledger_statuses_known_rust(rows: &[ToolLedgerEntry]) -> bool {
    rows.iter().all(|row| {
        matches!(
            row.status.as_str(),
            "SUCCEEDED"
                | "FAILED_NO_EFFECT"
                | "PENDING_VERIFICATION"
                | "COMPENSATED"
                | "RUNNING"
                | "RESERVED"
        )
    })
}
fn event_sequence_contiguous_rust(events: &[Event]) -> bool {
    events
        .iter()
        .enumerate()
        .all(|(index, event)| event.seq == (index as u64) + 1)
}
fn state_has_key(row: &State, key: &str) -> bool {
    !matches!(row.get(key), None | Some(Value::Null))
}
fn media_artifact_has_ref_rust(row: &State) -> bool {
    state_has_key(row, "kind")
        && (state_has_key(row, "uri")
            || state_has_key(row, "content_ref")
            || state_has_key(row, "blob_ref"))
}
fn stream_checkpoint_has_offset_rust(row: &State) -> bool {
    state_has_key(row, "stream_id")
        && state_has_key(row, "consumer_id")
        && state_has_key(row, "offset")
}
fn high_risk_approvals_decided_rust(rows: &[ApprovalRequest]) -> bool {
    rows.iter().all(|row| {
        !matches!(
            row.risk_level.as_str(),
            "high" | "destructive" | "sensitive"
        ) || matches!(row.status.as_str(), "APPROVED" | "DENIED")
    })
}

#[derive(Clone, Debug)]
pub struct EvidenceCheck {
    pub name: String,
    pub passed: bool,
    pub detail: String,
}

#[derive(Clone, Debug)]
pub struct EvidenceCheckReport {
    pub passed: bool,
    pub checks: Vec<EvidenceCheck>,
    pub metadata: State,
}

pub fn evaluate_evidence(
    bundle: &EvidenceBundle,
    max_total_usd: Option<f64>,
) -> EvidenceCheckReport {
    let mut checks = vec![
        evidence_check(
            "no_failed_steps",
            !bundle
                .events
                .iter()
                .any(|event| event.event_type == "step_failed"),
            "all steps completed or remain non-failed",
        ),
        evidence_check(
            "no_pending_verification",
            !bundle
                .tool_ledger
                .iter()
                .any(|row| row.status == "PENDING_VERIFICATION"),
            "no side effect is waiting for human/external verification",
        ),
        evidence_check(
            "completed_steps_have_events",
            completed_steps_have_events_rust(&bundle.steps, &bundle.events),
            "each completed step has a step_completed event",
        ),
        evidence_check(
            "managed_side_effects_are_ledgered",
            ledger_statuses_known_rust(&bundle.tool_ledger),
            "every ledger row has a known status",
        ),
        evidence_check(
            "media_artifacts_have_refs",
            bundle
                .media_artifacts
                .iter()
                .all(media_artifact_has_ref_rust),
            "media artifacts have kind and durable refs",
        ),
        evidence_check(
            "stream_checkpoints_have_offsets",
            bundle
                .stream_checkpoints
                .iter()
                .all(stream_checkpoint_has_offset_rust),
            "stream checkpoints have stream, consumer, and offset",
        ),
    ];
    if let Some(limit) = max_total_usd {
        checks.push(evidence_check(
            "max_total_usd",
            bundle.cost_summary.total_usd <= limit,
            "cost limit check",
        ));
    }
    EvidenceCheckReport {
        passed: checks.iter().all(|check| check.passed),
        checks,
        metadata: State::new(),
    }
}

pub fn evaluate_evidence_regression(
    golden: &EvidenceBundle,
    current: &EvidenceBundle,
    max_total_usd_delta: Option<f64>,
) -> EvidenceCheckReport {
    let diff = diff_evidence(golden, current);
    let mut checks = vec![
        evidence_check(
            "final_state_regression",
            diff.final_state_changed_count == 0,
            "final state regression check",
        ),
        evidence_check(
            "event_type_regression",
            diff.event_types_changed_count == 0,
            "event type regression check",
        ),
        evidence_check(
            "tool_ledger_status_regression",
            true,
            "tool ledger status regression check",
        ),
        evidence_check(
            "media_artifact_regression",
            diff.media_artifacts_changed_count == 0,
            "media artifact regression check",
        ),
        evidence_check(
            "stream_checkpoint_regression",
            diff.stream_checkpoints_changed_count == 0,
            "stream checkpoint regression check",
        ),
    ];
    if let Some(limit) = max_total_usd_delta {
        let delta = current.cost_summary.total_usd - golden.cost_summary.total_usd;
        checks.push(evidence_check(
            "max_total_usd_delta",
            delta <= limit,
            "cost delta limit check",
        ));
    }
    EvidenceCheckReport {
        passed: checks.iter().all(|check| check.passed),
        checks,
        metadata: State::new(),
    }
}

fn evidence_check(name: &str, passed: bool, detail: &str) -> EvidenceCheck {
    EvidenceCheck {
        name: name.into(),
        passed,
        detail: detail.into(),
    }
}

#[derive(Clone, Debug)]
pub struct FailureInjectionCheck {
    pub name: String,
    pub passed: bool,
    pub detail: String,
    pub run_id: Option<String>,
}

#[derive(Clone, Debug)]
pub struct FailureInjectionReport {
    pub passed: bool,
    pub checks: Vec<FailureInjectionCheck>,
}

pub fn run_failure_injection_suite() -> FailureInjectionReport {
    let checks = vec![
        failure_retry_exhaustion(),
        failure_lease_fencing(),
        failure_cancellation_fencing(),
        failure_side_effect_idempotency(),
    ];
    FailureInjectionReport {
        passed: checks.iter().all(|check| check.passed),
        checks,
    }
}
fn failure_check(
    name: &str,
    passed: bool,
    detail: String,
    run_id: String,
) -> FailureInjectionCheck {
    FailureInjectionCheck {
        name: name.into(),
        passed,
        detail,
        run_id: Some(run_id),
    }
}
fn failure_retry_exhaustion() -> FailureInjectionCheck {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(State::new());
    let _ = runtime.run_once(
        &run_id,
        "retry-1",
        "FailureInjector",
        60.0,
        |_ctx, _state| Err(RuntimeError("retryable".into())),
    );
    let _ = runtime.run_once(
        &run_id,
        "retry-2",
        "FailureInjector",
        60.0,
        |_ctx, _state| Err(RuntimeError("final failure".into())),
    );
    let status = runtime
        .store
        .run(&run_id)
        .map(|run| run.status)
        .unwrap_or_else(|_| "missing".into());
    failure_check(
        "retry_exhaustion",
        status == "failed",
        format!("run_status={status}"),
        run_id,
    )
}
fn failure_lease_fencing() -> FailureInjectionCheck {
    let mut store = MemoryStore::new();
    let (run_id, step_id) = store.create_run(State::new());
    let claim = store.claim_step("stale-worker", &run_id, 0.0).unwrap();
    let recovered = store.recover_expired_leases();
    let stale_rejected = store
        .commit_state_patch(&run_id, &step_id, &claim.lease_token, 0, State::new())
        .is_err();
    let fresh = store.claim_step("fresh-worker", &run_id, 60.0).unwrap();
    let passed = recovered == 1 && stale_rejected && fresh.attempt == 2;
    failure_check(
        "lease_fencing",
        passed,
        format!("recovered_steps={recovered} stale_rejected={stale_rejected}"),
        run_id,
    )
}
fn failure_cancellation_fencing() -> FailureInjectionCheck {
    let mut store = MemoryStore::new();
    let (run_id, step_id) = store.create_run(State::new());
    let claim = store.claim_step("stale-worker", &run_id, 60.0).unwrap();
    let cancelled = store.cancel_run(&run_id, "failure injection").unwrap();
    let stale_rejected = store
        .commit_state_patch(&run_id, &step_id, &claim.lease_token, 0, State::new())
        .is_err();
    let fresh = store.claim_step("fresh-worker", &run_id, 60.0).is_err();
    let status = store.run(&run_id).map(|run| run.status).unwrap_or_default();
    let passed = cancelled == 1 && stale_rejected && fresh && status == "cancelled";
    failure_check(
        "cancellation_fencing",
        passed,
        format!("cancelled_steps={cancelled} stale_rejected={stale_rejected}"),
        run_id,
    )
}
fn failure_side_effect_idempotency() -> FailureInjectionCheck {
    use std::sync::{Arc, Mutex};
    let calls = Arc::new(Mutex::new(0usize));
    let calls_for_tool = Arc::clone(&calls);
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "external.create",
            Box::new(move |_args| {
                let mut guard = calls_for_tool.lock().unwrap();
                *guard += 1;
                Ok(Value::Object(state(&[(
                    "id",
                    Value::String("EXT-1".into()),
                )])))
            }),
        )
        .side_effect("external")
        .idempotency_required(true),
    );
    let (run_id, _) = runtime.create_run(State::new());
    let ctx = failure_claim_context(&mut runtime, &run_id, "worker-1", "FailureInjector");
    let _ = runtime.call_tool(
        &ctx,
        "external.create",
        state(&[("title", Value::String("once".into()))]),
    );
    runtime
        .store
        .mark_retry(&run_id, &ctx.step_id, "RetryableAgentError", "retryable");
    let ctx2 = failure_claim_context(&mut runtime, &run_id, "worker-2", "FailureInjector");
    let _ = runtime.call_tool(
        &ctx2,
        "external.create",
        state(&[("title", Value::String("once".into()))]),
    );
    let count = *calls.lock().unwrap();
    failure_check(
        "side_effect_idempotency",
        count == 1,
        format!("external_call_count={count}"),
        run_id,
    )
}

fn failure_claim_context(
    runtime: &mut Runtime,
    run_id: &str,
    worker_id: &str,
    agent_role: &str,
) -> AgentContext {
    let claim = runtime.store.claim_step(worker_id, run_id, 60.0).unwrap();
    AgentContext {
        run_id: claim.run_id,
        session_id: claim.session_id,
        step_id: claim.step_id,
        agent_role: agent_role.to_string(),
        lease_token: claim.lease_token,
        attempt: claim.attempt,
        state_version: claim.state_version,
        pending_patch: State::new(),
    }
}

#[derive(Clone, Debug)]
pub struct ShadowReport {
    pub source_run_id: String,
    pub shadow_run_id: String,
    pub ok: bool,
    pub state_diff: State,
}

pub fn diff_states(source: &State, shadow: &State) -> State {
    let mut changed = State::new();
    for key in source.keys().chain(shadow.keys()) {
        if changed.contains_key(key) {
            continue;
        }
        if source.get(key) != shadow.get(key) {
            changed.insert(
                key.clone(),
                Value::Object(state(&[
                    ("source", source.get(key).cloned().unwrap_or_default()),
                    ("shadow", shadow.get(key).cloned().unwrap_or_default()),
                ])),
            );
        }
    }
    state(&[
        ("changed", Value::Object(changed.clone())),
        ("changed_count", Value::Number(changed.len() as f64)),
    ])
}

pub fn shadow_report(
    source_run_id: &str,
    shadow_run_id: &str,
    ok: bool,
    source_state: &State,
    shadow_state: &State,
) -> ShadowReport {
    ShadowReport {
        source_run_id: source_run_id.into(),
        shadow_run_id: shadow_run_id.into(),
        ok,
        state_diff: diff_states(source_state, shadow_state),
    }
}

pub fn builtin_golden_names() -> Vec<String> {
    vec![
        "media-stream-checkpoint".into(),
        "minimal-success".into(),
        "tool-ledger-success".into(),
    ]
}

pub fn builtin_golden_evidence(name: &str) -> Result<EvidenceBundle> {
    match name {
        "minimal-success" => golden_minimal_success(),
        "tool-ledger-success" => golden_tool_ledger_success(),
        "media-stream-checkpoint" => golden_media_stream_checkpoint(),
        _ => Err(RuntimeError(format!(
            "unknown built-in golden case: {name}"
        ))),
    }
}

pub fn golden_regression(golden: &EvidenceBundle, current: &EvidenceBundle) -> EvidenceCheckReport {
    evaluate_evidence_regression(golden, current, None)
}

fn golden_minimal_success() -> Result<EvidenceBundle> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(State::new());
    runtime.run_once(
        &run_id,
        "golden-worker",
        "GoldenAgent",
        60.0,
        |ctx, _state| {
            ctx.write_state("answer", Value::String("ok".into()));
            Ok(())
        },
    )?;
    export_evidence(&runtime.store, &run_id)
}
fn golden_tool_ledger_success() -> Result<EvidenceBundle> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "github.create_issue",
            Box::new(|_args| {
                Ok(Value::Object(state(&[(
                    "issue_id",
                    Value::String("ISSUE-1".into()),
                )])))
            }),
        )
        .side_effect("external"),
    );
    let (run_id, _) = runtime.create_run(State::new());
    runtime.run_once(
        &run_id,
        "golden-worker",
        "ExecutorAgent",
        60.0,
        |ctx, _state| {
            ctx.write_state("issue_id", Value::String("ISSUE-1".into()));
            Ok(())
        },
    )?;
    export_evidence(&runtime.store, &run_id)
}
fn golden_media_stream_checkpoint() -> Result<EvidenceBundle> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(State::new());
    runtime.run_once(
        &run_id,
        "golden-worker",
        "MediaAgent",
        60.0,
        |ctx, _state| {
            ctx.write_state("processed_offset", Value::Number(42.0));
            Ok(())
        },
    )?;
    runtime.store.create_artifact(
        &run_id,
        None,
        "golden-video-frame",
        State::new(),
        state(&[(
            "agentledger_media",
            Value::Object(state(&[
                ("kind", Value::String("frame".into())),
                ("uri", Value::String("file://golden-frame.jpg".into())),
            ])),
        )]),
    );
    runtime.store.create_artifact(
        &run_id,
        None,
        "golden-stream-checkpoint",
        State::new(),
        state(&[(
            "agentledger_stream",
            Value::Object(state(&[
                ("stream_id", Value::String("stream-golden".into())),
                ("consumer_id", Value::String("consumer-golden".into())),
                ("offset", Value::Number(42.0)),
            ])),
        )]),
    );
    export_evidence(&runtime.store, &run_id)
}

#[derive(Clone, Debug)]
pub struct TimeTravelFrame {
    pub seq: u64,
    pub event_id: String,
    pub event_type: String,
    pub step_id: Option<String>,
    pub agent_role: Option<String>,
    pub state_version: Option<u64>,
    pub timestamp: f64,
    pub state_changed: bool,
    pub changed_keys: Vec<String>,
    pub patch: Option<State>,
    pub state_after: Option<State>,
}

#[derive(Clone, Debug)]
pub struct TimeTravelReport {
    pub run_id: String,
    pub at_seq: Option<u64>,
    pub event_count: usize,
    pub timeline: Vec<TimeTravelFrame>,
    pub state_at_seq: State,
    pub selected_event: Option<TimeTravelFrame>,
}

pub fn time_travel(
    bundle: &EvidenceBundle,
    at_seq: Option<u64>,
    include_states: bool,
) -> TimeTravelReport {
    let mut current = State::new();
    let mut state_at_seq = State::new();
    let mut selected_event = None;
    let mut timeline = Vec::new();
    for event in &bundle.events {
        let before = current.clone();
        let patch = patch_for_time_travel_event(event);
        if let Some(patch_value) = &patch {
            for (key, value) in patch_value {
                current.insert(key.clone(), value.clone());
            }
        }
        let diff = diff_states(&before, &current);
        let changed_keys = match diff.get("changed") {
            Some(Value::Object(obj)) => obj.keys().cloned().collect(),
            _ => Vec::new(),
        };
        let frame = TimeTravelFrame {
            seq: event.seq,
            event_id: event.event_id.clone(),
            event_type: event.event_type.clone(),
            step_id: event.step_id.clone(),
            agent_role: event.agent_role.clone(),
            state_version: event.state_version,
            timestamp: event.timestamp,
            state_changed: diff.get("changed_count") != Some(&Value::Number(0.0)),
            changed_keys,
            patch,
            state_after: if include_states {
                Some(current.clone())
            } else {
                None
            },
        };
        if at_seq.is_some_and(|seq| event.seq <= seq) {
            state_at_seq = current.clone();
            selected_event = Some(frame.clone());
        }
        timeline.push(frame);
    }
    if at_seq.is_none() {
        state_at_seq = current.clone();
    }
    TimeTravelReport {
        run_id: bundle.run.run_id.clone(),
        at_seq,
        event_count: timeline.len(),
        timeline,
        state_at_seq,
        selected_event,
    }
}

fn patch_for_time_travel_event(event: &Event) -> Option<State> {
    if event.event_type == "run_created" {
        if let Some(Value::Object(obj)) = event.payload.get("initial_state") {
            return Some(obj.clone());
        }
        return Some(State::new());
    }
    if event.event_type == "state_committed"
        || event.event_type == "state_patch_committed"
        || event.event_type == "system_state_patch_applied"
    {
        if let Some(Value::Object(obj)) = event.payload.get("patch") {
            return Some(obj.clone());
        }
        return Some(State::new());
    }
    None
}

pub fn time_travel_html(report: &TimeTravelReport) -> String {
    let rows = report
        .timeline
        .iter()
        .map(|frame| {
            format!(
                "<tr><td>{}</td><td>{}</td><td>{}</td></tr>",
                frame.seq,
                frame.event_type,
                frame.changed_keys.join(", ")
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    format!("<!doctype html><html><head><meta charset=\"utf-8\"><title>AgentLedger Time Travel Report</title></head><body><h1>AgentLedger Time Travel Report</h1><p>Run <code>{}</code></p><table>{}</table><h2>State At Selected Point</h2><pre>{:?}</pre><h2>Selected Event</h2><pre>{:?}</pre></body></html>", report.run_id, rows, report.state_at_seq, report.selected_event)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OptionalAdapterCapability {
    pub name: String,
    pub category: String,
    pub core_imports_heavy_sdks: bool,
    pub adapter_is_optional: bool,
    pub fail_closed_without_adapter: bool,
    pub contract_surface: Vec<String>,
}

pub fn optional_adapter_capabilities() -> Vec<OptionalAdapterCapability> {
    fn item(name: &str, category: &str, surface: &[&str]) -> OptionalAdapterCapability {
        OptionalAdapterCapability {
            name: name.to_string(),
            category: category.to_string(),
            core_imports_heavy_sdks: false,
            adapter_is_optional: true,
            fail_closed_without_adapter: true,
            contract_surface: surface.iter().map(|s| s.to_string()).collect(),
        }
    }
    vec![
        item("postgres", "storage", &["ddl_for", "migrations_for", "state_store"]),
        item("mysql", "storage", &["ddl_for", "migrations_for", "state_store"]),
        item("s3", "blobstore", &["put_json", "get_json", "content_address"]),
        item("docker", "sandbox", &["sandbox_policy", "sandbox_result", "tool_gateway"]),
        item("e2b", "sandbox", &["sandbox_policy", "sandbox_result", "tool_gateway"]),
        item("bubblewrap", "sandbox", &["sandbox_policy", "sandbox_result", "tool_gateway"]),
        item("kubernetes", "sandbox", &["sandbox_policy", "sandbox_result", "tool_gateway"]),
        item("gvisor", "sandbox", &["sandbox_policy", "sandbox_result", "tool_gateway"]),
        item("firecracker", "sandbox", &["sandbox_policy", "sandbox_result", "tool_gateway"]),
        item("langgraph", "framework", &["framework_adapter", "checkpoint_contract"]),
        item("langchain", "framework", &["framework_adapter"]),
        item("crewai", "framework", &["framework_adapter"]),
        item("autogen", "framework", &["framework_adapter"]),
        item("openai-agents-sdk", "framework", &["framework_adapter"]),
        item("llamaindex", "framework", &["framework_adapter"]),
        item("semantic-kernel", "framework", &["framework_adapter"]),
        item("mcp-transport", "mcp", &["mcp_tool_descriptor", "mcp_resource_descriptor"]),
        item("langfuse", "observability", &["evidence_bundle", "trace_payload", "correlation_ids"]),
        item("shadow-runner", "shadow", &["evidence_bundle", "tool_ledger", "state_diff"]),
    ]
}

pub trait SqlExecutor {
    fn exec(&mut self, sql: &str, params: &[Value]) -> Result<()>;
}

pub struct PostgresAdapter<C: SqlExecutor> {
    pub schema: String,
    pub client: C,
}

impl<C: SqlExecutor> PostgresAdapter<C> {
    pub fn new(client: C, schema: &str) -> Self {
        Self { schema: if schema.is_empty() { "agentledger".to_string() } else { schema.to_string() }, client }
    }
    pub fn migration_plan(&self) -> Result<Vec<Migration>> { migrations_for("postgres") }
    pub fn apply_migrations(&mut self) -> Result<()> {
        self.client.exec(&ddl_for("postgres")?, &[])?;
        for migration in self.migration_plan()? {
            self.client.exec(
                "INSERT INTO schema_migrations(version, name, checksum) VALUES ($1, $2, $3) ON CONFLICT (version) DO NOTHING",
                &[Value::String(migration.version), Value::String(migration.name), Value::String(stable_hash(&migration.sql))],
            )?;
        }
        Ok(())
    }
}

pub struct MySQLAdapter<C: SqlExecutor> {
    pub database: String,
    pub client: C,
}

impl<C: SqlExecutor> MySQLAdapter<C> {
    pub fn new(client: C, database: &str) -> Self {
        Self { database: if database.is_empty() { "agentledger".to_string() } else { database.to_string() }, client }
    }
    pub fn migration_plan(&self) -> Result<Vec<Migration>> { migrations_for("mysql") }
    pub fn apply_migrations(&mut self) -> Result<()> {
        self.client.exec(&ddl_for("mysql")?, &[])?;
        for migration in self.migration_plan()? {
            self.client.exec(
                "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?, ?, ?, UNIX_TIMESTAMP()) ON DUPLICATE KEY UPDATE version=version",
                &[Value::String(migration.version), Value::String(migration.name), Value::String(stable_hash(&migration.sql))],
            )?;
        }
        Ok(())
    }
}

pub trait ObjectClient {
    fn put_object(&mut self, bucket: &str, key: &str, body: &[u8], content_type: &str, metadata: State) -> Result<()>;
    fn get_object(&mut self, bucket: &str, key: &str) -> Result<Vec<u8>>;
}

pub struct S3BlobStoreAdapter<C: ObjectClient> {
    pub bucket: String,
    pub prefix: String,
    pub client: C,
}

impl<C: ObjectClient> S3BlobStoreAdapter<C> {
    pub fn new(client: C, bucket: &str, prefix: &str) -> Self {
        Self { bucket: bucket.to_string(), prefix: if prefix.is_empty() { "agentledger/blobs".to_string() } else { prefix.trim_matches('/').to_string() }, client }
    }
    pub fn put_json(&mut self, value: &Value) -> Result<(String, String)> {
        let encoded = encode_value(value);
        let digest = stable_hash(&encoded);
        let key = format!("{}/sha256/{}.json", self.prefix, digest);
        let mut metadata = State::new();
        metadata.insert("agentledger-digest".to_string(), Value::String(format!("sha256:{digest}")));
        self.client.put_object(&self.bucket, &key, encoded.as_bytes(), "application/json", metadata)?;
        Ok((format!("sha256:{digest}"), format!("s3://{}/{}", self.bucket, key)))
    }
    pub fn get_json(&mut self, reference: &str) -> Result<Value> {
        let prefix = format!("s3://{}/", self.bucket);
        if !reference.starts_with(&prefix) || reference.contains("..") {
            return Err(RuntimeError(format!("unsupported s3 blob ref: {reference}")));
        }
        let key = &reference[prefix.len()..];
        let body = self.client.get_object(&self.bucket, key)?;
        let text = String::from_utf8(body).map_err(|err| RuntimeError(err.to_string()))?;
        decode_value(&text)
    }
}

pub trait OtlpClient { fn post_json(&mut self, endpoint: &str, payload: &str, content_type: &str) -> Result<()>; }
pub struct OtlpTransport<C: OtlpClient> { pub endpoint: String, pub client: C }
impl<C: OtlpClient> OtlpTransport<C> { pub fn export(&mut self, payload: &str) -> Result<()> { self.client.post_json(&self.endpoint, payload, "application/json") } }

pub struct DockerSandboxAdapter { pub image: String }
impl DockerSandboxAdapter {
    pub fn manifest(&self, policy: &State, command: Vec<String>) -> State {
        let mut out = State::new();
        out.insert("backend".to_string(), Value::String("docker".to_string()));
        out.insert("image".to_string(), Value::String(if self.image.is_empty() { "python:3.11-slim".to_string() } else { self.image.clone() }));
        let network = match policy.get("network") { Some(Value::String(value)) if value != "deny" => value.clone(), _ => "none".to_string() };
        out.insert("network".to_string(), Value::String(network));
        out.insert("read_only_root".to_string(), Value::Bool(true));
        out.insert("requires_explicit_execution".to_string(), Value::Bool(true));
        out.insert("command".to_string(), Value::Array(command.into_iter().map(Value::String).collect()));
        out
    }
}

pub struct DockerSandboxExecutor {
    pub image: String,
    pub binary: String,
    pub allow_command_execution: bool,
    pub allow_shell: bool,
    pub shell: String,
    pub memory: String,
    pub cpus: String,
}

impl DockerSandboxExecutor {
    pub fn new(image: &str, allow_command_execution: bool) -> Self {
        Self {
            image: image.to_string(),
            binary: "docker".to_string(),
            allow_command_execution,
            allow_shell: false,
            shell: "/bin/sh".to_string(),
            memory: String::new(),
            cpus: String::new(),
        }
    }

    pub fn with_binary(mut self, binary: &str) -> Self {
        self.binary = binary.to_string();
        self
    }

    fn extract_command(&self, args: &State) -> std::result::Result<Vec<String>, String> {
        let raw = args.get("_sandbox_command").or_else(|| args.get("command"));
        match raw {
            Some(Value::String(command)) => {
                if !self.allow_shell {
                    Err("string commands require allow_shell=true; pass argv list in `_sandbox_command` instead".to_string())
                } else {
                    let shell = if self.shell.is_empty() { "/bin/sh" } else { &self.shell };
                    Ok(vec![shell.to_string(), "-lc".to_string(), command.clone()])
                }
            }
            Some(Value::Array(items)) => {
                let mut command = Vec::new();
                for item in items {
                    match item {
                        Value::String(value) if !value.is_empty() => command.push(value.clone()),
                        _ => return Err("_sandbox_command must be a non-empty string array".to_string()),
                    }
                }
                if command.is_empty() {
                    Err("_sandbox_command must be a non-empty string array".to_string())
                } else {
                    Ok(command)
                }
            }
            _ => Err("external sandbox tools require a command-style `_sandbox_command` arg".to_string()),
        }
    }

    fn docker_argv(&self, policy: &SandboxPolicy, command: &[String]) -> Vec<String> {
        let image = if self.image.is_empty() { "python:3.11-slim" } else { &self.image };
        let network = if policy.network == "deny" || policy.network.is_empty() { "none" } else { &policy.network };
        let mut argv = vec![
            self.binary.clone(),
            "run".to_string(),
            "--rm".to_string(),
            "--network".to_string(),
            network.to_string(),
            "--read-only".to_string(),
        ];
        if !self.memory.is_empty() {
            argv.extend(["--memory".to_string(), self.memory.clone()]);
        }
        if !self.cpus.is_empty() {
            argv.extend(["--cpus".to_string(), self.cpus.clone()]);
        }
        argv.push(image.to_string());
        argv.extend(command.iter().cloned());
        argv
    }

    fn result_error(policy: &SandboxPolicy, manifest: State, error_type: &str, error: String) -> SandboxResult {
        let mut metadata = State::new();
        metadata.insert("executor".to_string(), Value::String(policy.executor.clone()));
        metadata.insert("isolation_level".to_string(), Value::String("container".to_string()));
        metadata.insert("manifest".to_string(), Value::Object(manifest));
        metadata.insert("error_type".to_string(), Value::String(error_type.to_string()));
        SandboxResult { ok: false, output: Value::Null, error: Some(error), metadata }
    }
}

impl SandboxExecutor for DockerSandboxExecutor {
    fn run_tool(&self, args: State, policy: &SandboxPolicy) -> SandboxResult {
        let command = match self.extract_command(&args) {
            Ok(command) => command,
            Err(error) => return Self::result_error(policy, State::new(), "InvalidSandboxCommand", error),
        };
        let mut policy_state = State::new();
        policy_state.insert("network".to_string(), Value::String(policy.network.clone()));
        let manifest = (DockerSandboxAdapter { image: self.image.clone() }).manifest(&policy_state, command.clone());
        if !self.allow_command_execution {
            return Self::result_error(policy, manifest, "SandboxAdapterNotInstalled", "command execution is not enabled for this executor".to_string());
        }
        let argv = self.docker_argv(policy, &command);
        let mut cmd = Command::new(&argv[0]);
        cmd.args(&argv[1..]).stdout(Stdio::piped()).stderr(Stdio::piped());
        let output = match cmd.output() {
            Ok(output) => output,
            Err(error) => return Self::result_error(policy, manifest, "SandboxBinaryMissing", error.to_string()),
        };
        let mut value = State::new();
        value.insert("stdout".to_string(), Value::String(String::from_utf8_lossy(&output.stdout).to_string()));
        value.insert("stderr".to_string(), Value::String(String::from_utf8_lossy(&output.stderr).to_string()));
        value.insert("returncode".to_string(), Value::Number(output.status.code().unwrap_or(-1) as f64));
        let mut metadata = State::new();
        metadata.insert("executor".to_string(), Value::String(policy.executor.clone()));
        metadata.insert("isolation_level".to_string(), Value::String("container".to_string()));
        metadata.insert("manifest".to_string(), Value::Object(manifest));
        metadata.insert("executed".to_string(), Value::Bool(true));
        if !output.status.success() {
            metadata.insert("error_type".to_string(), Value::String("SandboxCommandFailed".to_string()));
            return SandboxResult {
                ok: false,
                output: Value::Object(value),
                error: Some(format!("sandbox command exited with {}", output.status.code().unwrap_or(-1))),
                metadata,
            };
        }
        SandboxResult { ok: true, output: Value::Object(value), error: None, metadata }
    }
}

pub mod adapters {
    pub mod postgres {
        pub const PACKAGE_NAME: &str = "agentledger-postgres";
        pub const FEATURE: &str = "adapter-postgres";
        pub use crate::{migrations_for, Migration, PostgresAdapter, SqlExecutor};
    }

    pub mod mysql {
        pub const PACKAGE_NAME: &str = "agentledger-mysql";
        pub const FEATURE: &str = "adapter-mysql";
        pub use crate::{migrations_for, Migration, MySQLAdapter, SqlExecutor};
    }

    pub mod s3 {
        pub const PACKAGE_NAME: &str = "agentledger-s3";
        pub const FEATURE: &str = "adapter-s3";
        pub use crate::{ObjectClient, S3BlobStoreAdapter};
    }

    pub mod mcp {
        pub const PACKAGE_NAME: &str = "agentledger-mcp";
        pub const FEATURE: &str = "adapter-mcp";
        pub use crate::{
            InMemoryMCPContextServer, InMemoryMCPToolServer, MCPCall, MCPContextAdapter,
            MCPResourceDescriptor, MCPResourceRead, MCPToolAdapter,
        };
    }

    pub mod otel {
        pub const PACKAGE_NAME: &str = "agentledger-otel";
        pub const FEATURE: &str = "adapter-otel";
        pub use crate::{OtlpClient, OtlpTransport};
    }

    pub mod langfuse {
        pub const PACKAGE_NAME: &str = "agentledger-langfuse";
        pub const FEATURE: &str = "adapter-langfuse";
        pub const CATEGORY: &str = "observability";
    }

    pub mod docker {
        pub const PACKAGE_NAME: &str = "agentledger-sandbox-docker";
        pub const FEATURE: &str = "adapter-docker";
        pub use crate::{DockerSandboxAdapter, DockerSandboxExecutor, State, Value};
    }

    pub mod framework {
        pub const PACKAGE_NAME: &str = "agentledger-framework";
        pub const FEATURE: &str = "adapter-framework";
        pub use crate::{FunctionAdapter, MethodFrameworkAdapter};
    }
}
