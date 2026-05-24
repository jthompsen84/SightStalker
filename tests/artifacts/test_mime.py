"""MIME policy tests (spec 11, 19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sightstalker.artifacts import infer_mime_type, mime_type_for_artifact_type
from sightstalker.artifacts.errors import UnsupportedArtifactTypeError


def test_defaults_per_type() -> None:
    assert mime_type_for_artifact_type("storage_state_initial") == "application/json"
    assert mime_type_for_artifact_type("storage_state_final") == "application/json"
    assert mime_type_for_artifact_type("fingerprint_profile") == "application/json"
    assert mime_type_for_artifact_type("run_log") == "application/x-jsonlines"
    assert mime_type_for_artifact_type("screenshot") == "image/png"
    assert mime_type_for_artifact_type("trace") == "application/zip"
    assert mime_type_for_artifact_type("diagnostic_bundle") == "application/zip"


def test_unknown_type_default_rejected() -> None:
    with pytest.raises(UnsupportedArtifactTypeError):
        mime_type_for_artifact_type("not_a_type")  # type: ignore[arg-type]


def test_extension_refinement_json() -> None:
    assert infer_mime_type("storage_state_initial", Path("a/b.json")) == "application/json"


def test_extension_refinement_jsonl_for_run_log() -> None:
    assert infer_mime_type("run_log", Path("logs/run.jsonl")) == "application/x-jsonlines"


def test_extension_refinement_txt_for_run_log() -> None:
    assert infer_mime_type("run_log", Path("logs/run.txt")) == "text/plain"


def test_unknown_extension_falls_back_to_default() -> None:
    assert infer_mime_type("trace", Path("t/trace.weird")) == "application/zip"


def test_jpeg_screenshot_inferred() -> None:
    assert infer_mime_type("screenshot", Path("s/shot.jpg")) == "image/jpeg"
    assert infer_mime_type("screenshot", Path("s/shot.jpeg")) == "image/jpeg"


def test_png_screenshot_inferred() -> None:
    assert infer_mime_type("screenshot", Path("s/shot.png")) == "image/png"


def test_compatible_explicit_override_accepted() -> None:
    assert (
        infer_mime_type("screenshot", Path("s/shot.bin"), explicit="image/jpeg")
        == "image/jpeg"
    )
    assert (
        infer_mime_type("run_log", Path("l/run.bin"), explicit="text/plain")
        == "text/plain"
    )


def test_incompatible_explicit_override_rejected() -> None:
    with pytest.raises(UnsupportedArtifactTypeError):
        infer_mime_type("screenshot", Path("s/shot.png"), explicit="application/json")
    with pytest.raises(UnsupportedArtifactTypeError):
        infer_mime_type("storage_state_initial", Path("a.json"), explicit="image/png")


def test_syntactically_invalid_explicit_rejected() -> None:
    with pytest.raises(UnsupportedArtifactTypeError):
        infer_mime_type("run_log", Path("l/run.txt"), explicit="not-a-mime")
    with pytest.raises(UnsupportedArtifactTypeError):
        infer_mime_type("run_log", Path("l/run.txt"), explicit="")


def test_extension_incompatible_with_type_falls_back() -> None:
    # A .png suffix on a storage-state artifact is not compatible → default.
    assert (
        infer_mime_type("storage_state_initial", Path("weird/name.png"))
        == "application/json"
    )
