from __future__ import annotations

import unittest

import httpx

from ai_deep_agents_assistant.app.services.daily_report_api_client import (
    DailyReportApiClient,
    DailyReportApiError,
    DailyReportAuthError,
)
from ai_deep_agents_assistant.app.services.request_context import ErpRequestContext


class DailyReportApiClientTests(unittest.TestCase):
    user = ErpRequestContext(
        user_id="863",
        uid="863",
        authorization="Bearer test-token",
    )

    def _client(self, handler):
        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)
        return DailyReportApiClient(
            http_client=http_client,
            base_url="https://erp.example.test",
        )

    def test_forwards_authorization_and_uid(self) -> None:
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(request.headers)
            return httpx.Response(200, json={"code": 200, "data": {}})

        result = self._client(handler).get_config(self.user)

        self.assertEqual(result["code"], 200)
        self.assertEqual(captured_headers["authorization"], "Bearer test-token")
        self.assertEqual(captured_headers["uid"], "863")

    def test_http_401_becomes_auth_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "token rejected"})

        with self.assertRaisesRegex(DailyReportAuthError, "ERP登录状态无效"):
            self._client(handler).get_config(self.user)

    def test_business_401_becomes_auth_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"code": 401, "message": "token expired"},
            )

        with self.assertRaisesRegex(DailyReportAuthError, "ERP登录状态无效"):
            self._client(handler).get_form_fields(self.user)

    def test_other_business_error_is_not_treated_as_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"code": 500, "message": "business rejected"},
            )

        with self.assertRaisesRegex(DailyReportApiError, "code=500"):
            self._client(handler).get_draft(self.user, 1, "2026-08-18")


if __name__ == "__main__":
    unittest.main()
