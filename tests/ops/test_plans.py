"""Tests for sightstalker.ops.plans (PlanResult container + Plan alias)."""

from __future__ import annotations

import json

from sightstalker.ops import PlanResult


def test_default_title_none() -> None:
    assert PlanResult().title is None


def test_default_final_url_none() -> None:
    assert PlanResult().final_url is None


def test_default_diagnostics_is_fresh_list() -> None:
    result = PlanResult()
    assert result.diagnostics == []


def test_default_extra_is_fresh_dict() -> None:
    result = PlanResult()
    assert result.extra == {}


def test_instances_do_not_share_diagnostics() -> None:
    a = PlanResult()
    b = PlanResult()
    a.diagnostics.append(("x", 1))  # type: ignore[arg-type]
    assert b.diagnostics == []


def test_instances_do_not_share_extra() -> None:
    a = PlanResult()
    b = PlanResult()
    a.extra["k"] = "v"
    assert b.extra == {}


def test_extra_is_json_safe_when_populated() -> None:
    result = PlanResult(extra={"a": 1, "b": ["x", None, True], "c": {"d": 2.5}})
    # Round-trips through JSON without error.
    assert json.loads(json.dumps(result.extra)) == result.extra
