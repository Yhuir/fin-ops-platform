from __future__ import annotations

import asyncio
import ctypes
import json
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import bson
import pymongo
from bson import json_util
from bson.errors import InvalidBSON
from pymongo.errors import ConfigurationError, InvalidURI
from pymongo.uri_parser_shared import split_hosts


class DriverSecurityTests(unittest.TestCase):
    def test_gridfs_delete_uses_literal_id_in_both_drivers(self):
        from gridfs import AsyncGridFSBucket, GridFSBucket

        identity = {"$ne": "unrelated"}
        client = pymongo.MongoClient(connect=False)
        self.addCleanup(client.close)
        bucket = GridFSBucket(client.test)
        bucket._files = Mock()
        bucket._files.delete_one.return_value.deleted_count = 1
        bucket._chunks = Mock()
        bucket.delete(identity)
        bucket._files.delete_one.assert_called_once_with({"_id": {"$eq": identity}}, session=None)
        bucket._chunks.delete_many.assert_called_once_with({"files_id": {"$eq": identity}}, session=None)

        async def check_async():
            client = pymongo.AsyncMongoClient(connect=False)
            try:
                bucket = AsyncGridFSBucket(client.test)
                bucket._files = AsyncMock()
                bucket._files.delete_one.return_value = SimpleNamespace(deleted_count=1)
                bucket._chunks = AsyncMock()
                await bucket.delete(identity)
                bucket._files.delete_one.assert_awaited_once_with({"_id": {"$eq": identity}}, session=None)
                bucket._chunks.delete_many.assert_awaited_once_with({"files_id": {"$eq": identity}}, session=None)
            finally:
                await client.close()

        asyncio.run(check_async())

    def test_installed_release_has_native_extensions(self):
        self.assertEqual(pymongo.version, "4.17.0+finops.1")
        self.assertTrue(bson.has_c())

    def test_uri_rejects_encoded_hostname_without_breaking_sockets_or_ipv6(self):
        for host in ("example.com%2Cexample.org%3A27017", "example.com%2F27017"):
            with self.subTest(host=host), self.assertRaises(InvalidURI):
                split_hosts(host)
            with self.assertRaises(InvalidURI):
                pymongo.MongoClient(f"mongodb://{host}", connect=False)
        self.assertEqual(split_hosts("%2Ftmp%2Fmongo.sock"), [("/tmp/mongo.sock", None)])
        self.assertEqual(split_hosts("[fe80::1%25eth0]:27017"), [("fe80::1%eth0", 27017)])

    def test_bson_native_buffer_rejects_overflow_without_large_allocation(self):
        # Exercise the actual compiled fix with a synthetic position; allocate
        # only the driver's initial buffer, never a multi-gigabyte test string.
        lib = ctypes.PyDLL(bson._cbson.__file__)
        lib.pymongo_buffer_new.restype = ctypes.c_void_p
        lib.pymongo_buffer_update_position.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.pymongo_buffer_save_space.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.pymongo_buffer_free.argtypes = [ctypes.c_void_p]
        buffer = lib.pymongo_buffer_new()
        self.assertTrue(buffer)
        try:
            with self.assertRaisesRegex(ValueError, "BSON size limit"):
                lib.pymongo_buffer_save_space(buffer, -1)
            lib.pymongo_buffer_update_position(buffer, 2**31 - 2)
            with self.assertRaisesRegex(ValueError, "BSON size limit"):
                lib.pymongo_buffer_save_space(buffer, 4)
        finally:
            lib.pymongo_buffer_free(buffer)

    def test_bson_embedded_document_cannot_consume_terminator_or_read_past_buffer(self):
        valid = bson.encode({"0": {"a": 1}})
        self.assertEqual(bson._array_of_documents_to_buffer(valid), bson.encode({"a": 1}))
        for length in (len(valid) - 7, 32767):
            malformed = bytearray(valid)
            malformed[7:11] = struct.pack("<i", length)
            with self.assertRaises(InvalidBSON):
                bson._array_of_documents_to_buffer(bytes(malformed))

    def test_extended_json_timestamp_rejects_unexpected_fields(self):
        for payload in ({"$timestamp": {"t": 1, "i": 2, "extra": 3}}, {"$timestamp": 1}):
            with self.assertRaises(TypeError):
                json_util.loads(json.dumps(payload))
        self.assertEqual(json_util.loads('{"$timestamp":{"t":1,"i":2}}'), bson.Timestamp(1, 2))

    def test_kms_socket_endpoint_is_rejected_before_network_io_in_both_drivers(self):
        for mode in ("synchronous", "asynchronous"):
            module = __import__(f"pymongo.{mode}.encryption", fromlist=["_EncryptionIO"])
            io = object.__new__(module._EncryptionIO)
            io._kms_ssl_contexts = {"aws": object()}
            context = SimpleNamespace(endpoint="/tmp/kms.sock", message=b"request", kms_provider="aws")
            with patch.object(module, "PoolOptions"), patch.object(module, "_connect_kms") as connect:
                with self.assertRaisesRegex(ConfigurationError, "Invalid KMS endpoint"):
                    if mode == "synchronous":
                        io.kms_request(context)
                    else:
                        asyncio.run(io.kms_request(context))
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
