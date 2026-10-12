from forgex.schemas.agent import AgentRole
from forgex.sandbox.permissions import Permission, PermissionSet, permission_set_for


def test_architect_cannot_write():
    assert not permission_set_for(AgentRole.ARCHITECT).permits(Permission.WRITE)


def test_builder_can_write_and_run():
    perms = permission_set_for(AgentRole.BUILDER)
    assert perms.permits(Permission.WRITE, Permission.TERMINAL, Permission.DELETE, Permission.GIT)


def test_supervisor_reads_and_tests_but_never_writes():
    perms = permission_set_for(AgentRole.SUPERVISOR)
    assert perms.permits(Permission.READ, Permission.TEST, Permission.GIT)
    assert not perms.permits(Permission.WRITE)


def test_deny_reason_lists_missing():
    reason = PermissionSet(allow={Permission.READ}).deny_reason(Permission.READ, Permission.WRITE)
    assert reason is not None and "write" in reason


def test_unknown_role_fails_closed():
    class FakeRole:
        value = "ghost"

    assert not permission_set_for(FakeRole()).permits(Permission.READ)  # type: ignore[arg-type]
