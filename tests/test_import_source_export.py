from __future__ import annotations

import base64
import hashlib
import io
import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fin_ops_platform.tools import import_audit_repair_ops as command


class ImportSourceExportTests(unittest.TestCase):
    def run_export(self, *, content=b"original workbook", source=None):
        class Connection:
            def __init__(self):
                self.statements = []
                self.closed = False

            @contextmanager
            def transaction(self):
                yield self

            def execute(self, statement):
                self.statements.append(statement)

            def close(self):
                self.closed = True

        connection = Connection()
        output = io.StringIO()
        record = source if source is not None else {
            "file_id": "file-1", "session_id": "session-1", "original_filename": "original.xlsx",
            "stored_file_path": "registered-object-ref", "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        reader = Mock(return_value=content)
        with patch.object(command.PostgresSettings, "from_env", return_value=object()), \
             patch.object(command, "PostgresConnection", return_value=connection), \
             patch.object(command, "load_import_source_file", return_value=record) as lookup, \
             patch.object(command, "_build_bank_repair_state_store", return_value=SimpleNamespace(read_import_file=reader)):
            command.main(["--dry-run", "--export-source-file-id", "file-1"], stdout=output)
        lookup.assert_called_once_with(connection, "file-1")
        reader.assert_called_once_with("registered-object-ref")
        self.assertTrue(connection.closed)
        self.assertEqual(connection.statements, ["set transaction isolation level repeatable read, read only"])
        return json.loads(output.getvalue())

    def test_export_reads_registered_original_and_verifies_identity(self):
        result = self.run_export()
        self.assertTrue(result["read_only"])
        self.assertEqual(result["source_name"], "original.xlsx")
        self.assertEqual(base64.b64decode(result["content_base64"]), b"original workbook")
        self.assertNotIn("stored_file_path", result)

    def test_changed_bytes_are_not_exported(self):
        source = {"file_id": "file-1", "stored_file_path": "registered-object-ref", "sha256": "incorrect", "size_bytes": 17}
        with self.assertRaisesRegex(ValueError, "checksum or size mismatch"):
            self.run_export(source=source)

    def test_export_rejects_write_and_mixed_operations(self):
        for extra in (["--execute"], ["--dry-run", "--file-id", "another"]):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                command.main([*extra, "--export-source-file-id", "file-1"], stdout=io.StringIO())

    def test_export_rejects_interactive_terminal(self):
        output = Mock()
        output.isatty.return_value = True
        with self.assertRaisesRegex(SystemExit, "private task artifact"):
            command.main(["--dry-run", "--export-source-file-id", "file-1"], stdout=output)
