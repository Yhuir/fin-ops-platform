from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_applicant_credentials import (
    InMemoryOaApplicantCredentialRepository,
    OaApplicantCredentialPermissionError,
    OaApplicantCredentialService,
    OaApplicantCredentialValidationError,
)


class OaApplicantCredentialServiceTests(unittest.TestCase):
    def test_admin_saves_and_lists_configured_credential_without_exposing_password(self) -> None:
        service = OaApplicantCredentialService(repository=InMemoryOaApplicantCredentialRepository())

        saved = service.save_credential(
            target_applicant_code="chen_xiuyun",
            target_applicant_name="陈秀云",
            oa_username="chen_xiuyun",
            password="correct-password",
            actor_id="YNSYLP005",
            can_admin_access=True,
        )
        listed = service.list_credentials(can_admin_access=True)
        secret = service.resolve_login_credential("chen_xiuyun")

        self.assertEqual(saved["credentialStatus"], "configured")
        self.assertTrue(saved["hasCredential"])
        self.assertEqual(saved["targetApplicantCode"], "chen_xiuyun")
        self.assertEqual(saved["targetApplicantName"], "陈秀云")
        self.assertEqual(saved["oaUsername"], "chen_xiuyun")
        self.assertNotIn("password", saved)
        self.assertEqual(listed["credentials"], [saved])
        self.assertEqual(secret.oa_username, "chen_xiuyun")
        self.assertEqual(secret.password, "correct-password")

    def test_non_admin_cannot_save_or_list_credentials(self) -> None:
        service = OaApplicantCredentialService(repository=InMemoryOaApplicantCredentialRepository())

        with self.assertRaises(OaApplicantCredentialPermissionError):
            service.save_credential(
                target_applicant_code="chen_xiuyun",
                target_applicant_name="陈秀云",
                oa_username="chen_xiuyun",
                password="correct-password",
                actor_id="FULL001",
                can_admin_access=False,
            )
        with self.assertRaises(OaApplicantCredentialPermissionError):
            service.list_credentials(can_admin_access=False)

    def test_save_rejects_empty_required_fields_and_password(self) -> None:
        service = OaApplicantCredentialService(repository=InMemoryOaApplicantCredentialRepository())

        with self.assertRaises(OaApplicantCredentialValidationError):
            service.save_credential(
                target_applicant_code="",
                target_applicant_name="陈秀云",
                oa_username="chen_xiuyun",
                password="correct-password",
                actor_id="YNSYLP005",
                can_admin_access=True,
            )
        with self.assertRaises(OaApplicantCredentialValidationError):
            service.save_credential(
                target_applicant_code="chen_xiuyun",
                target_applicant_name="陈秀云",
                oa_username="chen_xiuyun",
                password="",
                actor_id="YNSYLP005",
                can_admin_access=True,
            )

    def test_delete_returns_to_unconfigured_state_without_audit_history_requirement(self) -> None:
        service = OaApplicantCredentialService(repository=InMemoryOaApplicantCredentialRepository())
        service.save_credential(
            target_applicant_code="chen_xiuyun",
            target_applicant_name="陈秀云",
            oa_username="chen_xiuyun",
            password="correct-password",
            actor_id="YNSYLP005",
            can_admin_access=True,
        )

        deleted = service.delete_credential(
            target_applicant_code="chen_xiuyun",
            actor_id="YNSYLP005",
            can_admin_access=True,
        )

        self.assertEqual(deleted["credentialStatus"], "unconfigured")
        self.assertFalse(deleted["hasCredential"])
        self.assertIsNone(service.resolve_login_credential("chen_xiuyun"))


if __name__ == "__main__":
    unittest.main()
