-- Coach-controlled success plan switch. NOT NULL with default false: nobody is switched on by accident.
-- One time rule: trainees already at meeting 7 to 10, or in ongoing support, are switched on when the column is first added.
-- Safe to run again: if the column already exists nothing runs, so a switch the coach turned off later is never turned on again.
-- Apply in Cloud SQL aicoach_db BEFORE deploying the code that reads and writes it.
-- Rollback: ALTER TABLE coaching_programs DROP COLUMN success_plan_active;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'coaching_programs' AND column_name = 'success_plan_active') THEN
    ALTER TABLE coaching_programs ADD COLUMN success_plan_active boolean NOT NULL DEFAULT false;
    UPDATE coaching_programs SET success_plan_active = true
      WHERE phase IN ('meeting_7', 'meeting_8', 'meeting_9', 'meeting_10', 'ongoing');
  END IF;
END $$;
