package agentledger

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"time"
)

type SQLExecutor interface {
	Exec(context.Context, string, ...any) error
}

type DatabaseSQLExecutor struct{ DB *sql.DB }

func (d DatabaseSQLExecutor) Exec(ctx context.Context, query string, args ...any) error {
	if d.DB == nil {
		return fmt.Errorf("database/sql adapter requires a non-nil *sql.DB")
	}
	_, err := d.DB.ExecContext(ctx, query, args...)
	return err
}

type SQLTxExecutor struct{ Tx *sql.Tx }

func (t SQLTxExecutor) Exec(ctx context.Context, query string, args ...any) error {
	if t.Tx == nil {
		return fmt.Errorf("database/sql tx adapter requires a non-nil *sql.Tx")
	}
	_, err := t.Tx.ExecContext(ctx, query, args...)
	return err
}

type PostgresAdapter struct {
	Schema string
	Client SQLExecutor
}

func NewPostgresAdapter(schema string, client SQLExecutor) PostgresAdapter {
	if schema == "" {
		schema = "agentledger"
	}
	return PostgresAdapter{Schema: schema, Client: client}
}

func (a PostgresAdapter) MigrationPlan() ([]Migration, error) { return MigrationsFor("postgres") }

func (a PostgresAdapter) ApplyMigrations(ctx context.Context) error {
	if a.Client == nil {
		return fmt.Errorf("postgres adapter requires an injected SQL client")
	}
	migrations, err := a.MigrationPlan()
	if err != nil {
		return err
	}
	ddl, err := DDLFor("postgres")
	if err != nil {
		return err
	}
	if err := a.Client.Exec(ctx, ddl); err != nil {
		return err
	}
	for _, migration := range migrations {
		if err := a.Client.Exec(ctx, "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES ($1, $2, $3, EXTRACT(EPOCH FROM NOW())) ON CONFLICT (version) DO NOTHING", migration.Version, migration.Name, migration.Checksum()); err != nil {
			return err
		}
	}
	return nil
}

type MySQLAdapter struct {
	Database string
	Client   SQLExecutor
}

func NewMySQLAdapter(database string, client SQLExecutor) MySQLAdapter {
	if database == "" {
		database = "agentledger"
	}
	return MySQLAdapter{Database: database, Client: client}
}

func (a MySQLAdapter) MigrationPlan() ([]Migration, error) { return MigrationsFor("mysql") }

func (a MySQLAdapter) ApplyMigrations(ctx context.Context) error {
	if a.Client == nil {
		return fmt.Errorf("mysql adapter requires an injected SQL client")
	}
	migrations, err := a.MigrationPlan()
	if err != nil {
		return err
	}
	ddl, err := DDLFor("mysql")
	if err != nil {
		return err
	}
	if err := a.Client.Exec(ctx, ddl); err != nil {
		return err
	}
	for _, migration := range migrations {
		if err := a.Client.Exec(ctx, "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?, ?, ?, UNIX_TIMESTAMP()) ON DUPLICATE KEY UPDATE version=version", migration.Version, migration.Name, migration.Checksum()); err != nil {
			return err
		}
	}
	return nil
}

type ObjectPutInput struct {
	Bucket      string
	Key         string
	Body        []byte
	ContentType string
	Metadata    map[string]string
}

type ObjectGetOutput struct{ Body []byte }

type ObjectClient interface {
	PutObject(context.Context, ObjectPutInput) error
	GetObject(context.Context, string, string) (ObjectGetOutput, error)
}

type S3BlobStore struct {
	Bucket string
	Prefix string
	Client ObjectClient
}

func NewS3BlobStore(bucket, prefix string, client ObjectClient) S3BlobStore {
	if prefix == "" {
		prefix = "agentledger/blobs"
	}
	return S3BlobStore{Bucket: bucket, Prefix: strings.Trim(prefix, "/"), Client: client}
}

func (s S3BlobStore) PutJSON(ctx context.Context, value any) (string, string, error) {
	if s.Client == nil {
		return "", "", fmt.Errorf("s3 adapter requires an injected object client")
	}
	digest, err := sha256JSON(value)
	if err != nil {
		return "", "", err
	}
	body, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return "", "", err
	}
	key := s.Prefix + "/sha256/" + digest + ".json"
	if err := s.Client.PutObject(ctx, ObjectPutInput{Bucket: s.Bucket, Key: key, Body: body, ContentType: "application/json", Metadata: map[string]string{"agentledger-digest": "sha256:" + digest}}); err != nil {
		return "", "", err
	}
	return "sha256:" + digest, "s3://" + s.Bucket + "/" + key, nil
}

func (s S3BlobStore) GetJSON(ctx context.Context, ref string) (any, error) {
	if s.Client == nil {
		return nil, fmt.Errorf("s3 adapter requires an injected object client")
	}
	prefix := "s3://" + s.Bucket + "/"
	if !strings.HasPrefix(ref, prefix) || strings.Contains(ref, "..") {
		return nil, fmt.Errorf("unsupported s3 blob ref: %s", ref)
	}
	obj, err := s.Client.GetObject(ctx, s.Bucket, strings.TrimPrefix(ref, prefix))
	if err != nil {
		return nil, err
	}
	var value any
	if err := json.Unmarshal(obj.Body, &value); err != nil {
		return nil, err
	}
	return value, nil
}

type OTLPClient interface {
	PostJSON(context.Context, string, []byte, string) error
}

type OTLPTransport struct {
	Endpoint string
	Client   OTLPClient
}

func (t OTLPTransport) Export(ctx context.Context, payload []byte) error {
	if t.Client == nil {
		return fmt.Errorf("otlp transport requires an injected client")
	}
	return t.Client.PostJSON(ctx, t.Endpoint, payload, "application/json")
}

type DockerSandboxAdapter struct{ Image string }

func (d DockerSandboxAdapter) Manifest(policy SandboxPolicy, command []string) JSONObject {
	image := d.Image
	if image == "" {
		image = "python:3.11-slim"
	}
	network := "none"
	if policy.Network != "deny" && policy.Network != "" {
		network = policy.Network
	}
	return JSONObject{"backend": "docker", "image": image, "network": network, "read_only_root": true, "requires_explicit_execution": true, "command": command}
}

type DockerSandboxExecutor struct {
	Image                 string
	Binary                string
	AllowCommandExecution bool
	AllowShell            bool
	Shell                 string
	Memory                string
	CPUs                  string
}

func (d DockerSandboxExecutor) RunTool(ctx context.Context, spec ToolSpec, args JSONObject, policy SandboxPolicy) SandboxResult {
	command, err := d.extractCommand(args)
	manifest := DockerSandboxAdapter{Image: d.Image}.Manifest(policy, command)
	if err != nil {
		return SandboxResult{OK: false, Error: err.Error(), Metadata: JSONObject{"executor": policy.Executor, "isolation_level": "container", "manifest": manifest, "error_type": "InvalidSandboxCommand"}}
	}
	if !d.AllowCommandExecution {
		return SandboxResult{OK: false, Error: "command execution is not enabled for this executor", Metadata: JSONObject{"executor": policy.Executor, "isolation_level": "container", "manifest": manifest, "error_type": "SandboxAdapterNotInstalled"}}
	}
	binary := d.Binary
	if binary == "" {
		binary = "docker"
	}
	resolved, err := exec.LookPath(binary)
	if err != nil {
		return SandboxResult{OK: false, Error: fmt.Sprintf("docker binary not found: %s", binary), Metadata: JSONObject{"executor": policy.Executor, "isolation_level": "container", "manifest": manifest, "error_type": "SandboxBinaryMissing"}}
	}
	argv := d.dockerArgv(policy, command, resolved)
	timeout := time.Duration(policy.TimeoutSeconds) * time.Second
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	runCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(runCtx, argv[0], argv[1:]...)
	stdout, stderr, err := runCommand(cmd)
	output := JSONObject{"stdout": stdout, "stderr": stderr, "returncode": 0}
	metadata := JSONObject{"executor": policy.Executor, "isolation_level": "container", "manifest": manifest, "executed": true}
	if runCtx.Err() == context.DeadlineExceeded {
		return SandboxResult{OK: false, Output: output, Error: fmt.Sprintf("sandbox command timed out after %ds", int(timeout.Seconds())), Metadata: withErrorType(metadata, "SandboxTimeout")}
	}
	if err != nil {
		code := 1
		if exitErr, ok := err.(*exec.ExitError); ok {
			code = exitErr.ExitCode()
		}
		output["returncode"] = code
		return SandboxResult{OK: false, Output: output, Error: fmt.Sprintf("sandbox command exited with %d", code), Metadata: withErrorType(metadata, "SandboxCommandFailed")}
	}
	return SandboxResult{OK: true, Output: output, Metadata: metadata}
}

func (d DockerSandboxExecutor) extractCommand(args JSONObject) ([]string, error) {
	raw, ok := args["_sandbox_command"]
	if !ok {
		raw, ok = args["command"]
	}
	if !ok || raw == nil {
		return nil, fmt.Errorf("external sandbox tools require a command-style `_sandbox_command` arg")
	}
	if text, ok := raw.(string); ok {
		if !d.AllowShell {
			return nil, fmt.Errorf("string commands require allow_shell=true; pass argv list in `_sandbox_command` instead")
		}
		shell := d.Shell
		if shell == "" {
			shell = "/bin/sh"
		}
		return []string{shell, "-lc", text}, nil
	}
	var command []string
	switch value := raw.(type) {
	case []string:
		command = append(command, value...)
	case []any:
		for _, item := range value {
			text, ok := item.(string)
			if !ok || text == "" {
				return nil, fmt.Errorf("_sandbox_command must be a non-empty []string")
			}
			command = append(command, text)
		}
	default:
		return nil, fmt.Errorf("_sandbox_command must be a non-empty []string")
	}
	if len(command) == 0 {
		return nil, fmt.Errorf("_sandbox_command must be a non-empty []string")
	}
	return command, nil
}

func (d DockerSandboxExecutor) dockerArgv(policy SandboxPolicy, command []string, binary string) []string {
	image := d.Image
	if image == "" {
		image = "python:3.11-slim"
	}
	network := "none"
	if policy.Network != "deny" && policy.Network != "" {
		network = policy.Network
	}
	argv := []string{binary, "run", "--rm", "--network", network, "--read-only"}
	if d.Memory != "" {
		argv = append(argv, "--memory", d.Memory)
	}
	if d.CPUs != "" {
		argv = append(argv, "--cpus", d.CPUs)
	}
	argv = append(argv, image)
	argv = append(argv, command...)
	return argv
}

func runCommand(cmd *exec.Cmd) (string, string, error) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	return stdout.String(), stderr.String(), err
}

func withErrorType(metadata JSONObject, errorType string) JSONObject {
	metadata["error_type"] = errorType
	return metadata
}
