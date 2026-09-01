-- fin-ops OA menu visibility helper for one account.
-- App page permissions remain in PostgreSQL; OA only projects whether the account
-- can see the app entry. Run only after the exact two-role topology is active.
--
-- Supported access values: hidden, user, admin.
-- admin is valid only for fixed account YNSYLP005.

SET @target_username = 'YNSYLP005';
SET @target_access = 'admin';
SET @user_role_key = 'finops_app_user';
SET @admin_role_key = 'finops_admin';

SET @target_user_count = (SELECT COUNT(*) FROM sys_user WHERE user_name = @target_username AND status = '0' AND del_flag = '0');
SET @user_role_count = (SELECT COUNT(*) FROM sys_role WHERE role_key = @user_role_key);
SET @admin_role_count = (SELECT COUNT(*) FROM sys_role WHERE role_key = @admin_role_key);
SET @target_user_id = IF(@target_user_count = 1, (SELECT MIN(user_id) FROM sys_user WHERE user_name = @target_username), NULL);
SET @user_role_id = IF(@user_role_count = 1, (SELECT MIN(role_id) FROM sys_role WHERE role_key = @user_role_key), NULL);
SET @admin_role_id = IF(@admin_role_count = 1, (SELECT MIN(role_id) FROM sys_role WHERE role_key = @admin_role_key), NULL);
SET @target_request_valid = (
  @target_access IN ('hidden', 'user', 'admin')
  AND (@target_access <> 'admin' OR @target_username = 'YNSYLP005')
  AND (@target_access <> 'user' OR @target_username <> 'YNSYLP005')
  AND @target_user_count = 1
  AND @user_role_count = 1
  AND @admin_role_count = 1
);

START TRANSACTION;

DELETE FROM sys_user_role
WHERE user_id = @target_user_id
  AND @target_request_valid
  AND role_id IN (@user_role_id, @admin_role_id);

INSERT INTO sys_user_role (user_id, role_id)
SELECT @target_user_id, @user_role_id
WHERE @target_request_valid AND @target_access = 'user';

INSERT INTO sys_user_role (user_id, role_id)
SELECT @target_user_id, @admin_role_id
WHERE @target_request_valid AND @target_access = 'admin';

COMMIT;

SELECT u.user_name, r.role_key
FROM sys_user_role ur
JOIN sys_user u ON u.user_id = ur.user_id
JOIN sys_role r ON r.role_id = ur.role_id
WHERE u.user_name = @target_username
  AND r.role_key IN (@user_role_key, @admin_role_key)
ORDER BY r.role_key;

SELECT @target_request_valid AS request_valid;
