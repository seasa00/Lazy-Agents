"""JSON Schemas sent to the initial provider's Structured Outputs endpoint."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties),
        "additionalProperties": False,
    }


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


_STRING = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}

_REQUIREMENT = _object({"id": _STRING, "description": _STRING, "acceptance_criteria": _array(_STRING), "priority": _STRING})
_TASK = _object(
    {
        "id": _STRING,
        "title": _STRING,
        "description": _STRING,
        "acceptance_criteria": _array(_STRING),
        "assignee": {"type": "string", "enum": ["manager", "developer", "reviewer"]},
        "dependencies": _array(_STRING),
    }
)
_DECISION = _object({"id": _STRING, "summary": _STRING, "rationale": _STRING})
_FILE_CHANGE = _object({"path": _STRING, "change_type": _STRING, "summary": _STRING})
_TEST_RESULT = _object({"name": _STRING, "status": _STRING, "summary": _STRING})
_ASSESSMENT = _object({"criterion_id": _STRING, "passed": _BOOL, "evidence": _STRING, "notes": _STRING})
_FINDING = _object(
    {
        "id": _STRING,
        "severity": {"type": "string", "enum": ["blocker", "major", "minor", "note"]},
        "summary": _STRING,
        "evidence": _STRING,
        "criterion_id": {"type": ["string", "null"]},
    }
)

_SCHEMAS: dict[str, dict[str, Any]] = {
    'manager_decision.v1': _object({
        'action': {'type': 'string', 'enum': ['assign_task', 'request_revision', 'accept_submission', 'block', 'complete', 'request_user_input']},
        'task_id': {'type': ['string', 'null']}, 'reason': _STRING,
        'revision_instructions': _array(_STRING),
    }),
    'final_result.v1': _object({
        'status': {'type': 'string', 'enum': ['completed']}, 'summary': _STRING,
        'completed_task_ids': {**_array(_STRING),
            'description': 'Copy every ID from workflow.completed_task_ids exactly. Omit none and add none.'},
        'evidence_refs': {**_array(_STRING),
            'description': 'Copy every ID from workflow.evidence_refs exactly. These are current accepted submission IDs identifying immutable evidence, not task IDs, file paths, digests or evidence text. Omit none and add none.'},
        'limitations': _array(_STRING),
    }),
    "manager_plan.v1": _object(
        {
            "summary": _STRING,
            "requirements": _array(_REQUIREMENT),
            "tasks": _array(_TASK),
            "assumptions": _array(_STRING),
            "decisions": _array(_DECISION),
        }
    ),
    "developer_submission.v1": _object(
        {
            "submission_id": _STRING,
            "task_id": _STRING,
            "output_version": _INT,
            "summary": _STRING,
            "changed_files": _array(_FILE_CHANGE),
            "tests": _array(_TEST_RESULT),
            "ready_for_review": _BOOL,
            "notes": _array(_STRING),
        }
    ),
    "review_result.v1": _object(
        {
            "review_id": _STRING,
            "submission_id": _STRING,
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "summary": _STRING,
            "assessments": _array(_ASSESSMENT),
            "findings": _array(_FINDING),
            "checks_not_performed": _array(_STRING),
        }
    ),
}


def schema_for_output(name: str) -> dict[str, Any]:
    """Return a defensive copy of a supported role schema."""

    try:
        return deepcopy(_SCHEMAS[name])
    except KeyError as exc:
        raise ValueError(f"unsupported structured output schema {name!r}") from exc
