from forgex.utils.redact import redact


def test_redacts_secret():
    assert redact("key=gsk_abc123 done", ["gsk_abc123"]) == "key=***REDACTED*** done"


def test_ignores_none_and_short_values():
    assert redact("abc ab abc", [None, "", "ab"]) == "abc ab abc"
