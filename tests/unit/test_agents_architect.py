



class FakeRouter:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls = []

    async def generate(self, agent, *, messages, system=None,
                       response_format=None, temperature=None, **kwargs):
        self.calls.append({"messages": messages, "system": system or ""})
        await agent.plan("Build a todo API")
