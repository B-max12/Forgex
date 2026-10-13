
from forgex.agents.supervisor import apply_quality_gates
from forgex.schemas.agent import SupervisorJudgment
from forgex.schemas.result import TestResults, VerificationOutcome


def _tests(exit_code=0, passed=1, failed=0, timed_out=False) -> TestResults:
    return TestResults(command=["python", "-m", "pytest", "-q"], exit_code=exit_code,
                       passed=passed, failed=failed, timed_out=timed_out)


def _judgment(status="pass") -> SupervisorJudgment:
    return SupervisorJudgment(status=status, summary="looks fine to me")


def test_gates_force_fail_over_lying_llm():
    outcome = VerificationOutcome(tests=_tests(exit_code=1, passed=0, failed=2))
    report = apply_quality_gates(_judgment("pass"), outcome)
    assert report.status == "fail"
    assert any("tests failed" in e for e in report.errors)


def test_gates_soft_no_tests_collected():
    outcome = VerificationOutcome(tests=_tests(exit_code=5, passed=0, failed=0))
    report = apply_quality_gates(_judgment("pass"), outcome)
    assert report.status == "needs_review"


def test_gates_denied_test_command_is_soft():
    outcome = VerificationOutcome(tests=_tests(exit_code=None))
    report = apply_quality_gates(_judgment("pass"), outcome)
    assert report.status == "needs_review"

    assert any("tests failed" in e for e in report.errors)
