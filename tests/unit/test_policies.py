from forgex.sandbox.policies import CommandPolicy, Decision, resolve_approval


def test_destructive_command_denied():
    assert CommandPolicy().check(["rm", "-rf", "/"]).decision is Decision.DENY


def test_shells_denied():
    for shell in ("bash", "sh", "powershell", "cmd"):
        assert CommandPolicy().check([shell, "-c", "x"]).decision is Decision.DENY, shell


def test_allowlist_mode_denies_unlisted():
    policy = CommandPolicy(allowed=frozenset({"python"}))
    assert policy.check(["python", "-V"]).decision is Decision.ALLOW
    assert policy.check(["git", "status"]).decision is Decision.DENY


def test_network_command_requires_approval():
    policy = CommandPolicy(network_allowed=False)
    assert policy.check(["pip", "install", "x"]).decision is Decision.APPROVAL
    assert policy.check(["python", "-V"]).decision is Decision.ALLOW


def test_network_allowed_config_permits_package_managers():
    policy = CommandPolicy(network_allowed=True)
    assert policy.check(["pip", "install", "x"]).decision is Decision.ALLOW


def test_resolved_path_base_is_checked():
    policy = CommandPolicy()
    assert policy.check(["/usr/bin/rm", "x"]).decision is Decision.DENY


def test_resolve_approval_modes():
    assert resolve_approval("safe", "x", lambda d: True) is False
    assert resolve_approval("auto", "x", None) is True
    assert resolve_approval("ask", "x", lambda d: True) is True
    assert resolve_approval("ask", "x", None) is False  # fail-safe
    assert resolve_approval("ask", "x", lambda d: False) is False
