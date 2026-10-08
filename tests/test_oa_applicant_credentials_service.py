from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.services.oa_applicant_credentials import (
    InMemoryOaApplicantCredentialRepository,
    OaApplicantCredentialConfigurationError,
    OaApplicantCredentialConflictError,
    OaApplicantCredentialNotFoundError,
    OaApplicantCredentialPermissionError,
    OaApplicantCredentialService,
    OaApplicantCredentialSummary,
    OaApplicantCredentialValidationError,
    OaApplicantCredentialVerificationError,
)
from fin_ops_platform.services.oa_identity_service import OAIdentityService, OAIdentitySettings
from fin_ops_platform.services.oa_role_sync_service import OAUserDirectoryEntry, OARoleSyncExecutionError
from fin_ops_platform.services.target_oa_applicant_token_provider import (
    TargetOaApplicantLoginError, TargetOaApplicantLoginUnavailableError,
)


class CredentialDirectory:
    users = [OAUserDirectoryEntry("login-7", "陈秀云", True, "7"),
             OAUserDirectoryEntry("login-8", "停用", False, "8")]

    def list_users(self):
        return self.users

    def get_user(self, identity):
        return next((user for user in self.users if user.user_id == identity), None)


def credential_service(repository=None, login=None, identity=None):
    return OaApplicantCredentialService(
        repository=repository or InMemoryOaApplicantCredentialRepository(), directory=CredentialDirectory(),
        login_client=SimpleNamespace(login=login or (lambda username, password: "verified-token")),
        identity_resolver=SimpleNamespace(resolve_identity=identity or (
            lambda token: SimpleNamespace(user_id="7", username="login-7"))),
    )


def save(service, **changes):
    return service.save_credential(**{"oa_user_id": "7", "password": " secret ", "remark": " 差旅 ",
                                      "actor_id": "admin", "can_admin_access": True, **changes})


class OaApplicantCredentialServiceTests(unittest.TestCase):
    def test_verified_save_preserves_password_and_returns_nonsecret_authoritative_identity(self):
        calls = []
        service = credential_service(login=lambda username, password: calls.append((username, password)) or "token")
        saved = save(service)
        self.assertEqual(calls, [("login-7", " secret ")])
        self.assertEqual(saved["targetApplicantName"], "陈秀云")
        self.assertEqual(saved["oaUsername"], "login-7")
        self.assertEqual(saved["remark"], "差旅")
        self.assertEqual(saved["oaUserId"], "7")
        self.assertEqual(saved["version"], 1)
        self.assertIsNotNone(saved["verifiedAt"])
        self.assertNotIn("password", saved)
        self.assertEqual(service.resolve_login_credential(saved["targetApplicantCode"]).password, " secret ")
        self.assertEqual(service.applicant_options(), [{"code": saved["targetApplicantCode"], "name": "陈秀云", "remark": "差旅"}])

    def test_permission_invalid_fields_and_disabled_or_missing_users_do_not_login(self):
        calls = []
        service = credential_service(login=lambda *args: calls.append(args))
        with self.assertRaises(OaApplicantCredentialPermissionError):
            save(service, can_admin_access=False)
        for change in ({"password": ""}, {"password": 1}, {"oa_user_id": 7}, {"oa_user_id": "missing"},
                       {"oa_user_id": "8"}, {"remark": None}, {"remark": "a" * 101}, {"expected_version": 1}):
            with self.subTest(change=change), self.assertRaises(OaApplicantCredentialValidationError):
                save(service, **change)
        self.assertEqual(calls, [])
        self.assertEqual(service.list_credentials(can_admin_access=True), {"credentials": []})

    def test_failed_verification_preserves_existing_record(self):
        for error, expected in ((TargetOaApplicantLoginError("密码错误"), OaApplicantCredentialVerificationError),
                                (TargetOaApplicantLoginUnavailableError("timeout"), OaApplicantCredentialConfigurationError)):
            repo = InMemoryOaApplicantCredentialRepository()
            service = credential_service(repo)
            original = save(service)
            failed = credential_service(repo, login=lambda *args: (_ for _ in ()).throw(error))
            with self.assertRaises(expected):
                save(failed, target_applicant_code=original["targetApplicantCode"], expected_version=1, remark="new")
            self.assertEqual(service.list_credentials(can_admin_access=True)["credentials"], [original])
        mismatched = credential_service(identity=lambda token: SimpleNamespace(user_id="9", username="login-7"))
        with self.assertRaisesRegex(OaApplicantCredentialVerificationError, "身份"):
            save(mismatched)
        self.assertEqual(mismatched.applicant_options(), [])

    def test_duplicate_update_version_delete_and_no_resurrection(self):
        service = credential_service()
        first = save(service)
        code = first["targetApplicantCode"]
        with self.assertRaises(OaApplicantCredentialConflictError):
            save(service)
        second = save(service, target_applicant_code=code, expected_version=1, remark="新版")
        self.assertEqual(second["version"], 2)
        with self.assertRaises(OaApplicantCredentialConflictError):
            save(service, target_applicant_code=code, expected_version=1)
        with self.assertRaises(OaApplicantCredentialValidationError):
            save(service, target_applicant_code=code, expected_version=2, oa_user_id="8")
        with self.assertRaises(OaApplicantCredentialConflictError):
            service.delete_credential(target_applicant_code=code, expected_version=1, actor_id="admin", can_admin_access=True)
        self.assertEqual(service.delete_credential(target_applicant_code=code, expected_version=2,
                         actor_id="admin", can_admin_access=True), {"deleted": True, "targetApplicantCode": code})
        with self.assertRaises(OaApplicantCredentialNotFoundError):
            save(service, target_applicant_code=code, expected_version=2)
        self.assertEqual(service.applicant_options(), [])
        self.assertIsNone(service.resolve_login_credential(code))

    def test_old_unverified_record_is_not_usable_and_rebind_keeps_internal_code(self):
        repo = InMemoryOaApplicantCredentialRepository()
        legacy = OaApplicantCredentialSummary("legacy", "旧名称", "LOGIN-7", "configured", True)
        repo.save_credential(summary=legacy, password="old", actor_id="admin", expected_version=None)
        service = credential_service(repo)
        self.assertEqual(service.applicant_options(), [])
        self.assertIsNone(service.resolve_login_credential("legacy"))
        saved = save(service, target_applicant_code="legacy", expected_version=1)
        self.assertEqual(saved["targetApplicantCode"], "legacy")
        self.assertEqual(saved["version"], 2)
        self.assertEqual(len(service.applicant_options()), 1)

    def test_directory_failure_missing_configuration_and_permissions_are_explicit(self):
        service = credential_service()
        with self.assertRaises(OaApplicantCredentialPermissionError):
            service.list_users(can_admin_access=False)
        self.assertEqual(len(service.list_users(can_admin_access=True)["users"]), 2)
        service._directory = SimpleNamespace(list_users=lambda: (_ for _ in ()).throw(OARoleSyncExecutionError("failed")))
        with self.assertRaises(OaApplicantCredentialConfigurationError):
            service.list_users(can_admin_access=True)
        missing = OaApplicantCredentialService(repository=InMemoryOaApplicantCredentialRepository())
        with self.assertRaises(OaApplicantCredentialConfigurationError):
            save(missing)

    def test_late_verified_update_cannot_revive_concurrently_deleted_record(self):
        repo = InMemoryOaApplicantCredentialRepository()
        service = credential_service(repo)
        first = save(service)
        code = first["targetApplicantCode"]
        def login(*args):
            repo.delete_credential(target_applicant_code=code, actor_id="admin", expected_version=1)
            return "token"
        racing = credential_service(repo, login=login)
        with self.assertRaises(OaApplicantCredentialConflictError):
            save(racing, target_applicant_code=code, expected_version=1)
        self.assertEqual(service.applicant_options(), [])

    def test_legacy_record_cannot_rebind_another_account_or_be_bypassed_by_create(self):
        repo = InMemoryOaApplicantCredentialRepository()
        legacy = OaApplicantCredentialSummary("legacy", "旧名称", "LOGIN-7", "configured", True)
        repo.save_credential(summary=legacy, password="old", actor_id="admin", expected_version=None)
        calls = []
        service = credential_service(repo, login=lambda *args: calls.append(args))
        with self.assertRaises(OaApplicantCredentialConflictError):
            save(service)
        service._directory = SimpleNamespace(get_user=lambda user_id: OAUserDirectoryEntry("other-login", "另一人", True, "9"))
        with self.assertRaisesRegex(OaApplicantCredentialValidationError, "原有"):
            save(service, target_applicant_code="legacy", expected_version=1, oa_user_id="9")
        self.assertEqual(calls, [])
        self.assertEqual(repo.get_credential("legacy"), legacy)

    def test_identity_transport_timeout_never_changes_saved_record(self):
        for error in (TimeoutError("synthetic timeout"), OSError("synthetic network failure")):
            with self.subTest(error=type(error).__name__):
                repo = InMemoryOaApplicantCredentialRepository()
                original = save(credential_service(repo))
                service = credential_service(repo)
                service._identity_resolver = OAIdentityService(
                    OAIdentitySettings(base_url="https://oa.example.test", cache_ttl_seconds=0))
                with patch("fin_ops_platform.services.oa_identity_service.urlopen", side_effect=error):
                    with self.assertRaises(OaApplicantCredentialConfigurationError):
                        save(service, target_applicant_code=original["targetApplicantCode"], expected_version=1)
                self.assertEqual(service.list_credentials(can_admin_access=True)["credentials"], [original])
