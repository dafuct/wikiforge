"""Redaction and Claude Code transcript parsing for dev-event capture."""

from __future__ import annotations

import json
from pathlib import Path

from wikiforge.ops.capture import (
    Turn,
    extract_turn,
    parse_hook_stdin,
    read_transcript,
    redact_secrets,
)


def test_redact_masks_common_secret_shapes() -> None:
    out = redact_secrets("key sk-ABCDEF0123456789ABCD and AKIAIOSFODNN7EXAMPLE end")
    assert "sk-ABCDEF" not in out
    assert "AKIA" not in out
    assert "***" in out


def test_redact_leaves_plain_text() -> None:
    assert redact_secrets("fix the login bug") == "fix the login bug"


def test_parse_hook_stdin_extracts_transcript_path() -> None:
    raw = json.dumps({"transcript_path": "/tmp/t.jsonl", "cwd": "/repo"})
    assert parse_hook_stdin(raw) == "/tmp/t.jsonl"


def test_parse_hook_stdin_bad_input_returns_none() -> None:
    assert parse_hook_stdin("not json") is None
    assert parse_hook_stdin(json.dumps({"no_path": 1})) is None


def test_extract_turn_takes_last_request_and_this_turns_edits() -> None:
    entries = [
        {"type": "user", "message": {"role": "user", "content": "old request"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "old.py"}}]}},
        {"type": "user", "message": {"role": "user", "content": "fix the retriever"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "on it"},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py"}},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "b.py"}}]}},
    ]
    turn = extract_turn(entries)
    assert turn.request == "fix the retriever"
    assert turn.files == ["a.py", "b.py"]  # old.py excluded — it was a prior turn


def test_extract_turn_ignores_tool_result_user_messages() -> None:
    entries = [
        {"type": "user", "message": {"role": "user", "content": "do it"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "ok"}]}},
    ]
    turn = extract_turn(entries)
    assert turn.request == "do it"       # tool_result is not a human turn — no reset
    assert turn.files == ["a.py"]


def test_extract_turn_no_edits() -> None:
    entries = [{"type": "user", "message": {"role": "user", "content": "what does x do?"}}]
    assert extract_turn(entries) == Turn(request="what does x do?", files=[])


def test_read_transcript_tolerates_blank_and_bad_lines(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('{"a": 1}\n\nnot json\n{"b": 2}\n', encoding="utf-8")
    assert read_transcript(p) == [{"a": 1}, {"b": 2}]


def test_read_transcript_tolerates_non_utf8(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"a": 1}\n\xff\xfe not utf-8\n')
    assert read_transcript(p) == [{"a": 1}]
