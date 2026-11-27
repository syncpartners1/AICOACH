-- Read only. Expected application DB: aicoach_db; application role: aicoach_user.
SELECT current_database() AS database_name, current_user AS database_user;
SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns
 WHERE table_schema='public' AND table_name='coaching_programs' AND column_name IN ('coaching_track','program_type','phase','success_plan_active');
SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint
 WHERE conrelid IN ('public.coaching_programs'::regclass,to_regclass('public.coaching_track_events'))
 AND conname IN ('coaching_programs_professional_track_check','coaching_track_events_new_track_check','coaching_track_events_previous_track_check','coaching_track_events_user_id_fkey');
SELECT to_regclass('public.coaching_track_events') AS event_table,
 CASE WHEN to_regclass('public.coaching_track_events') IS NULL THEN NULL
 ELSE has_table_privilege('aicoach_user','public.coaching_track_events','SELECT,INSERT') END AS app_can_read_write;
-- No names, phones, emails, IDs, tokens or client session content are returned.
