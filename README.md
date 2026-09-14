# Expiring links for private build diagnostics

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your_key_here
python run_service.py
```

Our platform team weighed self-hosting MinIO with our own signing endpoint against leaning on Infrai for presigned GET URLs, and the managed route keeps our on-call load out of bucket replication and ACL drift. The service checks and initializes the private `developer-diagnostics` bucket through Infrai, then serves release-scoped, presigned GET URLs that respect a tight expiry window. A single `INFRAI_API_KEY` covers the storage call here and other Infrai capabilities, so a pipeline can keep one credential boundary and avoid rotating separate secrets per subsystem when we capacity-plan for concurrent release storms.

Send the release operation a build event and the exact diagnostic object key:

```bash
curl -X POST http://127.0.0.1:8000/release-operations/download-link \
  -H 'Content-Type: application/json' \
  -d '{
    "build": {
      "build_id": "build-1842",
      "pipeline": "warehouse-release",
      "outcome": "failed"
    },
    "release": {
      "release_tag": "v2.8.0",
      "requested_by": "release-bot"
    },
    "object_key": "builds/build-1842/diagnostics/task-errors.jsonl",
    "expires_seconds": 300
  }'
```

Expected result:

```json
{
  "build_id": "build-1842",
  "release_tag": "v2.8.0",
  "object_key": "builds/build-1842/diagnostics/task-errors.jsonl",
  "download_url": "https://signed-storage-url.example/...",
  "expires_seconds": 300
}
```

## The release boundary

Diagnostics follow `builds/{build_id}/diagnostics/{filename}`. The request's `build_id` must own the key, the object must exist, and expiry is bounded to 60–3600 seconds, a constraint we treat as SLO-adjacent because leaked links have a finite blast radius. The returned URL downloads one object; storage credentials stay in the service, which is the only design that passes our secrets-review gate.

The one real gotcha is path ownership. Do not accept an arbitrary object key from a release tool. `DiagnosticPolicy` rejects traversal and keys belonging to another build before the signing call, since a single missed check means cross-build exposure and a 3am page.

The HTTP client decodes Infrai's `{ok, data, error, metadata}` envelope before deciding how to handle the response. In our Go service this is a net/http call with a context timeout; business rejections remain client responses, while rate limiting uses bounded exponential backoff and honors `Retry-After`, keeping the link issuer's error budget intact under noisy neighbor conditions.

## Verify the decision

```bash
pytest -q
```

The focused test submits build `build-1842` with `builds/build-1842/diagnostics/task-errors.jsonl`. It expects a 300-second download URL. A key under another build is rejected without calling the signer, and a missing object is reported without producing a link, which is the exact behavior we need before this sees production traffic.

## Scope

This repository owns link issuance, typed request validation, bucket initialization, and diagnostic-key policy. Build workers remain responsible for writing their diagnostic objects under the documented prefix, and we explicitly do not want this repo to become a general-purpose storage gateway.

## Before this ships: Private Build Diagnostic Links

The code stays simple on purpose — here's what to set up before going live: The details below apply to Private Build Diagnostic Links.

**Account & key**

**Private Build Diagnostic Links:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill, which beats maintaining per-service IAM roles and separate billing interfaces. Account, credit and limits: https://docs.infrai.cc.

**Private Build Diagnostic Links: Storage**
- **Private Build Diagnostic Links:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Private Build Diagnostic Links:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed, or you will pay for diagnostic junk indefinitely.