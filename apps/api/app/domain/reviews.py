"""Reviews and revision briefs bind to exact immutable submissions."""
from dataclasses import dataclass
from app.agents.contracts import ReviewResult, ReviewVerdict
from app.domain.submissions import SubmissionManifest


@dataclass(frozen=True, slots=True)
class ReviewRound:
    task_id: str
    number: int
    submission_id: str
    submission_version: int
    result: ReviewResult

    @classmethod
    def validate(cls, result, submission: SubmissionManifest, criteria, number):
        if result.submission_id != submission.id:
            raise ValueError('stale submission in review')
        expected = {f'c{i}' for i in range(1, len(criteria) + 1)}
        if len(result.assessments) != len(expected) or {a.criterion_id for a in result.assessments} != expected:
            raise ValueError('review must assess every current criterion exactly once')
        if any(not a.evidence.strip() for a in result.assessments):
            raise ValueError('review evidence is required')
        if result.verdict is ReviewVerdict.PASS and (
            not all(a.passed for a in result.assessments) or
            any(f.severity.value in {'major', 'blocker'} for f in result.findings)
        ):
            raise ValueError('PASS cannot bypass failed criteria or blocking findings')
        return cls(submission.task_id, number, submission.id, submission.version, result)


@dataclass(frozen=True, slots=True)
class RevisionBrief:
    task_id: str
    submission_id: str
    review_id: str
    required_fixes: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    remaining_review_rounds: int
