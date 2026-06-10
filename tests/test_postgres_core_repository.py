import unittest

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


class _CaptureConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))


class PostgresCoreRepositoryTests(unittest.TestCase):
    def test_save_invoice_drops_weak_fingerprint_when_source_unique_key_exists(self) -> None:
        connection = _CaptureConnection()
        repository = PostgresCoreRepository(connection)

        repository._save_invoice(
            connection,
            {
                "id": "inv_existing_etc_stale",
                "invoice_type": "input",
                "invoice_no": "26537911470300077680",
                "digital_invoice_no": "26537911470300077680",
                "source_unique_key": "26537911470300077680",
                "data_fingerprint": "invoice:昆明新机场高速公路建设发展有限公司:2026-03-31:9.22",
                "invoice_date": "2026-03-31",
                "counterparty": {"id": "cp_etc", "name": "昆明新机场高速公路建设发展有限公司"},
                "seller_name": "昆明新机场高速公路建设发展有限公司",
                "amount": "9.22",
                "signed_amount": "9.22",
                "total_with_tax": "9.22",
            },
        )

        self.assertEqual(len(connection.calls), 1)
        params = connection.calls[0][1]
        self.assertEqual(params[5], "26537911470300077680")
        self.assertIsNone(params[6])


if __name__ == "__main__":
    unittest.main()
