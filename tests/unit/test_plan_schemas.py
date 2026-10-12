import pytest
from pydantic import ValidationError

from forgex.schemas.plan import (
    AnalysisResult, ArchitecturePlan, TaskSpec, specs_to_tasks,
)
from forgex.schemas.task import TaskPriority, TaskStatus


def _plan(**overrides):
    base = {
        "goal": "Todo API",
        "requirements": ["CRUD"],
        "tasks": [
            {"id": "TASK-001", "description": "Scaffold app",
             "acceptance_criteria": ["app starts"]},
            {"id": "TASK-002", "description": "Add tests",
             "depends_on": ["TASK-001"]},
        ],
        "libraries": ["fastapi"],
        "architecture": {"style": "modular"},
    }
    base.update(overrides)
    return ArchitecturePlan.model_validate(base)


def test_valid_plan_roundtrip():
    plan = _plan()
    assert plan.tasks[0].priority is TaskPriority.MEDIUM
    dumped = plan.model_dump(mode="json")
    assert ArchitecturePlan.model_validate(dumped) == plan


def test_plan_requires_goal():
    with pytest.raises(ValidationError):
        ArchitecturePlan.model_validate({"requirements": []})


def test_plan_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _plan(taks=[])


def test_specs_to_tasks_creates_pending_tasks():
    tasks = specs_to_tasks(_plan().tasks)
    assert all(t.status is TaskStatus.PENDING for t in tasks)
    assert [t.id for t in tasks] == ["TASK-001", "TASK-002"]
    assert tasks[1].depends_on == ["TASK-001"]


def test_model_json_schema_is_buildable():
    schema = ArchitecturePlan.model_json_schema()
    assert "properties" in schema and "tasks" in schema["properties"]
