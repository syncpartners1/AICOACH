-- Structural checks only, no client values returned.
SELECT current_database() AS database_name,current_user AS database_user;
SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='person_name_events' ORDER BY ordinal_position;
SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid='public.person_name_events'::regclass ORDER BY conname;
SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='person_name_events';
SELECT has_table_privilege('aicoach_user','public.person_name_events','SELECT') AS can_select,has_table_privilege('aicoach_user','public.person_name_events','INSERT') AS can_insert;
