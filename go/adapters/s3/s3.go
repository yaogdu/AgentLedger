// Package s3 exposes the AgentLedger S3-compatible BlobStore adapter boundary for Go.
package s3

import runtime "github.com/yaogdu/AgentLedger/go"

type BlobStore = runtime.S3BlobStore
type ObjectClient = runtime.ObjectClient
type ObjectGetOutput = runtime.ObjectGetOutput
type ObjectPutInput = runtime.ObjectPutInput

func New(bucket, prefix string, client ObjectClient) BlobStore {
	return runtime.NewS3BlobStore(bucket, prefix, client)
}

