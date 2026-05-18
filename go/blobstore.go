package agentledger

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type LocalBlobStore struct {
	Root string
}

func NewLocalBlobStore(root string) (*LocalBlobStore, error) {
	if err := os.MkdirAll(root, 0o755); err != nil {
		return nil, err
	}
	return &LocalBlobStore{Root: root}, nil
}

func (b *LocalBlobStore) PutJSON(value any) (string, string, error) {
	digest, err := sha256JSON(value)
	if err != nil {
		return "", "", err
	}
	path := filepath.Join(b.Root, "sha256", digest+".json")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return "", "", err
	}
	if _, err := os.Stat(path); err != nil {
		if !os.IsNotExist(err) {
			return "", "", err
		}
		data, err := json.MarshalIndent(value, "", "  ")
		if err != nil {
			return "", "", err
		}
		tmp := path + ".tmp"
		if err := os.WriteFile(tmp, data, 0o644); err != nil {
			return "", "", err
		}
		if err := os.Rename(tmp, path); err != nil {
			return "", "", err
		}
	}
	return "sha256:" + digest, "blob://sha256/" + digest + ".json", nil
}

func (b *LocalBlobStore) GetJSON(ref string) (any, error) {
	const prefix = "blob://sha256/"
	if !strings.HasPrefix(ref, prefix) || strings.Contains(ref, "..") || strings.ContainsAny(strings.TrimPrefix(ref, prefix), `/\\`) {
		return nil, fmt.Errorf("unsupported blob ref: %s", ref)
	}
	name := strings.TrimPrefix(ref, prefix)
	path := filepath.Join(b.Root, "sha256", name)
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var value any
	if err := json.Unmarshal(data, &value); err != nil {
		return nil, err
	}
	return value, nil
}
