from __future__ import annotations

import unittest

from fin_ops_platform.app.http_upload import MultipartBodyError, MultipartLimits, parse_multipart_body


def multipart(parts: list[bytes], boundary: str = "finops-boundary") -> tuple[bytes, str]:
    delimiter = f"--{boundary}".encode()
    body = b"\r\n".join([piece for part in parts for piece in (delimiter, part)] + [delimiter + b"--", b""])
    return body, f"multipart/form-data; boundary={boundary}"


class HttpUploadTests(unittest.TestCase):
    def test_parses_text_fields_and_files(self) -> None:
        body, content_type = multipart(
            [
                b'Content-Disposition: form-data; name="month"\r\n\r\n2026-05',
                b'Content-Disposition: form-data; name="files"; filename="invoice.txt"\r\nContent-Type: text/plain\r\n\r\ncontent',
            ]
        )

        fields, files = parse_multipart_body(body, content_type)

        self.assertEqual(fields, {"month": ["2026-05"]})
        self.assertEqual(files[0].file_name, "invoice.txt")
        self.assertEqual(files[0].content, b"content")

    def test_rejects_oversized_file_and_too_many_parts(self) -> None:
        body, content_type = multipart(
            [b'Content-Disposition: form-data; name="files"; filename="big.bin"\r\n\r\n12345']
        )
        with self.assertRaises(MultipartBodyError) as oversized:
            parse_multipart_body(body, content_type, limits=MultipartLimits(max_file_bytes=4))
        self.assertEqual(oversized.exception.error, "upload_file_too_large")
        self.assertEqual(oversized.exception.status_code, 413)

        two_parts, content_type = multipart(
            [
                b'Content-Disposition: form-data; name="a"\r\n\r\n1',
                b'Content-Disposition: form-data; name="b"\r\n\r\n2',
            ]
        )
        with self.assertRaises(MultipartBodyError) as too_many:
            parse_multipart_body(two_parts, content_type, limits=MultipartLimits(max_parts=1))
        self.assertEqual(too_many.exception.error, "multipart_too_many_parts")

    def test_rejects_missing_boundary(self) -> None:
        with self.assertRaises(MultipartBodyError) as error:
            parse_multipart_body(b"invalid", "multipart/form-data")
        self.assertEqual(error.exception.error, "invalid_multipart_body")


if __name__ == "__main__":
    unittest.main()
