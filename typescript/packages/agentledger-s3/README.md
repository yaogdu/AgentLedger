# agentledger-s3

TypeScript S3-compatible blob store adapter boundary for AgentLedger Runtime.

```bash
npm install agentledger-runtime agentledger-s3
```

```js
import { S3BlobStoreAdapter } from 'agentledger-s3';

const blobs = new S3BlobStoreAdapter(s3Client, { bucket: 'agentledger-evidence' });
const { ref } = await blobs.putJSON({ ok: true });
```
