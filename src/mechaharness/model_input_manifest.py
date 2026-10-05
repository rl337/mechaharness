"""Replayable manifests for model-visible inference inputs.

WalkingLabs' DeepSeek harness breakdown states that anything entering a model
request must be reconstructible from append-only session state
(https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/).
Project P06 reinforces that observability must support trace replay
(https://walkinglabs.github.io/learn-harness-engineering/en/projects/project-06-runtime-observability-and-debugging/).

MechaHarness expresses this as ``ModelInputManifest``: messages, tool schemas,
instructions, and content hashes emitted before inference::

    >>> from mechaharness.model_input_manifest import (
    ...     ModelInputManifest, content_digest, reconstruct_messages,
    ... )
    >>> messages = [
    ...     {"role": "system", "content": "You are a careful agent."},
    ...     {"role": "user", "content": "Summarize the diff."},
    ... ]
    >>> manifest = ModelInputManifest.from_parts(
    ...     messages=messages,
    ...     tool_definitions=[{"name": "read_file", "parameters": {"type": "object"}}],
    ...     instructions=["Prefer repository state over chat memory."],
    ... )
    >>> manifest.content_hashes["messages"] == content_digest(messages)
    True
    >>> reconstruct_messages(manifest) == messages
    True
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def content_digest(value: Any) -> str:
    """Stable SHA-256 hex digest of a JSON-serializable value."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ModelInputManifest(BaseModel):
    """Everything model-visible for one inference call, with content hashes."""

    model_config = ConfigDict(extra="allow")

    manifest_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = "1"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_definitions: list[dict[str, Any]] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    content_hashes: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    lane: str | None = None
    run_id: str | None = None
    node_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_parts(
        cls,
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        tool_definitions: Sequence[Mapping[str, Any]] | None = None,
        instructions: Sequence[str] | None = None,
        context_refs: Sequence[str] | None = None,
        model: str | None = None,
        lane: str | None = None,
        run_id: str | None = None,
        node_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
        manifest_id: str | None = None,
    ) -> ModelInputManifest:
        msg_list = [dict(item) for item in (messages or ())]
        tools = [dict(item) for item in (tool_definitions or ())]
        instr = list(instructions or ())
        refs = list(context_refs or ())
        hashes = {
            "messages": content_digest(msg_list),
            "tool_definitions": content_digest(tools),
            "instructions": content_digest(instr),
            "context_refs": content_digest(refs),
        }
        return cls(
            manifest_id=manifest_id or str(uuid4()),
            messages=msg_list,
            tool_definitions=tools,
            instructions=instr,
            context_refs=refs,
            content_hashes=hashes,
            model=model,
            lane=lane,
            run_id=run_id,
            node_id=node_id,
            extra=dict(extra or {}),
        )

    def verify_hashes(self) -> bool:
        """Return True when stored hashes match current payload digests."""
        expected = {
            "messages": content_digest(self.messages),
            "tool_definitions": content_digest(self.tool_definitions),
            "instructions": content_digest(self.instructions),
            "context_refs": content_digest(self.context_refs),
        }
        return self.content_hashes == expected

    def to_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def reconstruct_messages(manifest: ModelInputManifest) -> list[dict[str, Any]]:
    """Rebuild message list from a recorded manifest (no hidden in-memory state)."""
    if not manifest.verify_hashes():
        raise ValueError("manifest content hashes do not match payload")
    return [dict(item) for item in manifest.messages]


def attach_manifest_ref(
    decision_fields: dict[str, Any], manifest: ModelInputManifest
) -> dict[str, Any]:
    """Return decision fields with ``context_manifest_ref`` set to the manifest id."""
    out = dict(decision_fields)
    out["context_manifest_ref"] = manifest.manifest_id
    return out
