from fastapi.testclient import TestClient

from diagnostic_service import app, get_client


class RecordingStorage:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.presigned: list[tuple[str, str, int, str]] = []

    def head_object(self, bucket: str, key: str) -> dict[str, bool]:
        return {"found": self.found}

    def presign_download(
        self, bucket: str, key: str, expires_seconds: int, filename: str
    ) -> dict[str, str]:
        self.presigned.append((bucket, key, expires_seconds, filename))
        return {"url": "https://downloads.example/signed-build-log"}


def payload(object_key: str) -> dict[str, object]:
    return {
        "build": {
            "build_id": "build-1842",
            "pipeline": "warehouse-release",
            "outcome": "failed",
        },
        "release": {"release_tag": "v2.8.0", "requested_by": "release-bot"},
        "object_key": object_key,
        "expires_seconds": 300,
    }


def test_failed_build_diagnostic_gets_scoped_download_link() -> None:
    storage = RecordingStorage()
    app.dependency_overrides[get_client] = lambda: storage
    response = TestClient(app).post(
        "/release-operations/download-link",
        json=payload("builds/build-1842/diagnostics/task-errors.jsonl"),
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "build_id": "build-1842",
        "release_tag": "v2.8.0",
        "object_key": "builds/build-1842/diagnostics/task-errors.jsonl",
        "download_url": "https://downloads.example/signed-build-log",
        "expires_seconds": 300,
    }
    assert storage.presigned == [
        (
            "developer-diagnostics",
            "builds/build-1842/diagnostics/task-errors.jsonl",
            300,
            "task-errors.jsonl",
        )
    ]


def test_key_from_another_build_is_rejected_before_signing() -> None:
    storage = RecordingStorage()
    app.dependency_overrides[get_client] = lambda: storage
    response = TestClient(app).post(
        "/release-operations/download-link",
        json=payload("builds/build-9911/diagnostics/task-errors.jsonl"),
    )
    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert storage.presigned == []


def test_missing_diagnostic_is_reported_without_signing() -> None:
    storage = RecordingStorage(found=False)
    app.dependency_overrides[get_client] = lambda: storage
    response = TestClient(app).post(
        "/release-operations/download-link",
        json=payload("builds/build-1842/diagnostics/task-errors.jsonl"),
    )
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert storage.presigned == []
