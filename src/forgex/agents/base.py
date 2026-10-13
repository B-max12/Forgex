"""Agent base classes (spec sections 7, 9, 42, 47, 48, 75).

Agents are persistence-free services: they receive a request, tools, and
a router, and return structured results.

The tool loop: bounded multi-turn loop supporting native tool calls
or JSON protocol fallback. Enforces transcript budgets and secret redaction.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError

from forgex.models.base import Message
from forgex.orchestration.events import EventRecorder
from forgex.prompts import load_prompt
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import AgentOutputError, PermissionDeniedError
from forgex.schemas.event import EventType
from forgex.tools import ToolExecutor, ToolResult
from forgex.tools.base import ToolCall as SystemToolCall
from forgex.tools.filesystem import is_secret_file
from forgex.utils.paths import PathViolationError, resolve_in_workspace
from forgex.utils.redact import redact_patterns

if TYPE_CHECKING:
    from forgex.models.router import ModelRouter

logger = logging.getLogger("forgex.agents")

ModelT = TypeVar("ModelT", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)

MAX_TOOL_RESULT_CHARS = 8_000
MAX_PROTOCOL_ERRORS = 3
MAX_TRANSCRIPT_CHARS = 150_000
_SOFT_BUDGET_RATIO = 0.75

PROTOCOL_MODE_DOC = """
Tool protocol — this model does not support native tool calls.
To call a tool, respond with ONLY:
{{"action": "tool", "tool": "<tool name>", "arguments": {{<arguments>}}}}
The tool result is returned to you as JSON in the next message.
To finish, respond with ONLY:
{{"action": "done", "result": {{<final report matching the schema>}}}}

Available tools (JSON Schemas):
{tool_schemas}
"""


def extract_json(text: str) -> Any:
    """Extract JSON from model output: raw, fenced, or embedded in prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    match = _FENCE_RE.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except ValueError:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                continue
    raise ValueError("no JSON object found in model output")


def prefetch_files(
    workspace: Path,
    files: Iterable[str],
    *,
    budget: int,
    max_files: int | None = None,
) -> str:
    """Prefetch existing files' contents into an instruction block."""
    sections: list[str] = []
    remaining = budget
    for rel in files:
        if remaining <= 0:
            break
        if max_files is not None and len(sections) >= max_files:
            break
        if is_secret_file(Path(rel).name):
            continue
        try:
            path = resolve_in_workspace(workspace, rel)
        except PathViolationError:
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        content = redact_patterns(content)
        if len(content) > remaining:
            content = content[:remaining] + "\n... [trimmed]"
        sections.append(f"--- {rel} ---\n{content}")
        remaining -= len(content)
    return "\n\n".join(sections)


def _transcript_chars(messages: list[Message]) -> int:
    total = 0
    for m in messages:
        total += len(m.content or "")
        if m.tool_calls:
            total += len(json.dumps(m.tool_calls))
    return total


@dataclass
class ToolLoopResult:
    report: Any
    rounds: int
    tool_calls_count: int


class BaseAgent(ABC):
    role: AgentRole
    prompt_name: str

    def __init__(
        self,
        *,
        router: ModelRouter,
        events: EventRecorder | None = None,
        run_id: str | None = None,
        temperature: float = 0.2,
        max_output_attempts: int = 2,
    ) -> None:
        self._router = router
        self._events = events
        self._run_id = run_id
        self.temperature = temperature
        self.max_output_attempts = max_output_attempts

    def _system_prompt(self, target_schema: type[BaseModel] | None = None) -> str:
        prompt_text = load_prompt(self.prompt_name)
        if target_schema is not None:
            schema_json = json.dumps(target_schema.model_json_schema(), indent=2)
            prompt_text += (
                f"\n\nYou must respond with JSON adhering to this schema:\n```json\n{schema_json}\n```\n"
            )
        return prompt_text

    async def _generate_structured(
        self,
        messages: list[Message],
        target_schema: type[ModelT],
        *,
        agent_role: str | None = None,
    ) -> ModelT:
        role_key = agent_role or self.role.value
        caps = self._router.capabilities_for(role_key)
        system = self._system_prompt(target_schema)

        if self._events:
            self._events.record(
                EventType.AGENT_THINKING,
                {"agent": role_key, "stage": "structured_generation"},
                run_id=self._run_id,
            )

        msgs = list(messages)
        rf = {"type": "json_object"} if caps.supports_json else None

        for attempt in range(1, self.max_output_attempts + 1):
            resp = await self._router.generate(
                role_key,
                messages=msgs,
                system=system,
                response_format=rf,
                temperature=self.temperature,
                run_id=self._run_id,
            )
            raw = resp.content or ""
            try:
                data = extract_json(raw)
                return target_schema.model_validate(data)
            except (ValueError, ValidationError) as exc:
                if attempt >= self.max_output_attempts:
                    raise AgentOutputError(
                        f"{self.role.value} failed to produce valid JSON: {exc}\nRaw: {raw[:300]}"
                    ) from exc
                logger.warning(
                    "%s structured output attempt %d failed (%s); retrying",
                    self.role.value,
                    attempt,
                    exc,
                )
                msgs.append(Message(role="assistant", content=raw))
                msgs.append(
                    Message(
                        role="user",
                        content=f"Your previous response did not match the required JSON schema ({exc}). Please reply with ONLY valid JSON.",
                    )
                )

        raise AgentOutputError(f"{self.role.value} exceeded output attempts")

    async def _tool_loop(
        self,
        initial_instruction: str,
        tools: ToolExecutor,
        target_schema: type[ModelT],
        *,
        max_rounds: int = 16,
        agent_role: str | None = None,
    ) -> ToolLoopResult:
        role_key = agent_role or self.role.value
        caps = self._router.capabilities_for(role_key)
        system = self._system_prompt(target_schema)

        messages: list[Message] = [Message(role="user", content=initial_instruction)]
        rounds = 0
        total_tool_calls = 0
        warned = False

        if caps.supports_tools:
            # Native tool-calling mode
            available_schemas = tools.schemas()
            while rounds < max_rounds:
                rounds += 1
                size = _transcript_chars(messages)
                if size > MAX_TRANSCRIPT_CHARS:
                    raise AgentOutputError(f"{self.role.value} exceeded context budget ({MAX_TRANSCRIPT_CHARS} chars)")
                if not warned and size > MAX_TRANSCRIPT_CHARS * _SOFT_BUDGET_RATIO:
                    warned = True
                    messages.append(
                        Message(role="user", content="CONTEXT LIMIT APPROACHING: finish current step and produce your final JSON report now.")
                    )

                if self._events:
                    self._events.record(
                        EventType.AGENT_THINKING,
                        {"agent": role_key, "round": rounds},
                        run_id=self._run_id,
                    )

                resp = await self._router.generate(
                    role_key,
                    messages=messages,
                    system=system,
                    tools=available_schemas,
                    temperature=self.temperature,
                    run_id=self._run_id,
                )

                if resp.tool_calls:
                    # Convert to wire format for message history
                    tc_dicts = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in resp.tool_calls
                    ]
                    messages.append(Message(role="assistant", content=resp.content, tool_calls=tc_dicts))

                    for tc in resp.tool_calls:
                        total_tool_calls += 1
                        try:
                            args = json.loads(tc.arguments) if tc.arguments else {}
                        except ValueError:
                            args = {}
                        t_call = SystemToolCall(id=tc.id, name=tc.name, arguments=args)
                        try:
                            t_res = await tools.execute(t_call)
                        except PermissionDeniedError as exc:
                            t_res = ToolResult(ok=False, denied=True, error=str(exc))
                        out_text = t_res.output or (f"Error: {t_res.error}" if t_res.error else "done")
                        if len(out_text) > MAX_TOOL_RESULT_CHARS:
                            out_text = out_text[:MAX_TOOL_RESULT_CHARS] + "\n... [truncated]"
                        messages.append(
                            Message(role="tool", tool_call_id=tc.id, name=tc.name, content=out_text)
                        )
                else:
                    # Final report produced
                    raw = resp.content or ""
                    try:
                        data = extract_json(raw)
                        report = target_schema.model_validate(data)
                        return ToolLoopResult(report=report, rounds=rounds, tool_calls_count=total_tool_calls)
                    except (ValueError, ValidationError) as exc:
                        # Bounded repair
                        messages.append(Message(role="assistant", content=raw))
                        messages.append(
                            Message(
                                role="user",
                                content=f"Your final response did not match the JSON schema ({exc}). Please return ONLY the final JSON object.",
                            )
                        )
                        repair_resp = await self._router.generate(
                            role_key,
                            messages=messages,
                            system=system,
                            temperature=self.temperature,
                            run_id=self._run_id,
                        )
                        data = extract_json(repair_resp.content or "")
                        report = target_schema.model_validate(data)
                        return ToolLoopResult(report=report, rounds=rounds, tool_calls_count=total_tool_calls)

            # Loop limit reached; ask for final report
            final = await self._generate_structured(messages, target_schema, agent_role=role_key)
            return ToolLoopResult(report=final, rounds=rounds, tool_calls_count=total_tool_calls)

        else:
            # JSON Protocol mode for models without tool support
            protocol_doc = PROTOCOL_MODE_DOC.format(
                tool_schemas=json.dumps(tools.schemas(), indent=2)
            )
            protocol_system = system + "\n\n" + protocol_doc
            protocol_errors = 0

            while rounds < max_rounds:
                rounds += 1
                size = _transcript_chars(messages)
                if size > MAX_TRANSCRIPT_CHARS:
                    raise AgentOutputError(f"{self.role.value} exceeded context budget")

                resp = await self._router.generate(
                    role_key,
                    messages=messages,
                    system=protocol_system,
                    temperature=self.temperature,
                    run_id=self._run_id,
                )
                raw = resp.content or ""

                try:
                    action_data = extract_json(raw)
                except ValueError:
                    protocol_errors += 1
                    if protocol_errors >= MAX_PROTOCOL_ERRORS:
                        raise AgentOutputError(f"{self.role.value} protocol errors exceeded: {raw[:200]}")
                    messages.append(Message(role="assistant", content=raw))
                    messages.append(Message(role="user", content="Please reply with a valid JSON action: {\"action\": \"tool\", ...} or {\"action\": \"done\", ...}."))
                    continue

                if not isinstance(action_data, dict):
                    protocol_errors += 1
                    if protocol_errors >= MAX_PROTOCOL_ERRORS:
                        raise AgentOutputError(f"{self.role.value} protocol errors exceeded: expected JSON object")
                    messages.append(Message(role="assistant", content=raw))
                    messages.append(Message(role="user", content="Please reply with a valid JSON object: {\"action\": \"tool\", ...} or {\"action\": \"done\", ...}."))
                    continue

                # Normalize keys (strip quotes, whitespace, lowercase)
                normalized: dict[str, Any] = {}
                for k, v in action_data.items():
                    normalized[str(k).strip().strip('"\'').lower()] = v

                action = str(normalized.get("action") or "").strip().lower()
                if action == "tool":
                    raw_tool = normalized.get("tool") or normalized.get("name")
                    if not raw_tool or not isinstance(raw_tool, str):
                        protocol_errors += 1
                        messages.append(Message(role="assistant", content=raw))
                        messages.append(Message(role="user", content="Tool name missing or invalid. Use {\"action\": \"tool\", \"tool\": \"<name>\", \"arguments\": {...}}."))
                        continue
                    tool_name: str = raw_tool.strip()
                    args = normalized.get("arguments") or normalized.get("args") or {}
                    if not isinstance(args, dict):
                        args = {}
                    total_tool_calls += 1
                    t_res = await tools.execute(SystemToolCall(name=tool_name, arguments=args))
                    out_text = t_res.output or (f"Error: {t_res.error}" if t_res.error else "done")
                    if len(out_text) > MAX_TOOL_RESULT_CHARS:
                        out_text = out_text[:MAX_TOOL_RESULT_CHARS] + "\n... [truncated]"
                    messages.append(Message(role="assistant", content=raw))
                    messages.append(Message(role="user", content=json.dumps({"tool_result": out_text})))
                elif action == "done":
                    res_data = normalized.get("result") or normalized.get("report")
                    if res_data is None or not isinstance(res_data, dict):
                        res_data = {k: v for k, v in normalized.items() if k not in ("action", "tool", "arguments", "args")}
                    try:
                        report = target_schema.model_validate(res_data)
                        return ToolLoopResult(report=report, rounds=rounds, tool_calls_count=total_tool_calls)
                    except (ValidationError, ValueError) as val_exc:
                        protocol_errors += 1
                        if protocol_errors >= MAX_PROTOCOL_ERRORS:
                            raise AgentOutputError(f"{self.role.value} schema validation failed: {val_exc}") from val_exc
                        messages.append(Message(role="assistant", content=raw))
                        messages.append(
                            Message(
                                role="user",
                                content=f"Your 'done' result did not match the JSON schema ({val_exc}). Please return valid JSON: {{\"action\": \"done\", \"result\": {{...}}}}.",
                            )
                        )
                else:
                    protocol_errors += 1
                    messages.append(Message(role="assistant", content=raw))
                    messages.append(Message(role="user", content="Unknown action. Use 'tool' or 'done'."))

            final = await self._generate_structured(messages, target_schema, agent_role=role_key)
            return ToolLoopResult(report=final, rounds=rounds, tool_calls_count=total_tool_calls)

    async def aclose(self) -> None:
        await self._router.aclose()
