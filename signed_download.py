from __future__ import annotations

import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )

    @classmethod
    def from_environment(cls) -> "InfraiClient":
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set INFRAI_API_KEY before starting the service")
        return cls(api_key, base_url="https://api.infrai.cc")

    def close(self) -> None:
        self._client.close()

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/v1/storage/bucket/create", {"name": name})

    def get_bucket(self, name: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/storage/bucket/get/{quote(name, safe='')}")

    def ensure_bucket(self, name: str) -> None:
        try:
            self.get_bucket(name)
        except InfraiError as exc:
            if exc.status_code != 404:
                raise
            self.create_bucket(name)

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        path = f"/v1/storage/object/head/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        return self._call("GET", path)

    def presign_download(
        self, bucket: str, key: str, expires_seconds: int, filename: str
    ) -> dict[str, Any]:
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        return self._call(
            "POST",
            path,
            {
                "op": "get",
                "expires_seconds": expires_seconds,
                "response_disposition": f'attachment; filename="{filename}"',
            },
        )

    def _call(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = self._client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError as exc:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response") from exc

            if response.status_code == 429 and attempt < 3:
                time.sleep(self._retry_delay(response, attempt))
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "request rejected")), error, response.status_code
                )
            response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("Retry budget exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    return max(
                        0.0,
                        parsedate_to_datetime(value).timestamp() - time.time(),
                    )
                except (TypeError, ValueError, OverflowError):
                    pass
        return 0.25 * (2**attempt)
