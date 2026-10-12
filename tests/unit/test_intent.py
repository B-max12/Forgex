from forgex.cli.intent import IntentAction, classify_intent


def test_intent_plan_detection():
    res = classify_intent("plan a REST API for book store")
    assert res.action == IntentAction.PLAN
    assert res.command_args == ["plan", "a REST API for book store"]

    res2 = classify_intent("create a user authentication endpoint")
    assert res2.action == IntentAction.PLAN
    assert "user authentication endpoint" in res2.command_args[1]


def test_intent_build_detection():
    res = classify_intent("build")
    assert res.action == IntentAction.BUILD
    assert res.command_args == ["build"]

    res2 = classify_intent("run build")
    assert res2.action == IntentAction.BUILD


def test_intent_fix_detection():
    res = classify_intent("fix the failing tests")
    assert res.action == IntentAction.FIX
    assert res.command_args == ["fix"]

    res2 = classify_intent("autofix")
    assert res2.action == IntentAction.FIX


def test_intent_review_and_verify():
    res = classify_intent("review recent changes")
    assert res.action == IntentAction.REVIEW
    assert res.command_args == ["review"]

    res2 = classify_intent("run tests")
    assert res2.action == IntentAction.VERIFY
    assert res2.command_args == ["verify"]


def test_intent_status_and_doctor():
    res = classify_intent("show status")
    assert res.action == IntentAction.STATUS
    assert res.command_args == ["status"]

    res2 = classify_intent("check environment")
    assert res2.action == IntentAction.DOCTOR
    assert res2.command_args == ["doctor"]


def test_intent_fallback_task():
    res = classify_intent("implement websocket notification channel")
    assert res.action == IntentAction.PLAN
    assert "websocket notification channel" in res.command_args[1]


def test_intent_plan_and_build_pipeline():
    res = classify_intent("build me a REST API")
    assert res.action == IntentAction.PLAN_AND_BUILD
    assert res.pipeline == [["plan", "a REST API"], ["build"]]

    res2 = classify_intent("plan and build payment webhook")
    assert res2.action == IntentAction.PLAN_AND_BUILD
    assert res2.pipeline == [["plan", "payment webhook"], ["build"]]
