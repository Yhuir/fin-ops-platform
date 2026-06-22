from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_ENV_EXAMPLE = REPO_ROOT / "deploy/oa/env/fin-ops.common.env.example"
SECRETS_ENV_EXAMPLE = REPO_ROOT / "deploy/oa/env/fin-ops.secrets.env.example"


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

    def test_production_env_examples_match_runtime_redis_settings_contract(self) -> None:
        common_env = COMMON_ENV_EXAMPLE.read_text(encoding="utf-8")
        secrets_env = SECRETS_ENV_EXAMPLE.read_text(encoding="utf-8")

        for name in (
            "FIN_OPS_REDIS_KEY_PREFIX",
            "FIN_OPS_REDIS_WAKEUP_CHANNEL",
            "FIN_OPS_REDIS_DEFAULT_TTL_SECONDS",
        ):
            self.assertIn(f"{name}=", common_env)
        self.assertIn("FIN_OPS_REDIS_URL=", secrets_env)

        with patch.dict(
            os.environ,
            {
                "FIN_OPS_REDIS_URL": "redis://127.0.0.1:6379/0",
                "FIN_OPS_REDIS_KEY_PREFIX": "finops-prod",
                "FIN_OPS_REDIS_WAKEUP_CHANNEL": "finops:runtime:wakeup:prod",
                "FIN_OPS_REDIS_DEFAULT_TTL_SECONDS": "45",
            },
            clear=True,
        ):
            settings = RuntimeRedisSettings.from_env()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.url, "redis://127.0.0.1:6379/0")
        self.assertEqual(settings.key_prefix, "finops-prod")
        self.assertEqual(settings.wakeup_channel, "finops:runtime:wakeup:prod")
        self.assertEqual(settings.default_ttl_seconds, 45)

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

    def test_helper_supports_plain_text_version_keys(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertTrue(helper.set_text("workbench:version:all", "v7", ttl_seconds=60))
        self.assertEqual(helper.get_text("workbench:version:all"), "v7")

        self.assertEqual(client.calls[0], ("set", ("finops:workbench:version:all", "v7"), {"ex": 60}))
        with self.assertRaises(ValueError):
            helper.set_text("bad", "v1", ttl_seconds=0)

    def test_lock_uses_set_nx_with_ttl(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertTrue(helper.acquire_lock("dirty-scope", owner="worker-1", ttl_seconds=30))

        self.assertEqual(client.calls[0], ("set", ("finops:lock:dirty-scope", "worker-1"), {"ex": 30, "nx": True}))

    def test_health_summary_pings_configured_redis(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertEqual(helper.health_summary(), {"redis_status": "ready", "redis_hit_count": 0, "redis_miss_count": 0})
        self.assertEqual(client.calls[0], ("ping", (), {}))

    def test_health_summary_reports_redis_errors(self) -> None:
        helper = RuntimeRedisHelper(client=FailingRedisClient(), key_prefix="finops")

        self.assertEqual(
            helper.health_summary(),
            {"redis_status": "error", "redis_error": "redis unavailable", "redis_hit_count": 0, "redis_miss_count": 0},
        )

    def test_health_summary_reports_cache_hit_and_miss_counts(self) -> None:
        client = FakeRedisClient()
        helper = RuntimeRedisHelper(client=client, key_prefix="finops")

        self.assertIsNone(helper.get_json("missing"))
        self.assertTrue(helper.set_json("ready", {"ok": True}, ttl_seconds=15))
        self.assertEqual(helper.get_json("ready"), {"ok": True})

        self.assertEqual(helper.health_summary()["redis_hit_count"], 1)
        self.assertEqual(helper.health_summary()["redis_miss_count"], 1)


if __name__ == "__main__":
    unittest.main()
