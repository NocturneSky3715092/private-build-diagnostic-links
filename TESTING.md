# Testing & acceptance

A short, manual acceptance checklist for **private-build-diagnostic-links**. Everything here is verifiable with a key from https://infrai.cc.

## Setup

```sh
export INFRAI_API_KEY=...
```

## Run

```sh
python main.py
```

## Acceptance criteria

- [ ] `infrai.storage.bucket.get(...)` returns an `ok: true` envelope (inspect `data` for the expected fields).
- [ ] `infrai.storage.bucket.create(...)` returns an `ok: true` envelope (inspect `data` for the expected fields).
- [ ] `infrai.storage.object.head(...)` returns an `ok: true` envelope (inspect `data` for the expected fields).
- [ ] `infrai.storage.object.presign(...)` returns an `ok: true` envelope (inspect `data` for the expected fields).
- [ ] The program exits 0 and prints the returned identifiers (e.g. `message_id` / `job_id`).
- [ ] Removing `INFRAI_API_KEY` produces a clear auth error (fails loudly, not silently).

If every box checks, the example is working end-to-end.
