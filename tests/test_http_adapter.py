from __future__ import annotations

from io import BytesIO
import json
import unittest

from psycopg_pool import PoolTimeout

from fin_ops_platform.app.http_adapter import HttpRequestLimits, WsgiHttpAdapter
from fin_ops_platform.app.server import Response


class FakeApplication:
    def __init__(self, response: Response | None = None, error: Exception | None = None) -> None:
        self.response = response or Response(200, '{"status":"ok"}')
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def handle_request(self, method, path, body=None, headers=None):
        self.calls.append({"method": method, "path": path, "body": body, "headers": dict(headers or {})})
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        self.closed = True


def invoke(adapter: WsgiHttpAdapter, *, method: str = "GET", path: str = "/health", body: bytes = b"", content_type: str = "application/json", request_id: str = ""):
    status: list[str] = []
    headers: dict[str, str] = {}

    def start_response(value: str, values: list[tuple[str, str]]) -> None:
        status.append(value)
        headers.update(values)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)) if body else "",
        "wsgi.input": BytesIO(body),
    }
    if request_id:
        environ["HTTP_X_REQUEST_ID"] = request_id
    response_body = b"".join(adapter(environ, start_response))
    return status[0], headers, response_body


class WsgiHttpAdapterTests(unittest.TestCase):
    def test_dispatches_request_and_propagates_valid_request_id(self) -> None:
        application = FakeApplication()

        status, headers, body = invoke(WsgiHttpAdapter(application), request_id="request-123")

        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["X-Request-ID"], "request-123")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(application.calls[0]["path"], "/health")

    def test_rejects_oversized_json_before_application_dispatch(self) -> None:
        application = FakeApplication()
        adapter = WsgiHttpAdapter(application, limits=HttpRequestLimits(json_bytes=4, multipart_bytes=8, other_bytes=8))

        status, _headers, body = invoke(adapter, method="POST", path="/api/test", body=b"12345")

        self.assertEqual(status, "413 Request Entity Too Large")
        self.assertEqual(json.loads(body)["error"], "request_body_too_large")
        self.assertEqual(application.calls, [])

    def test_rejects_incomplete_body_before_application_dispatch(self) -> None:
        application = FakeApplication()
        statuses: list[str] = []
        adapter = WsgiHttpAdapter(application)
        body = b"{}"
        response = b"".join(
            adapter(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": "/api/test",
                    "QUERY_STRING": "",
                    "CONTENT_TYPE": "application/json",
                    "CONTENT_LENGTH": "3",
                    "wsgi.input": BytesIO(body),
                },
                lambda status, _headers: statuses.append(status),
            )
        )

        self.assertEqual(statuses, ["400 Bad Request"])
        self.assertEqual(json.loads(response)["error"], "incomplete_request_body")
        self.assertEqual(application.calls, [])

    def test_database_pool_backpressure_maps_to_retryable_503(self) -> None:
        application = FakeApplication(error=PoolTimeout("pool exhausted"))

        status, headers, body = invoke(WsgiHttpAdapter(application))

        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(headers["Retry-After"], "1")
        self.assertEqual(json.loads(body)["error"], "database_backpressure")

    def test_close_releases_application_resources(self) -> None:
        application = FakeApplication()
        adapter = WsgiHttpAdapter(application)

        adapter.close()

        self.assertTrue(application.closed)


if __name__ == "__main__":
    unittest.main()
