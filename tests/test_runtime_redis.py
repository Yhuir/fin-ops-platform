from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings


class FakeRedisClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.values: dict[str, str] = {}

    def get(self, key: str):
        self.calls.append(("get", (key,), {}))
        return self.values.get(key)

    def set(self, *args, **kwargs):
        self.calls.append(("set", args, kwargs))
        if kwargs.get("nx") and args[0] in self.values:
            return False
        self.values[str(args[0])] = str(args[1])
        return True

    def delete(self, key: str):
        self.calls.append(("delete", (key,), {}))
        self.values.pop(key, None)
        return 1

    def publish(self, channel: str, message: str):
        self.calls.append(("publish", (channel, message), {}))
        return 1

    def ping(self):
        self.calls.append(("ping", (), {}))
        return True


class FailingRedisClient(FakeRedisClient):
    def ping(self):
        self.calls.append(("ping", (), {}))
        raise RuntimeError("redis unavailable")


class RuntimeRedisTests(unittest.TestCase):
    def test_settings_are_disabled_without_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = RuntimeRedisSettings.from_env()

        self.assertFalse(settings.enabled)

    def test_disabled_helper_is_noop_so_postgres_polling_can_continue(self) -> None:
        helper = RuntimeRedisHelper.disabled()

        self.assertFalse(helper.enabled)
        self.assertEqual(helper.health_summary(), {"redis_status": "disabled"})
        self.assertIsNone(helper.get_json("missing"))
        self.assertFalse(helper.set_json("key", {"value": 1}, ttl_seconds=30))
        self.assertFalse(helper.publish_wakeup("runtime"))
        self.assertFalse(helper.acquire_lock("lock", owner="worker-1", ttl_seconds=30))

    def test_helper_limits_cache_to_positive_ttl_and_uses_json_payloads(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertTrue(helper.set_json("month-summary", {"count": 2}, ttl_seconds=15))
        self.assertEqual(client.calls[0], ("set", ("finops:month-summary", json.dumps({"count": 2}, ensure_ascii=False, sort_keys=True)), {"ex": 15}))
        self.assertEqual(helper.get_json("month-summary"), {"count": 2})
        with self.assertRaises(ValueError):
            helper.set_json("bad", {"count": 1}, ttl_seconds=0)

    def test_lock_uses_set_nx_with_ttl(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertTrue(helper.acquire_lock("dirty-scope", owner="worker-1", ttl_seconds=30))

        self.assertEqual(client.calls[0], ("set", ("finops:lock:dirty-scope", "worker-1"), {"ex": 30, "nx": True}))

    def test_health_summary_pings_configured_redis(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertEqual(helper.health_summary(), {"redis_status": "ready"})
        self.assertEqual(client.calls[0], ("ping", (), {}))

    def test_health_summary_reports_redis_errors(self) -> None:
        helper = RuntimeRedisHelper(client=FailingRedisClient(), key_prefix="finops")

        self.assertEqual(helper.health_summary(), {"redis_status": "error", "redis_error": "redis unavailable"})


if __name__ == "__main__":
    unittest.main()
