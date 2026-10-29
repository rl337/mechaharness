"""Bag-to-model context compilation (gastronomic M2).

Freeze a :class:`~mechaharness.walk_bag.WalkBag` snapshot, compile a declared
:class:`ContextSpec` into messages + :class:`ModelInputManifest`, then publish
structured inference results back into the **live** bag.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.core.types import ChatMessage, Role
from mechaharness.model_input_manifest import ModelInputManifest, content_digest
from mechaharness.walk_bag import WalkBag, WalkBagPathError


class ContextSpecError(ValueError):
    """Raised when a ContextSpec cannot be compiled against a bag snapshot."""


class ContextRead(BaseModel):
    """One bag path projected into model-visible context."""

    model_config = ConfigDict(extra="forbid")

    path: str
    required: bool = True
    label: str | None = None


class ContextResponseSpec(BaseModel):
    """Where (and optionally how) to publish a completion into the live bag."""

    model_config = ConfigDict(extra="forbid")

    writes: str
    parse: Literal["json", "text"] = "json"


class ContextSpec(BaseModel):
    """Versioned policy for compiling bag state into one Completer request."""

    model_config = ConfigDict(extra="forbid")

    version: str = "1"
    reads: list[ContextRead] = Field(default_factory=list)
    token_budget: int = 2048
    system: str = ""
    user_preamble: str = "Use only the following bag evidence."
    response: ContextResponseSpec

    @model_validator(mode="after")
    def _reads_or_system(self) -> ContextSpec:
        if not self.reads and not self.system.strip() and not self.user_preamble.strip():
            raise ValueError("ContextSpec needs reads and/or system/user_preamble text")
        return self


class CompiledContext(BaseModel):
    """Result of compiling a ContextSpec against an immutable bag snapshot."""

    model_config = ConfigDict(extra="allow")

    snapshot_id: str
    messages: list[ChatMessage]
    manifest: ModelInputManifest
    included_paths: list[str] = Field(default_factory=list)
    omitted_paths: list[str] = Field(default_factory=list)
    content_hash: str = ""


def _estimate_tokens(text: str) -> int:
    # Cheap deterministic budget proxy (≈4 chars / token).
    return max(1, (len(text) + 3) // 4)


def _format_section(label: str, path: str, value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, default=str)
    title = label or path
    return f"### {title}\npath: {path}\n{rendered}"


def freeze_bag_snapshot(bag: WalkBag) -> tuple[str, WalkBag]:
    """Deep-freeze bag state; return ``(snapshot_id, frozen_bag)``."""
    frozen = bag.deep_snapshot()
    snapshot_id = content_digest({"snapshot": frozen.serialize()})
    return snapshot_id, frozen


def compile_context_spec(
    snapshot: WalkBag,
    spec: ContextSpec,
    *,
    snapshot_id: str,
    model: str | None = None,
    run_id: str | None = None,
    node_id: str | None = None,
) -> CompiledContext:
    """Compile ``spec`` against an immutable bag snapshot into Completer messages."""
    sections: list[str] = []
    included: list[str] = []
    omitted: list[str] = []
    spent = _estimate_tokens(spec.system) + _estimate_tokens(spec.user_preamble)

    for read in spec.reads:
        try:
            value = snapshot.path_get(read.path)
        except WalkBagPathError:
            if read.required:
                raise ContextSpecError(
                    f"required bag path {read.path!r} missing from snapshot"
                ) from None
            omitted.append(read.path)
            continue
        section = _format_section(read.label or read.path, read.path, value)
        cost = _estimate_tokens(section)
        if spent + cost > spec.token_budget and sections:
            omitted.append(read.path)
            continue
        if spent + cost > spec.token_budget and not sections:
            # Always include at least the first fitting fragment when empty.
            raise ContextSpecError(
                f"token_budget {spec.token_budget} too small for path {read.path!r}"
            )
        sections.append(section)
        included.append(read.path)
        spent += cost

    messages: list[ChatMessage] = []
    if spec.system.strip():
        messages.append(ChatMessage(role=Role.SYSTEM, content=spec.system.strip()))
    body_parts = [spec.user_preamble.strip()] if spec.user_preamble.strip() else []
    body_parts.extend(sections)
    user_text = "\n\n".join(p for p in body_parts if p)
    if not user_text.strip():
        raise ContextSpecError("compiled context has empty user message")
    messages.append(ChatMessage(role=Role.USER, content=user_text))

    wire_messages = [
        {"role": m.role.value if hasattr(m.role, "value") else str(m.role), "content": m.content}
        for m in messages
    ]
    manifest = ModelInputManifest.from_parts(
        messages=wire_messages,
        context_refs=[f"bag:{p}" for p in included],
        instructions=[spec.user_preamble] if spec.user_preamble else [],
        model=model,
        run_id=run_id,
        node_id=node_id,
        extra={
            "snapshot_id": snapshot_id,
            "included_paths": included,
            "omitted_paths": omitted,
            "context_spec_version": spec.version,
        },
        manifest_id=str(uuid4()),
    )
    return CompiledContext(
        snapshot_id=snapshot_id,
        messages=messages,
        manifest=manifest,
        included_paths=included,
        omitted_paths=omitted,
        content_hash=manifest.content_hashes.get("messages", ""),
    )


def _parse_json_response(text: str) -> Any:
    """Parse JSON, tolerating optional markdown fences from live models."""
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ContextSpecError(f"response is not valid JSON: {exc}") from exc
        raise ContextSpecError(f"response is not valid JSON: {raw[:120]!r}") from None


def publish_response_to_bag(
    bag: WalkBag,
    spec: ContextResponseSpec,
    text: str,
) -> Any:
    """Parse completion text and write it to ``spec.writes`` on the live bag."""
    if spec.parse == "text":
        value: Any = text
    else:
        value = _parse_json_response(text)
    bag.path_put(spec.writes, WalkBag.copy_value(value))
    return value


def context_spec_from_mapping(raw: Mapping[str, Any] | ContextSpec) -> ContextSpec:
    if isinstance(raw, ContextSpec):
        return raw
    return ContextSpec.model_validate(raw)


__all__ = [
    "CompiledContext",
    "ContextRead",
    "ContextResponseSpec",
    "ContextSpec",
    "ContextSpecError",
    "compile_context_spec",
    "context_spec_from_mapping",
    "freeze_bag_snapshot",
    "publish_response_to_bag",
]
