from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fin_ops_platform.services.object_storage import ObjectStorageConfigurationError, ObjectStorageSettings


class ObjectStorageSettingsTests(unittest.TestCase):
    def test_from_env_defaults_to_disabled_local_boundary(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = ObjectStorageSettings.from_env()

        self.assertEqual(settings.backend, "local")
        self.assertFalse(settings.enabled)

    def test_s3_settings_require_bucket_and_credentials_without_constructing_client(self) -> None:
        with patch.dict(os.environ, {"OBJECT_STORAGE_BACKEND": "s3"}, clear=True):
            with self.assertRaises(ObjectStorageConfigurationError):
                ObjectStorageSettings.from_env()

    def test_minio_settings_accept_s3_compatible_endpoint(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OBJECT_STORAGE_BACKEND": "minio",
                "S3_ENDPOINT_URL": "http://minio.internal:9000",
                "S3_BUCKET": "fin-ops-files",
                "S3_REGION": "cn-north-1",
                "S3_ACCESS_KEY_ID": "access",
                "S3_SECRET_ACCESS_KEY": "secret",
            },
            clear=True,
        ):
            settings = ObjectStorageSettings.from_env()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.backend, "minio")
        self.assertEqual(settings.endpoint_url, "http://minio.internal:9000")
        self.assertEqual(settings.bucket, "fin-ops-files")


if __name__ == "__main__":
    unittest.main()
