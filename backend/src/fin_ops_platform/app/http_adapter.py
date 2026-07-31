from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from time import monotonic
from typing import Any, Iterable
from uuid import uuid4

from psycopg_pool import PoolTimeout, TooManyRequests

from fin_ops_platform.app.server import Application, Response
from fin_ops_platform.services.http_runtime_metrics import HTTP_RUNTIME_METRICS


LOGGER = logging.getLogger("fin_ops_platform.http")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class HttpRequestLimits:
    json_bytes: int = 2 * 1024 * 1024
    multipart_bytes: int = 128 * 1024 * 1024
    other_bytes: int = 8 * 1024 * 1024

    @classmethod
    def from_env(cls) -> HttpRequestLimits:
        return cls(
            json_bytes=_positive_int_env("FIN_OPS_HTTP_JSON_BODY_MAX_BYTES", cls.json_bytes),
            multipart_bytes=_positive_int_env("FIN_OPS_HTTP_MULTIPART_BODY_MAX_BYTES", cls.multipart_bytes),
            other_bytes=_positive_int_env("FIN_OPS_HTTP_OTHER_BODY_MAX_BYTES", cls.other_bytes),
        )

    def for_content_type(self, content_type: str) -> int:
        normalized = str(content_type or "").lower()
        if "multipart/form-data" in normalized:
            return self.multipart_bytes
        if "json" in normalized:
            return self.json_bytes
        return self.other_bytes


class WsgiHttpAdapter:
    def __init__(self, application: Application, *, limits: HttpRequestLimits | None = None) -> None:
        self._application = application
        self._limits = limits or HttpRequestLimits.from_env()

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        started_at = monotonic()
        active_requests = HTTP_RUNTIME_METRICS.request_started()
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = self._request_path(environ)
        request_id = self._request_id(environ)
        status_code = int(HTTPStatus.INTERNAL_SERVER_ERROR)
        try:
            body, body_error = self._read_body(environ, method=method, request_id=request_id)
            response = body_error or self._dispatch(method, path, body, self._headers(environ), request_id)
            status_code = int(response.status_code)
            response.headers.setdefault("X-Request-ID", request_id)
            encoded = response.body.encode("utf-8") if isinstance(response.body, str) else bytes(response.body)
            response.headers.setdefault("Content-Length", str(len(encoded)))
            start_response(
                f"{status_code} {HTTPStatus(status_code).phrase}",
                [(str(key), str(value)) for key, value in response.headers.items()],
            )
            self._finish_request(
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                started_at=started_at,
                active_requests=active_requests,
            )
            return [encoded]
        except Exception:
            self._finish_request(
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                started_at=started_at,
                active_requests=active_requests,
                error=True,
            )
            raise

    def close(self) -> None:
        self._application.close()

    def _dispatch(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
        request_id: str,
    ) -> Response:
        try:
            return self._application.handle_request(method, path, body=body, headers=headers)
        except (PoolTimeout, TooManyRequests):
            HTTP_RUNTIME_METRICS.reject_database_backpressure()
            return self._json_error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "database_backpressure",
                "服务繁忙，请稍后重试。",
                request_id,
                retry_after="1",
            )
        except Exception:
            LOGGER.exception(
                json.dumps(
                    {
                        "event": "http_unhandled_error",
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                    },
                    ensure_ascii=False,
                )
            )
            return self._json_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "internal_server_error",
                "接口处理失败，请联系管理员查看后端日志。",
                request_id,
            )

    def _read_body(
        self,
        environ: dict[str, Any],
        *,
        method: str,
        request_id: str,
    ) -> tuple[bytes | None, Response | None]:
        if method not in BODY_METHODS:
            return None, None
        raw_length = str(environ.get("CONTENT_LENGTH") or "").strip()
        if not raw_length:
            return None, None
        try:
            content_length = int(raw_length)
        except ValueError:
            HTTP_RUNTIME_METRICS.reject_body()
            return None, self._json_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length 必须是非负整数。",
                request_id,
            )
        if content_length < 0:
            HTTP_RUNTIME_METRICS.reject_body()
            return None, self._json_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length 必须是非负整数。",
                request_id,
            )
        limit = self._limits.for_content_type(str(environ.get("CONTENT_TYPE") or ""))
        if content_length > limit:
            HTTP_RUNTIME_METRICS.reject_body()
            return None, self._json_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "request_body_too_large",
                f"请求体超过 {limit} 字节限制。",
                request_id,
            )
        if content_length == 0:
            return None, None
        body = environ["wsgi.input"].read(content_length)
        if len(body) != content_length:
            HTTP_RUNTIME_METRICS.reject_body()
            return None, self._json_error(
                HTTPStatus.BAD_REQUEST,
                "incomplete_request_body",
                "请求体长度与 Content-Length 不一致。",
                request_id,
            )
        return body, None

    @staticmethod
    def _headers(environ: dict[str, Any]) -> dict[str, str]:
        headers = {
            key.removeprefix("HTTP_").replace("_", "-").title(): str(value)
            for key, value in environ.items()
            if key.startswith("HTTP_") and value is not None
        }
        if environ.get("CONTENT_TYPE"):
            headers["Content-Type"] = str(environ["CONTENT_TYPE"])
        if environ.get("CONTENT_LENGTH"):
            headers["Content-Length"] = str(environ["CONTENT_LENGTH"])
        return headers

    @staticmethod
    def _request_path(environ: dict[str, Any]) -> str:
        path = str(environ.get("PATH_INFO") or "/")
        query = str(environ.get("QUERY_STRING") or "")
        return f"{path}?{query}" if query else path

    @staticmethod
    def _request_id(environ: dict[str, Any]) -> str:
        candidate = str(environ.get("HTTP_X_REQUEST_ID") or "").strip()
        return candidate if REQUEST_ID_RE.match(candidate) else uuid4().hex

    @staticmethod
    def _json_error(
        status: HTTPStatus,
        error: str,
        message: str,
        request_id: str,
        *,
        retry_after: str | None = None,
    ) -> Response:
        headers = {"Content-Type": "application/json; charset=utf-8", "X-Request-ID": request_id}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        return Response(
            status_code=int(status),
            body=json.dumps({"error": error, "message": message, "requestId": request_id}, ensure_ascii=False),
            headers=headers,
        )

    @staticmethod
    def _finish_request(
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        started_at: float,
        active_requests: int,
        error: bool = False,
    ) -> None:
        remaining = HTTP_RUNTIME_METRICS.request_finished()
        log = LOGGER.error if error else LOGGER.info
        log(
            json.dumps(
                {
                    "event": "http_access",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": round((monotonic() - started_at) * 1000, 3),
                    "active_requests_at_start": active_requests,
                    "active_requests": remaining,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )


def _positive_int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value
