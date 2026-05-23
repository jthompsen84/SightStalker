"""
Optional real-browser smoke test for CAMOUFOX-ENGINE-1.

This test launches a real Camoufox browser. It is skipped unless:
- the `browser_smoke` marker is selected, and
- SIGHTSTALKER_BROWSER_SMOKE=1 is set in the environment, and
- the camoufox package plus a fetched browser binary are available.

It uses only a data: URL — no external network target.
"""

from __future__ import annotations

import os

import pytest

from sightstalker.engines import CamoufoxEngine
from sightstalker.models import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
)

pytestmark = pytest.mark.browser_smoke

_SMOKE_ENABLED = os.environ.get("SIGHTSTALKER_BROWSER_SMOKE") == "1"

_DATA_URL = "data:text/html,<title>SightStalker Smoke</title><h1>ok</h1>"


@pytest.mark.skipif(
    not _SMOKE_ENABLED,
    reason="Set SIGHTSTALKER_BROWSER_SMOKE=1 and fetch the Camoufox binary to run.",
)
@pytest.mark.asyncio
async def test_camoufox_real_browser_smoke(tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)

    engine = CamoufoxEngine()
    runtime = await engine.launch(BrowserLaunchConfig(mode="headless"))
    try:
        context = await runtime.new_context(BrowserContextConfig())
        try:
            page = await context.new_page()
            await page.goto(_DATA_URL)

            title = await page.title()
            assert title == "SightStalker Smoke"

            url = await page.url()
            assert url.startswith("data:text/html")

            state = await context.storage_state()
            assert isinstance(state, BrowserState)

            screenshot_path = tmp_path / "smoke.png"
            await page.screenshot(path=str(screenshot_path))
            assert screenshot_path.exists()
            assert screenshot_path.stat().st_size > 0

            await page.close()
        finally:
            await context.close()
    finally:
        await runtime.close()
        await engine.close()
