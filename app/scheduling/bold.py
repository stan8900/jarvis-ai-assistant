"""Authenticated Bold REST adapter for the documented `/rest/*` routes."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class BoldError(RuntimeError):
    pass


class BoldUnavailable(BoldError):
    pass


class BoldAuthError(BoldError):
    pass


@dataclass(frozen=True)
class RemoteRecord:
    id: str
    record_type: str
    title: str
    version: str = ""
    raw: dict[str, Any] | None = None


class BoldAdapter(Protocol):
    def list_records(self, record_type: str, *, limit: int = 20) -> dict[str, Any]: ...
    def get_record(self, record_type: str, record_id: str) -> RemoteRecord: ...
    def create_record(self, record_type: str, payload: dict[str, Any], idempotency_key: str) -> RemoteRecord: ...
    def update_record(self, record_type: str, record_id: str, payload: dict[str, Any], expected_version: str = "") -> RemoteRecord: ...


class UnconfiguredBold:
    def list_records(self, record_type: str, *, limit: int = 20):
        raise BoldUnavailable("Bold API is not configured.")

    def get_record(self, record_type: str, record_id: str):
        raise BoldUnavailable("Bold API and authentication have not been verified.")

    def create_record(self, record_type: str, payload: dict, idempotency_key: str):
        raise BoldUnavailable("Bold writes are disabled until its supported API is configured.")

    def update_record(self, record_type: str, record_id: str, payload: dict, expected_version: str = ""):
        raise BoldUnavailable("Bold updates require a verified API with conflict protection.")


class BoldRestClient:
    ROUTES = {"note": "notes", "task": "tasks", "person": "people", "company": "companies", "calendar_event": "calendarEvents"}

    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        if not base_url.startswith("https://"):
            raise BoldUnavailable("Bold API base URL must use HTTPS.")
        if not token:
            raise BoldUnavailable("BOLD_API_TOKEN is not configured.")
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    def _route(self, record_type: str) -> str:
        try:
            return self.ROUTES[record_type]
        except KeyError:
            raise BoldError(f"Unsupported Bold record type: {record_type}") from None

    def _request(self, method: str, path: str, *, params=None, payload=None, idempotency_key=None):
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        for attempt in range(3):
            try:
                response = httpx.request(method, f"{self.base_url}{path}", headers=headers, params=params, json=payload, timeout=self.timeout)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise BoldError("Bold API connection failed.") from exc
                time.sleep(0.25 * (2**attempt))
                continue
            if response.status_code in (401, 403):
                raise BoldAuthError("Bold rejected the configured token or role permissions.")
            if response.status_code == 429:
                if attempt == 2:
                    raise BoldError("Bold rate limit reached; retry later.")
                try:
                    delay = min(float(response.headers.get("Retry-After", "1")), 10.0)
                except ValueError:
                    delay = 1.0
                time.sleep(max(delay, 0.0))
                continue
            if response.status_code >= 500:
                if attempt == 2:
                    raise BoldError("Bold service is temporarily unavailable.")
                time.sleep(0.25 * (2**attempt))
                continue
            if response.status_code >= 400:
                raise BoldError(f"Bold rejected the request with HTTP {response.status_code}.")
            try:
                return response.json()
            except ValueError as exc:
                raise BoldError("Bold returned invalid JSON.") from exc
        raise BoldError("Bold request failed.")

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            values = [value for value in data.values() if isinstance(value, list)]
            if values:
                return [item for item in values[0] if isinstance(item, dict)]
            nested = [value for value in data.values() if isinstance(value, dict)]
            return [nested[0]] if nested else [data]
        return []

    @classmethod
    def _record(cls, payload: Any, record_type: str) -> RemoteRecord:
        records = cls._records(payload)
        if not records:
            raise BoldError("Bold returned no record.")
        item = records[0]
        record_id = str(item.get("id") or item.get("recordId") or "")
        if not record_id:
            raise BoldError("Bold returned a record without an ID.")
        return RemoteRecord(record_id, record_type, str(item.get("title") or item.get("name") or ""), str(item.get("updatedAt") or item.get("version") or ""), item)

    def list_records(self, record_type: str, *, limit: int = 20) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise BoldError("Bold list limit must be between 1 and 100.")
        payload = self._request("GET", f"/rest/{self._route(record_type)}", params={"limit": limit})
        return {"records": self._records(payload), "page_info": payload.get("pageInfo") if isinstance(payload, dict) else None, "total_count": payload.get("totalCount") if isinstance(payload, dict) else None}

    def get_record(self, record_type: str, record_id: str) -> RemoteRecord:
        return self._record(self._request("GET", f"/rest/{self._route(record_type)}/{record_id}"), record_type)

    def create_record(self, record_type: str, payload: dict[str, Any], idempotency_key: str) -> RemoteRecord:
        if not idempotency_key:
            raise BoldError("Bold creation requires an idempotency key.")
        return self._record(self._request("POST", f"/rest/{self._route(record_type)}", payload=payload, idempotency_key=idempotency_key), record_type)

    def update_record(self, record_type: str, record_id: str, payload: dict[str, Any], expected_version: str = "") -> RemoteRecord:
        body = dict(payload)
        if expected_version:
            body["_expectedVersion"] = expected_version
        return self._record(self._request("PATCH", f"/rest/{self._route(record_type)}/{record_id}", payload=body), record_type)
