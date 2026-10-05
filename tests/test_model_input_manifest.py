"""Unit coverage for replayable model-input manifests."""

from __future__ import annotations

import pytest

from mechaharness.model_input_manifest import (
    ModelInputManifest,
    attach_manifest_ref,
    content_digest,
    reconstruct_messages,
)


def test_manifest_hashes_and_reconstruct() -> None:
    messages = [{"role": "user", "content": "hi"}]
    manifest = ModelInputManifest.from_parts(
        messages=messages,
        tool_definitions=[{"name": "t"}],
        instructions=["be careful"],
        context_refs=["ctx:1"],
    )
    assert manifest.verify_hashes()
    assert manifest.content_hashes["messages"] == content_digest(messages)
    assert reconstruct_messages(manifest) == messages


def test_tampered_manifest_fails_reconstruct() -> None:
    manifest = ModelInputManifest.from_parts(messages=[{"role": "user", "content": "a"}])
    manifest.messages[0]["content"] = "tampered"
    assert not manifest.verify_hashes()
    with pytest.raises(ValueError, match="hashes"):
        reconstruct_messages(manifest)


def test_attach_manifest_ref() -> None:
    manifest = ModelInputManifest.from_parts(messages=[])
    fields = attach_manifest_ref({"verdict": "allow"}, manifest)
    assert fields["context_manifest_ref"] == manifest.manifest_id
