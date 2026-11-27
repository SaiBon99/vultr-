"""Unit tests for extracting code from model replies. No network."""

from backend.app.planner import extract_code


def test_extracts_fenced_python_block():
    reply = "Here you go:\n```python\nprint('hi')\n```\nDone."
    assert extract_code(reply) == "print('hi')\n"


def test_extracts_unlabelled_fence():
    reply = "```\nx = 1\n```"
    assert extract_code(reply) == "x = 1\n"


def test_falls_back_to_whole_reply_without_fence():
    assert extract_code("print(2)") == "print(2)\n"
