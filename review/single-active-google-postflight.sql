-- READ ONLY after separately approved schema APPLY. Summary always one row.
SELECT current_database() AS database_name,current_user AS database_user,
 current_setting('server_version') AS postgres_version,
 (SELECT count(*) FROM (SELECT user_id FROM google_login_credentials WHERE revoked_at IS NULL
 GROUP BY user_id HAVING count(*)>1) d) AS duplicate_active_user_groups,
 count(*) AS all_credentials,count(*) FILTER(WHERE revoked_at IS NULL) AS active_credentials
FROM google_login_credentials;
SELECT 'google_login_one_active_user' AS expected_index,
 to_regclass('google_login_one_active_user') IS NOT NULL AS index_present,
 coalesce(i.indisunique,false) AS is_unique,coalesce(i.indisvalid,false) AS is_valid,
 coalesce(i.indisready,false) AS is_ready,pg_get_indexdef(i.indexrelid) AS index_definition
FROM (SELECT 1) one LEFT JOIN pg_index i ON i.indexrelid=to_regclass('google_login_one_active_user');
