from __future__ import annotations

import unittest
from dataclasses import replace
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
    def test_remark_only_update_preserves_password_verification_and_disabled_state_without_oa(self):
        repo = InMemoryOaApplicantCredentialRepository()
        original = save(credential_service(repo))
        code = original["targetApplicantCode"]
        record = replace(repo.get_credential(code), enabled=False)
        repo.save_credential(summary=record, password=" secret ", actor_id="test", expected_version=1)
        service = OaApplicantCredentialService(repository=repo)
        updated = service.save_credential(oa_user_id="7", remark=" 新备注 ", actor_id="admin",
            can_admin_access=True, target_applicant_code=code, expected_version=1)
        self.assertEqual(updated["remark"], "新备注")
        self.assertEqual(updated["verifiedAt"], original["verifiedAt"])
        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(service.applicant_options(), [])
        self.assertEqual(repo.read_password_for_verification(code, 2).password, " secret ")

    def test_legacy_verification_uses_stored_password_and_keeps_code(self):
        repo = InMemoryOaApplicantCredentialRepository()
        repo.save_credential(summary=OaApplicantCredentialSummary("legacy", "旧名", "LOGIN-7", "configured", True),
            password=" old secret ", actor_id="test", expected_version=None)
        calls = []
        service = credential_service(repo, login=lambda *args: calls.append(args) or "token")
        self.assertEqual(service.applicant_options(), [])
        result = service.save_credential(oa_user_id="7", remark="报销", actor_id="admin", can_admin_access=True,
            target_applicant_code="legacy", expected_version=1)
        self.assertEqual(calls, [("login-7", " old secret ")])
        self.assertEqual(result["targetApplicantCode"], "legacy")
        self.assertEqual(result["oaUserId"], "7")
        self.assertTrue(result["verifiedAt"])
        self.assertEqual(service.resolve_login_credential("legacy").password, " old secret ")
        self.assertEqual(service.applicant_options(), [{"code": "legacy", "name": "陈秀云", "remark": "报销"}])

    def test_omitted_password_create_null_password_and_unconfigured_preserve_are_invalid(self):
        repo = InMemoryOaApplicantCredentialRepository()
        service = credential_service(repo)
        with self.assertRaises(OaApplicantCredentialValidationError):
            service.save_credential(oa_user_id="7", remark="", actor_id="admin", can_admin_access=True)
        original = save(service)
        with self.assertRaises(OaApplicantCredentialValidationError):
            save(service, password=None, target_applicant_code=original["targetApplicantCode"], expected_version=1)
        repo.save_credential(summary=OaApplicantCredentialSummary("empty", "旧名", "login-7", "missing", False),
            password="", actor_id="test", expected_version=None)
        with self.assertRaises(OaApplicantCredentialValidationError):
            service.save_credential(oa_user_id="7", remark="", actor_id="admin", can_admin_access=True,
                target_applicant_code="empty", expected_version=1)

    def test_new_password_failure_never_retries_stored_password(self):
        repo = InMemoryOaApplicantCredentialRepository()
        original = save(credential_service(repo))
        calls = []
        def reject(username, password):
            calls.append((username, password))
            raise TargetOaApplicantLoginError("密码错误")
        with self.assertRaises(OaApplicantCredentialVerificationError):
            save(credential_service(repo, login=reject), password="wrong", remark="new",
                target_applicant_code=original["targetApplicantCode"], expected_version=1)
        self.assertEqual(calls, [("login-7", "wrong")])
        self.assertEqual(credential_service(repo).list_credentials(can_admin_access=True)["credentials"], [original])

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
