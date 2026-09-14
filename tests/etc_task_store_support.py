from copy import deepcopy
from dataclasses import asdict, is_dataclass


class NarrowTaskStoreMixin:
    def get_etc_reconciliation_task_record(self, task_id):
        task = self.load_etc_reconciliation_state().get("tasks", {}).get(task_id)
        return asdict(task) if is_dataclass(task) else deepcopy(task)

    def save_etc_reconciliation_task(self, task, *, expected_version, expected_status=None):
        state = deepcopy(self.load_etc_reconciliation_state())
        previous = state.setdefault("tasks", {}).get(task.task_id)
        version = previous.get("version") if isinstance(previous, dict) else getattr(previous, "version", None)
        status = previous.get("status") if isinstance(previous, dict) else getattr(previous, "status", None)
        if version != expected_version or (expected_status is not None and status != expected_status):
            raise ValueError("task_version_conflict")
        state["tasks"][task.task_id] = deepcopy(task)
        for counter, values in (("task_counter", [task.task_id]), ("file_counter", [f.file_id for f in task.source_files]),
                                ("audit_counter", [e.event_id for e in task.audit_events])):
            state[counter] = max([int(state.get(counter, 0)), *[int(v.rsplit("-", 1)[-1]) for v in values if v.rsplit("-", 1)[-1].isdigit()]])
        self.save_etc_reconciliation_state(state)
