-- Formal workbench relations are the only persisted matching state.
-- Candidate and reconciliation-decision rows were rebuildable intermediate
-- states that could hide canonical facts from the paired/unpaired partition.

drop table if exists read_model.workbench_reconciliation_decisions;
drop table if exists read_model.workbench_candidate_matches;

delete from app.app_settings
where settings_key = 'state:workbench_candidate_matches';
