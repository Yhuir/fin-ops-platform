from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services import state_store_factory
from fin_ops_platform.services.state_store import ApplicationStateStore


class FakePostgresStateStore:
    def __init__(self, *, data_dir: Path, connection: object) -> None:
        self.data_dir = data_dir
        self.connection = connection

    @property
    def storage_backend(self) -> str:
        return "postgres"


class StateStoreFactoryPreflightTests(unittest.TestCase):
    def test_default_auto_local_and_mongo_backends_still_build_application_store(self) -> None:
        for backend in ["", "auto", "local", "local_pickle", "mongo", "mongo_pickle"]:
            with self.subTest(backend=backend), TemporaryDirectory() as temp_dir:
                env = {}
                if backend:
                    env[state_store_factory.APP_STORAGE_BACKEND_ENV] = backend

                with patch.dict("os.environ", env, clear=True):
                    store = state_store_factory.build_state_store(Path(temp_dir))

                self.assertIsInstance(store, ApplicationStateStore)

    def test_postgres_backend_still_builds_postgres_state_store(self) -> None:
        settings = object()
        connection = object()

        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {state_store_factory.APP_STORAGE_BACKEND_ENV: "postgres", "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://user:secret@db/fin_ops"},
            clear=True,
        ), patch(
            "fin_ops_platform.services.postgres_connection.PostgresSettings.from_env", return_value=settings
        ) as from_env, patch(
            "fin_ops_platform.services.postgres_connection.PostgresConnection", return_value=connection
        ) as connection_class, patch(
            "fin_ops_platform.services.postgres_state_store.PostgresStateStore", FakePostgresStateStore
        ):
            store = state_store_factory.build_state_store(Path(temp_dir))

        self.assertIsInstance(store, FakePostgresStateStore)
        self.assertIs(store.connection, connection)
        from_env.assert_called_once_with()
        connection_class.assert_called_once_with(settings)

    def test_shadow_requires_explicit_primary_and_shadow_backends(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {state_store_factory.APP_STORAGE_BACKEND_ENV: "shadow"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "FIN_OPS_PRIMARY_STORAGE_BACKEND"):
                state_store_factory.build_state_store(Path(temp_dir))

        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "shadow",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "FIN_OPS_SHADOW_STORAGE_BACKEND"):
                state_store_factory.build_state_store(Path(temp_dir))

    def test_dual_requires_explicit_primary_mirror_and_preflight_guard(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {state_store_factory.APP_STORAGE_BACKEND_ENV: "dual"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "FIN_OPS_PRIMARY_STORAGE_BACKEND"):
                state_store_factory.build_state_store(Path(temp_dir))

        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "dual",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "FIN_OPS_MIRROR_STORAGE_BACKEND"):
                state_store_factory.build_state_store(Path(temp_dir))

        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "dual",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_MIRROR_STORAGE_BACKEND": "postgres",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://user:secret@db/fin_ops",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "FIN_OPS_CUTOVER_PREFLIGHT_ONLY=1"):
                state_store_factory.build_state_store(Path(temp_dir))

    def test_preflight_modes_reject_app_mongo_backend_to_avoid_real_mongo_writer(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "shadow",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "mongo",
                "FIN_OPS_SHADOW_STORAGE_BACKEND": "local_pickle",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported FIN_OPS_PRIMARY_STORAGE_BACKEND='mongo'"):
                state_store_factory.build_state_store(Path(temp_dir))

    def test_shadow_wrapper_constructs_stores_without_postgres_when_not_selected(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "shadow",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_SHADOW_STORAGE_BACKEND": "local_pickle",
            },
            clear=True,
        ), patch("fin_ops_platform.services.postgres_connection.PostgresSettings.from_env") as from_env:
            store = state_store_factory.build_state_store(Path(temp_dir))

        self.assertEqual(store.storage_mode, "shadow")
        self.assertIsInstance(_primary_store(store), ApplicationStateStore)
        self.assertIsInstance(_shadow_store(store), ApplicationStateStore)
        from_env.assert_not_called()

    def test_dual_wrapper_constructs_postgres_only_for_selected_backend(self) -> None:
        settings = object()
        connection = object()

        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "dual",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_MIRROR_STORAGE_BACKEND": "postgres",
                "FIN_OPS_CUTOVER_PREFLIGHT_ONLY": "1",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://user:secret@db/fin_ops",
            },
            clear=True,
        ), patch(
            "fin_ops_platform.services.postgres_connection.PostgresSettings.from_env", return_value=settings
        ) as from_env, patch(
            "fin_ops_platform.services.postgres_connection.PostgresConnection", return_value=connection
        ), patch(
            "fin_ops_platform.services.postgres_state_store.PostgresStateStore", FakePostgresStateStore
        ):
            store = state_store_factory.build_state_store(Path(temp_dir))

        self.assertEqual(store.storage_backend, "dual")
        self.assertIsInstance(store.primary_store, ApplicationStateStore)
        self.assertIsInstance(store.mirror_store, FakePostgresStateStore)
        from_env.assert_called_once_with()

    def test_errors_redact_uri_password_and_token_values(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "shadow",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "postgresql://user:secret@db/fin_ops?token=abc",
                "FIN_OPS_SHADOW_STORAGE_BACKEND": "local_pickle",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError) as error:
                state_store_factory.build_state_store(Path(temp_dir))

        message = str(error.exception)
        self.assertNotIn("secret", message)
        self.assertNotIn("token=abc", message)
        self.assertNotIn("postgresql://user:secret@db", message)
        self.assertIn("<redacted-uri>", message)

    def test_shadow_sample_rate_is_validated(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "shadow",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_SHADOW_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE": "1.5",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE"):
                state_store_factory.build_state_store(Path(temp_dir))

    def test_dual_strict_flag_is_forwarded_to_wrapper(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "dual",
                "FIN_OPS_PRIMARY_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_MIRROR_STORAGE_BACKEND": "local_pickle",
                "FIN_OPS_CUTOVER_PREFLIGHT_ONLY": "1",
                "FIN_OPS_DUAL_WRITE_STRICT": "1",
            },
            clear=True,
        ):
            store = state_store_factory.build_state_store(Path(temp_dir))

        self.assertTrue(store._strict)


def _primary_store(store: object) -> object:
    return store.primary_store if hasattr(store, "primary_store") else store._primary  # type: ignore[attr-defined]


def _shadow_store(store: object) -> object:
    return store.shadow_store if hasattr(store, "shadow_store") else store._shadow  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
