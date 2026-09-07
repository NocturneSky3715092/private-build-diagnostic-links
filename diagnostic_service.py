from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from signed_download import InfraiClient, InfraiError

BUCKET = os.environ.get("DIAGNOSTICS_BUCKET", "developer-diagnostics")


class BuildEvent(BaseModel):
    build_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    pipeline: str = Field(min_length=1, max_length=80)
    outcome: str = Field(pattern=r"^(failed|passed)$")


class ReleaseOperation(BaseModel):
    release_tag: str = Field(min_length=1, max_length=80)
    requested_by: str = Field(min_length=1, max_length=120)


class DiagnosticRequest(BaseModel):
    build: BuildEvent
    release: ReleaseOperation
    object_key: str = Field(min_length=1, max_length=500)
    expires_seconds: int = Field(default=600, ge=60, le=3600)


class DiagnosticLink(BaseModel):
    build_id: str
    release_tag: str
    object_key: str
    download_url: str
    expires_seconds: int


@dataclass(frozen=True)
class DiagnosticPolicy:
    bucket: str

    def validate_key(self, build_id: str, object_key: str) -> str:
        key = PurePosixPath(object_key)
        expected = PurePosixPath("builds") / build_id / "diagnostics"
        if key.is_absolute() or ".." in key.parts or key.parent != expected:
            raise ValueError(f"object_key must name one file under {expected}/")
        return str(key)


client: InfraiClient | None = None


def get_client() -> Iterator[InfraiClient]:
    if client is None:
        raise RuntimeError("Storage client is not initialized")
    yield client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global client
    client = InfraiClient.from_environment()
    # Bucket creation has no corresponding delete capability; require the
    # deployment to provision the persistent bucket ahead of startup.
    client.get_bucket(BUCKET)
    try:
        yield
    finally:
        client.close()
        client = None


app = FastAPI(title="Developer diagnostics links", lifespan=lifespan)
policy = DiagnosticPolicy(BUCKET)


@app.post("/release-operations/download-link", response_model=DiagnosticLink)
def create_download_link(
    request: DiagnosticRequest,
    storage: InfraiClient = Depends(get_client),
) -> DiagnosticLink:
    try:
        key = policy.validate_key(request.build.build_id, request.object_key)
        state = storage.head_object(policy.bucket, key)
        if not state.get("found", False):
            raise HTTPException(status_code=404, detail="Diagnostic file was not found")
        signed = storage.presign_download(
            policy.bucket,
            key,
            request.expires_seconds,
            PurePosixPath(key).name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return DiagnosticLink(
        build_id=request.build.build_id,
        release_tag=request.release.release_tag,
        object_key=key,
        download_url=str(signed["url"]),
        expires_seconds=request.expires_seconds,
    )
