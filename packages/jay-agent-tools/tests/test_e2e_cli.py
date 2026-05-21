"""Tests for cli_check."""

import asyncio

import pytest

from jay_agent_tools.e2e.cli_check import cli_check


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_cli_check_pass():
    result = _run(cli_check("echo hello"))
    assert result.status.value == "pass"


def test_cli_check_fail_exit_code():
    result = _run(cli_check("exit 1", expected_exit_code=0))
    assert result.status.value == "fail"
    assert "Exit code" in result.message


def test_cli_check_stdout_contains():
    result = _run(cli_check("echo hello world", stdout_contains="hello"))
    assert result.status.value == "pass"


def test_cli_check_stdout_not_contains():
    result = _run(cli_check("echo hello", stdout_not_contains="goodbye"))
    assert result.status.value == "pass"


def test_cli_check_stdout_contains_fail():
    result = _run(cli_check("echo hello", stdout_contains="xyz"))
    assert result.status.value == "fail"


def test_cli_check_timeout():
    result = _run(cli_check("sleep 10", timeout=0.1))
    assert result.status.value == "fail"
    assert "Timed out" in result.message
