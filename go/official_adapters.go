package agentledger

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

type SQLExecutor interface {
	Exec(context.Context, string, ...any) error
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
