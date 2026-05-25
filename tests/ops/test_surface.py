"""Tests for sightstalker.ops.surface.RunSurface (fakes only; no browser)."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from sightstalker.artifacts import ArtifactManager, ArtifactPaths
from sightstalker.diagnostics import DiagnosticArtifactRecorder, DiagnosticTarget
from sightstalker.ops import RunSurface
from sightstalker.resilience.errors import SecurityRefusal


class _FakePage:
    def __init__(self) -> None:
        self.goto_calls = 0
        self.goto_urls: list[str] = []

    async def goto(self, url: str, **_kw: Any) -> None:
        self.goto_calls += 1
        self.goto_urls.append(url)


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()

    async def new_page(self) -> _FakePage:
        return self.page


class _FakeManaged:
    def __init__(self) -> None:
        self._context = _FakeContext()

    @property
    def context(self) -> _FakeContext:
        return self._context


def _surface(tmp_path: Any, url: str = "https://example.com/") -> RunSurface:
    recorder = DiagnosticArtifactRecorder(ArtifactManager(ArtifactPaths(tmp_path)))
    return RunSurface(
        managed=cast(Any, _FakeManaged()),
        raw_navigation_url=url,
        recorder=recorder,
        base_target=DiagnosticTarget(),
    )


def test_context_returns_managed_context(tmp_path: Any) -> None:
    surface = _surface(tmp_path)
    assert surface.context is surface.managed.context


def test_new_page_delegates_to_context(tmp_path: Any) -> None:
    surface = _surface(tmp_path)
    page = asyncio.run(surface.new_page())
    assert page is surface.managed.context.page  # type: ignore[attr-defined]


def test_navigate_calls_goto_once_with_raw_url(tmp_path: Any) -> None:
    surface = _surface(tmp_path, "https://example.com/raw")
    page = cast(_FakePage, asyncio.run(surface.new_page()))
    asyncio.run(surface.navigate(cast(Any, page)))
    assert page.goto_calls == 1
    assert page.goto_urls == ["https://example.com/raw"]


def test_navigate_rejects_second_navigation(tmp_path: Any) -> None:
    surface = _surface(tmp_path)
    page = asyncio.run(surface.new_page())
    asyncio.run(surface.navigate(cast(Any, page)))
    with pytest.raises(SecurityRefusal):
        asyncio.run(surface.navigate(cast(Any, page)))


def test_target_with_order_updates_run_order(tmp_path: Any) -> None:
    surface = _surface(tmp_path)
    target = surface.target_with_order(10)
    assert target.run_order == 10
    # Base target is unchanged (model_copy, not mutation).
    assert surface.base_target.run_order is None
