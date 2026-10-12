from forgex.cli.context_memory import ConversationContext


def test_context_memory_followup_detection():
    ctx = ConversationContext()
    assert not ctx.is_followup("add rate limiting to the endpoints")

    # Record first run
    ctx.record_run(
        request="create auth endpoints",
        status="completed",
        changed_files=["src/auth.py", "tests/test_auth.py"],
        checkpoint_id="abc1234",
    )

    assert ctx.is_followup("now add rate limiting to those endpoints")
    assert ctx.is_followup("fix it please")
    assert ctx.is_followup("make it pass")
    assert ctx.is_followup("also add redis cache")
    assert not ctx.is_followup("create a new discord bot")


def test_context_memory_request_enrichment():
    ctx = ConversationContext()
    ctx.record_run(
        request="implement JWT service",
        status="completed",
        changed_files=["src/jwt.py"],
    )

    enriched = ctx.enrich_request("now add refresh token rotation to it")
    assert "Previous task: implement JWT service" in enriched
    assert "Modified files: src/jwt.py" in enriched
    assert "now add refresh token rotation to it" in enriched

    # Non-followup should remain unaltered
    clean = ctx.enrich_request("list all users")
    assert clean == "list all users"
