-- fin-ops user role sync helper
-- Use only after the fixed menu and three dedicated role bindings already pass exact topology verification.
-- This script updates one OA account at a time so its menu visibility matches
-- the app-side access model.
--
-- Supported target tiers:
--   hidden
--   read_export_only
--   full_access
--   admin (only YNSYLP005; all other usernames are rejected without mutation)
--
-- Recommended OA role keys:
--   finops_read_export
--   finops_full_access
--   finops_admin

SET @target_username = 'YNSYLP005';
SET @target_tier = 'admin';

SET @readonly_role_key = 'finops_read_export';
SET @full_access_role_key = 'finops_full_access';
SET @admin_role_key = 'finops_admin';
SET @target_user_count = (
  SELECT COUNT(*) FROM sys_user WHERE user_name = @target_username
);
SET @readonly_role_count = (
  SELECT COUNT(*) FROM sys_role WHERE role_key = @readonly_role_key
);
SET @full_access_role_count = (
  SELECT COUNT(*) FROM sys_role WHERE role_key = @full_access_role_key
);
SET @admin_role_count = (
  SELECT COUNT(*) FROM sys_role WHERE role_key = @admin_role_key
);
SET @target_user_id = IF(
  @target_user_count = 1,
  (SELECT MIN(user_id) FROM sys_user WHERE user_name = @target_username),
  NULL
);
SET @readonly_role_id = IF(
  @readonly_role_count = 1,
  (SELECT MIN(role_id) FROM sys_role WHERE role_key = @readonly_role_key),
  NULL
);
SET @full_access_role_id = IF(
  @full_access_role_count = 1,
  (SELECT MIN(role_id) FROM sys_role WHERE role_key = @full_access_role_key),
  NULL
);
SET @admin_role_id = IF(
  @admin_role_count = 1,
  (SELECT MIN(role_id) FROM sys_role WHERE role_key = @admin_role_key),
  NULL
);
SET @target_request_valid = (
  @target_tier IN ('hidden', 'read_export_only', 'full_access', 'admin')
  AND (@target_tier <> 'admin' OR @target_username = 'YNSYLP005')
  AND @target_user_count = 1
  AND @readonly_role_count = 1
  AND @full_access_role_count = 1
  AND @admin_role_count = 1
);

DELETE FROM sys_user_role
WHERE user_id = @target_user_id
  AND @target_request_valid
  AND role_id IN (@readonly_role_id, @full_access_role_id, @admin_role_id);

INSERT INTO sys_user_role (user_id, role_id)
SELECT @target_user_id, @readonly_role_id
WHERE @target_user_id IS NOT NULL
  AND @target_request_valid
  AND @readonly_role_id IS NOT NULL
  AND @target_tier = 'read_export_only';

INSERT INTO sys_user_role (user_id, role_id)
SELECT @target_user_id, @full_access_role_id
WHERE @target_user_id IS NOT NULL
  AND @target_request_valid
  AND @full_access_role_id IS NOT NULL
  AND @target_tier = 'full_access';

INSERT INTO sys_user_role (user_id, role_id)
SELECT @target_user_id, @admin_role_id
WHERE @target_user_id IS NOT NULL
  AND @target_request_valid
  AND @admin_role_id IS NOT NULL
  AND @target_tier = 'admin';

SELECT
  u.user_id,
  u.user_name,
  r.role_id,
  r.role_name,
  r.role_key
FROM sys_user_role ur
JOIN sys_user u ON u.user_id = ur.user_id
JOIN sys_role r ON r.role_id = ur.role_id
WHERE u.user_name = @target_username
  AND r.role_key IN (@readonly_role_key, @full_access_role_key, @admin_role_key)
ORDER BY r.role_key;

SELECT @target_request_valid AS request_valid;
