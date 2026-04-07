-- fin-ops role binding bootstrap
-- Use after fin_ops_menu.mysql.sql has created or updated the menu.
-- Bind the menu to all fin-ops-visible OA roles.

SET @finops_menu_perms = 'finops:app:view';
SET @readonly_role_key = 'finops_read_export';
SET @full_access_role_key = 'finops_full_access';
SET @admin_role_key = 'finops_admin';

SET @finops_menu_id = (
  SELECT menu_id
  FROM sys_menu
  WHERE perms = @finops_menu_perms
  ORDER BY menu_id DESC
  LIMIT 1
);

SET @readonly_role_id = (
  SELECT role_id
  FROM sys_role
  WHERE role_key = @readonly_role_key
  ORDER BY role_id DESC
  LIMIT 1
);

SET @full_access_role_id = (
  SELECT role_id
  FROM sys_role
  WHERE role_key = @full_access_role_key
  ORDER BY role_id DESC
  LIMIT 1
);

SET @admin_role_id = (
  SELECT role_id
  FROM sys_role
  WHERE role_key = @admin_role_key
  ORDER BY role_id DESC
  LIMIT 1
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT @readonly_role_id, @finops_menu_id
WHERE @readonly_role_id IS NOT NULL
  AND @finops_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_role_menu
    WHERE role_id = @readonly_role_id
      AND menu_id = @finops_menu_id
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT @full_access_role_id, @finops_menu_id
WHERE @full_access_role_id IS NOT NULL
  AND @finops_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_role_menu
    WHERE role_id = @full_access_role_id
      AND menu_id = @finops_menu_id
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT @admin_role_id, @finops_menu_id
WHERE @admin_role_id IS NOT NULL
  AND @finops_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_role_menu
    WHERE role_id = @admin_role_id
      AND menu_id = @finops_menu_id
  );

SELECT
  r.role_id,
  r.role_name,
  r.role_key,
  m.menu_id,
  m.menu_name,
  m.perms
FROM sys_role_menu rm
JOIN sys_role r ON r.role_id = rm.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.perms = @finops_menu_perms
  AND r.role_key IN (@readonly_role_key, @full_access_role_key, @admin_role_key)
ORDER BY r.role_id;
