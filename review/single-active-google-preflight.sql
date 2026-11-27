-- READ ONLY. Both result sets must be reviewed; summary always returns one row.
SELECT current_database() AS database_name,current_user AS database_user,
 current_setting('server_version') AS postgres_version,
 count(*) AS duplicate_active_user_groups,
 coalesce(sum(active_count),0) AS credentials_in_duplicate_groups
FROM (SELECT user_id,count(*) AS active_count FROM google_login_credentials
 WHERE revoked_at IS NULL GROUP BY user_id HAVING count(*)>1) conflicts;
SELECT user_id,count(*) AS active_google_count
FROM google_login_credentials WHERE revoked_at IS NULL
GROUP BY user_id HAVING count(*)>1 ORDER BY user_id;
