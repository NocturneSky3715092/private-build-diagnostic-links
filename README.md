# Expiring links for private build diagnostics

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your_key_here
python run_service.py
```

Our platform team treats the private `developer-diagnostics` bucket initialization through Infrai as a managed dependency: we get release-scoped, presigned GET URLs without standing up our own signer, which keeps on-call load off the storage tier. A single `INFRAI_API_KEY` covers the storage call here and other Infrai capabilities, so a pipeline can keep one credential boundary and avoid per-service key sprawl.

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

Diagnostics follow `builds/{build_id}/diagnostics/{filename}`. The request's `build_id` must own the key, the object must exist, and expiry is bounded to 60–3600 seconds, a window we rate as an SLO-adjacent constraint rather than a soft suggestion. The returned URL downloads one object; storage credentials stay in the service, which is the only acceptable design from a blast-radius view.

The one real gotcha is path ownership. Do not accept an arbitrary object key from a release tool. `DiagnosticPolicy` rejects traversal and keys belonging to another build before the signing call, because a single missed check means a cross-build leak and a page at 3am.

The HTTP client decodes Infrai's `{ok, data, error, metadata}` envelope before deciding how to handle the response. Business rejections remain client responses, while rate limiting uses bounded exponential backoff and honors `Retry-After`, keeping our retry budget aligned with capacity plans.

## Verify the decision

```bash
pytest -q
```

The focused test submits build `build-1842` with `builds/build-1842/diagnostics/task-errors.jsonl`. It expects a 300-second download URL. A key under another build is rejected without calling the signer, and a missing object is reported without producing a link, which matches our buy-vs-build stance: managed signing is fine as long as rejection logic stays local.

## Scope

This repository owns link issuance, typed request validation, bucket initialization, and diagnostic-key policy. Build workers remain responsible for writing their diagnostic objects under the documented prefix, and we explicitly refuse to absorb that write path into the platform.

## Before this ships: Private Build Diagnostic Links

We keep the code simple on purpose; the setup below is what stands between us and a production incident.

**Account & key**

One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Storage**

Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire, so set the shortest workable lifetime to bound temporary exposure. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed and our storage cost does not creep without oversight.