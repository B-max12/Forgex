import json
import pytest
from forgex.agents.base import _repair_json_string, extract_json


def test_repair_clean_json():
    raw = '{"key": "value", "list": [1, 2, 3]}'
    assert _repair_json_string(raw) == raw
    data = extract_json(raw)
    assert data == {"key": "value", "list": [1, 2, 3]}


def test_repair_unescaped_newlines_in_string():
    raw = '{"text": "line1\nline2\nline3"}'
    repaired = _repair_json_string(raw)
    data = json.loads(repaired)
    assert data["text"] == "line1\nline2\nline3"


def test_repair_trailing_commas():
    raw = '{"a": 1, "b": [1, 2,], "c": {"d": 4,},}'
    repaired = _repair_json_string(raw)
    data = json.loads(repaired)
    assert data == {"a": 1, "b": [1, 2], "c": {"d": 4}}


def test_repair_escaped_quotes_and_backslashes():
    raw = r'{"escaped": "here is \"a quote\" and \\ a slash"}'
    repaired = _repair_json_string(raw)
    data = json.loads(repaired)
    assert 'here is "a quote" and \\ a slash' == data["escaped"]


def test_repair_truncated_json():
    raw = '{"status": "pass", "summary": "all good", "items": [{"id": 1'
    repaired = _repair_json_string(raw)
    data = json.loads(repaired)
    assert data["status"] == "pass"
    assert data["items"][0]["id"] == 1


def test_repair_truncated_string():
    raw = '{"status": "pass", "summary": "incomplete message'
    repaired = _repair_json_string(raw)
    data = json.loads(repaired)
    assert data["status"] == "pass"
    assert "incomplete message" in data["summary"]


def test_extract_json_markdown_fence():
    text = """Here is the result of my analysis:
```json
{
  "action": "done",
  "result": {
    "verdict": "pass"
  }
}
```
Hope that helps!"""
    data = extract_json(text)
    assert data["action"] == "done"
    assert data["result"]["verdict"] == "pass"


def test_extract_json_embedded_prose():
    text = 'Thinking... {"name": "test_tool", "arguments": {"cmd": "ls"}} concluding.'
    data = extract_json(text)
    assert data["name"] == "test_tool"
    assert data["arguments"]["cmd"] == "ls"


def test_extract_json_empty_or_invalid():
    with pytest.raises(ValueError, match="no JSON object found in empty model output"):
        extract_json("")

    with pytest.raises(ValueError, match="no JSON object found in empty model output"):
        extract_json("    ")

    with pytest.raises(ValueError):
        extract_json("Just plain text with no json at all")
