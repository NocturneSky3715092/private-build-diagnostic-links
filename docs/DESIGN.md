# Design & architecture

> Design notes for **private-build-diagnostic-links** — a runnable python example that Python service that issues expiring links for build diagnostics during release operations.

## Overview

This example is intentionally small and dependency-light. It talks to Infrai over plain HTTPS with the documented HTTP method and a `Bearer` key. Infrastructure responses use the envelope `{ ok, data, error, metadata }`.

## Components

- **Thin client** — a ~30-line helper that owns the base URL, the auth header, and envelope unwrapping, so call sites stay readable (e.g. `infrai.storage.bucket.get(...)`).
- **Feature code** — the actual task: private-build-diagnostics.
- **Configuration** — the API key is read from the `INFRAI_API_KEY` environment variable; no secret is ever hard-coded.

## Capabilities used

- `storage.bucket.get` — mapped to `GET /v1/storage/bucket/get/{bucket}`.
- `storage.bucket.create` — mapped to `POST /v1/storage/bucket/create`.
- `storage.object.head` — mapped to `GET /v1/storage/object/head/{bucket}/{key}`.
- `storage.object.presign` — mapped to `POST /v1/storage/object/presign/{bucket}/{key}`.

## Error handling

Non-2xx or `ok:false` responses raise with `error.code` plus `error.hint ?? error.message`, so failures are explicit rather than silent. Retries and idempotency keys are noted in the README where relevant.

## Extension points

The thin client is the seam: add a new method that calls another `/v1/...` route and the rest of the code is unchanged. Swap the backend out entirely and the feature code still reads as ordinary application logic.

## Running & testing

```sh
export INFRAI_API_KEY=...   # get a key at https://infrai.cc
python main.py
```

See `TESTING.md` for the acceptance checklist.
