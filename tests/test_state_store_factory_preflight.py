from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services import state_store_factory
class FakePostgresStateStore:
    def __init__(self, *, data_dir: Path, connection: object, sql_read_connection: object | None = None, **_kwargs: object) -> None:
        self.data_dir = data_dir
        self.connection = connection
        self.sql_read_connection = sql_read_connection

    @property
    def storage_backend(self) -> str:
        return "postgres"


class WarmableConnection:
    def __init__(self, settings: object) -> None:
        self.settings = settings
        self.warmed = False

    def warm_up(self) -> None:
        self.warmed = True


class StateStoreFactoryPreflightTests(unittest.TestCase):
    def test_local_pickle_preflight_backend_helper_is_removed(self) -> None:
        source = Path(state_store_factory.__file__).read_text(encoding="utf-8")

        self.assertNotIn("_required_preflight_backend", source)
        self.assertNotIn("Supported preflight backend values", source)
        self.assertNotIn("local_pickle and postgres", source)

    def test_default_auto_local_and_mongo_backends_are_removed(self) -> None:
        for backend in ["", "auto", "local", "local_pickle", "mongo", "mongo_pickle"]:
            with self.subTest(backend=backend), TemporaryDirectory() as temp_dir:
                env = {}
                if backend:
                    env[state_store_factory.APP_STORAGE_BACKEND_ENV] = backend

                with patch.dict("os.environ", env, clear=True):
                    with self.assertRaisesRegex(ValueError, "requires FIN_OPS_APP_STORAGE_BACKEND=postgres"):
                        state_store_factory.build_state_store(Path(temp_dir))

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

    def test_postgres_backend_warms_primary_and_optional_read_connections(self) -> None:
        write_settings = object()
        read_settings = object()
        created_connections: list[WarmableConnection] = []

        def create_connection(settings: object) -> WarmableConnection:
            connection = WarmableConnection(settings)
            created_connections.append(connection)
            return connection

        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "postgres",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://user:secret@db/fin_ops",
                "FIN_OPS_POSTGRES_READ_DATABASE_URL": "postgresql://readonly:secret@db/fin_ops",
            },
            clear=True,
        ), patch(
            "fin_ops_platform.services.postgres_connection.PostgresSettings.from_env", return_value=write_settings
        ), patch(
            "fin_ops_platform.services.postgres_connection.PostgresSettings.from_read_env", return_value=read_settings
        ), patch(
            "fin_ops_platform.services.postgres_connection.PostgresConnection", side_effect=create_connection
        ), patch(
            "fin_ops_platform.services.postgres_state_store.PostgresStateStore", FakePostgresStateStore
        ):
            store = state_store_factory.build_state_store(Path(temp_dir))

        self.assertIsInstance(store, FakePostgresStateStore)
        self.assertEqual([connection.settings for connection in created_connections], [write_settings, read_settings])
        self.assertTrue(all(connection.warmed for connection in created_connections))
        self.assertIs(store.connection, created_connections[0])
        self.assertIs(store.sql_read_connection, created_connections[1])

    def test_shadow_and_dual_backends_are_removed(self) -> None:
        for backend in ("shadow", "dual"):
            with self.subTest(backend=backend), TemporaryDirectory() as temp_dir, patch.dict(
                "os.environ",
                {state_store_factory.APP_STORAGE_BACKEND_ENV: backend},
                clear=True,
            ):
                with self.assertRaisesRegex(ValueError, "requires FIN_OPS_APP_STORAGE_BACKEND=postgres"):
                    state_store_factory.build_state_store(Path(temp_dir))

    def test_errors_redact_uri_password_and_token_values(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                state_store_factory.APP_STORAGE_BACKEND_ENV: "postgresql://user:secret@db/fin_ops?token=abc",
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


if __name__ == "__main__":
    unittest.main()
