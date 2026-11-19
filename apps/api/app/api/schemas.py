"""HTTP contracts; OpenAPI is the client type-generation boundary."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RequirementInput(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    priority: str = "normal"


class CreateProject(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=16000)
    requirements: list[RequirementInput] = Field(min_length=1, max_length=100)


class Command(StrictModel):
    expected_version: int = Field(ge=1)
    approval_id: str | None = None
    approved: bool | None = None
    operation_id: str | None = None
    action: str | None = None
    reason: str = Field(default='', max_length=4000)
    expected_epoch: int | None = Field(default=None, ge=0)
    quiescent: bool = False


class CommandAcknowledgement(StrictModel):
    command_id: str
    status: Literal['pending', 'applied', 'rejected']
    project_id: str
    run_id: str | None = None
    project_version: int | None = None
    event_cursor: int | None = None
    error: str | None = None


class ProjectSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    project: dict
    event_cursor: int


class AgentSettings(StrictModel):
    expected_version: int = Field(ge=1)
    kind: Literal['manager', 'developer', 'reviewer']
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    system_instructions: str = Field(min_length=1, max_length=16000)
