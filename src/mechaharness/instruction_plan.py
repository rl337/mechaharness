"""Instruction plan domain: oneshot vs list, refine, acceptance checks.

Used by the ``instruction_todo_plan`` Agentic Recipe and by
:class:`~mechaharness.generator_local_work.ProjectCodingLocalWork` when a
durable generator run must classify instructions, build a todo list, and
verify pre / per-item / post-list acceptance — yielding human refinement via
``request_guidance`` then restarting with answers in ``guidance_history``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

PlanMode = Literal["oneshot", "list"]
RefinementKind = Literal["scope", "list"]


@dataclass(frozen=True)
class TodoItem:
    """One executable step with its own acceptance criteria."""

    id: str
    instruction: str
    acceptance: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InstructionPlan:
    """Classified, optionally refined plan ready for execution."""

    mode: PlanMode
    items: list[TodoItem]
    pre_acceptance: list[str] = field(default_factory=list)
    post_acceptance: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    refined: bool = False


@dataclass(frozen=True)
class GuidanceAsk:
    """Payload fragment for DurableGraphGenerator ``request_guidance``."""

    question: str
    context_version: str
    choices: list[dict[str, str]] = field(default_factory=list)
    recommendation: str | None = None
    requested_authority: str = "advisory"
    parent_node_id: str | None = None


@dataclass(frozen=True)
class PlanBuildResult:
    """Either a ready plan or a human refinement ask (restart after answer)."""

    plan: InstructionPlan | None = None
    guidance: list[GuidanceAsk] = field(default_factory=list)


_NUMBERED = re.compile(r"^\s*(?:\d+[\.\)]|[-*])\s+\S", re.MULTILINE)
_CONFLICT_PAIRS = (
    (("delete", "remove", "drop"), ("keep", "retain", "preserve")),
    (("disable", "turn off"), ("enable", "turn on")),
    (("rename to", "rename"), ("keep name", "do not rename")),
)


def classify_mode(inputs: dict[str, Any]) -> PlanMode | None:
    """Return explicit mode, inferred mode, or None when ambiguous."""
    explicit = inputs.get("instruction_mode") or inputs.get("mode")
    if isinstance(explicit, str):
        lowered = explicit.strip().lower()
        if lowered in {"oneshot", "one_shot", "single", "one"}:
            return "oneshot"
        if lowered in {"list", "todo", "multi", "batch"}:
            return "list"
        if lowered in {"auto", "infer"}:
            explicit = None
        else:
            return None
    raw = inputs.get("instructions")
    if raw is None:
        raw = inputs.get("instruction")
    if isinstance(raw, list):
        return "list" if len(raw) > 1 else "oneshot"
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if _NUMBERED.search(text) or text.count("\n") >= 2:
            return "list"
        return "oneshot"
    goal = str(inputs.get("goal") or inputs.get("task") or "").strip()
    if goal and (_NUMBERED.search(goal) or goal.count("\n") >= 2):
        return "list"
    if goal:
        return "oneshot"
    return None


def _split_text_items(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return [text.strip()] if text.strip() else []
    items: list[str] = []
    for ln in lines:
        cleaned = re.sub(r"^\s*(?:\d+[\.\)]|[-*])\s*", "", ln).strip()
        if cleaned:
            items.append(cleaned)
    return items or ([text.strip()] if text.strip() else [])


def extract_instruction_texts(inputs: dict[str, Any]) -> list[str]:
    """Normalize inputs into an ordered list of instruction strings."""
    raw = inputs.get("instructions")
    if raw is None:
        raw = inputs.get("instruction")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return _split_text_items(raw)
    goal = str(inputs.get("goal") or inputs.get("task") or "").strip()
    if goal:
        return _split_text_items(goal) if (_NUMBERED.search(goal) or "\n" in goal) else [goal]
    return []


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def detect_conflicts(items: list[str]) -> list[str]:
    """Heuristic conflict phrases that would fail post-list acceptance."""
    joined = " | ".join(items).lower()
    found: list[str] = []
    for left, right in _CONFLICT_PAIRS:
        if any(tok in joined for tok in left) and any(tok in joined for tok in right):
            found.append(
                f"conflicting intents: {', '.join(left)} vs {', '.join(right)}"
            )
    # Duplicate / near-duplicate instructions
    seen: set[str] = set()
    for item in items:
        key = re.sub(r"\s+", " ", item.lower()).strip()
        if key in seen:
            found.append(f"duplicate instruction: {item!r}")
        seen.add(key)
    return found


def guidance_answers(record_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten guidance_history responses for restart-with-refinement."""
    out: list[dict[str, Any]] = []
    for entry in record_history:
        if not isinstance(entry, dict):
            continue
        req = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        resp = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        out.append(
            {
                "context_version": str(req.get("context_version") or ""),
                "question": str(req.get("question") or ""),
                "choice_id": resp.get("choice_id"),
                "text": resp.get("text"),
                "structured": resp.get("structured") or {},
            }
        )
    return out


def _has_context(answers: list[dict[str, Any]], context_version: str) -> bool:
    return any(a.get("context_version") == context_version for a in answers)


def _refined_texts_from_answers(
    answers: list[dict[str, Any]], *, context_version: str, fallback: list[str]
) -> list[str]:
    for ans in reversed(answers):
        if ans.get("context_version") != context_version:
            continue
        structured = ans.get("structured") or {}
        if isinstance(structured, dict):
            refined = structured.get("instructions") or structured.get("items")
            if isinstance(refined, list) and refined:
                return [str(x).strip() for x in refined if str(x).strip()]
            if isinstance(refined, str) and refined.strip():
                return _split_text_items(refined)
        text = ans.get("text")
        if isinstance(text, str) and text.strip():
            return _split_text_items(text)
    return fallback


def build_instruction_plan(
    inputs: dict[str, Any],
    *,
    guidance_history: list[dict[str, Any]] | None = None,
) -> PlanBuildResult:
    """Classify / refine into a plan, or ask for human refinement first.

    Restart semantics: when ``guidance`` is non-empty, the generator yields
    ``advice_requested``; after the driver answers, call again with the same
    inputs plus updated ``guidance_history``.
    """
    answers = guidance_answers(list(guidance_history or []))
    force = str(inputs.get("force_refinement") or "").strip().lower()

    mode = classify_mode(inputs)
    if force == "scope" and not _has_context(answers, "scope_refinement"):
        return PlanBuildResult(
            guidance=[
                GuidanceAsk(
                    question=(
                        "Is this a single oneshot instruction or a list of "
                        "ordered todo items? Clarify scope and acceptance."
                    ),
                    context_version="scope_refinement",
                    choices=[
                        {"id": "oneshot", "label": "One shot — single change"},
                        {"id": "list", "label": "List — ordered todo items"},
                    ],
                    recommendation="oneshot",
                    parent_node_id="classify",
                )
            ]
        )

    if mode is None:
        if not _has_context(answers, "scope_refinement"):
            return PlanBuildResult(
                guidance=[
                    GuidanceAsk(
                        question=(
                            "Could not classify the instruction as oneshot vs "
                            "list. Which is it, and what are the acceptance criteria?"
                        ),
                        context_version="scope_refinement",
                        choices=[
                            {"id": "oneshot", "label": "One shot"},
                            {"id": "list", "label": "Ordered list"},
                        ],
                        recommendation="oneshot",
                        parent_node_id="classify",
                    )
                ]
            )
        # Use choice from scope refinement
        for ans in reversed(answers):
            if ans.get("context_version") == "scope_refinement":
                choice = str(ans.get("choice_id") or "").lower()
                if choice in {"oneshot", "one_shot", "single"}:
                    mode = "oneshot"
                elif choice in {"list", "todo", "multi"}:
                    mode = "list"
                break
        if mode is None:
            mode = "oneshot"

    texts = extract_instruction_texts(inputs)
    if mode == "list" and len(texts) <= 1 and texts:
        # Explicit list mode with a single blob — still one item unless refined.
        pass
    if mode == "oneshot" and len(texts) > 1:
        texts = [" ".join(texts)] if texts else texts

    texts = _refined_texts_from_answers(
        answers, context_version="list_refinement", fallback=texts
    )
    if mode == "oneshot" and len(texts) > 1:
        texts = [texts[0]]

    pre_ac = _as_str_list(
        inputs.get("pre_acceptance")
        or inputs.get("pre_list_acceptance")
        or inputs.get("acceptance")
    )
    item_ac_default = _as_str_list(
        inputs.get("item_acceptance") or inputs.get("acceptance") or ["item_done"]
    )
    post_ac = _as_str_list(
        inputs.get("post_acceptance")
        or inputs.get("post_list_acceptance")
        or (pre_ac if mode == "list" else item_ac_default)
    )

    conflicts = detect_conflicts(texts) if mode == "list" else []
    declared = _as_str_list(inputs.get("known_conflicts"))
    conflicts = list(dict.fromkeys([*conflicts, *declared]))

    if force == "list" and not _has_context(answers, "list_refinement"):
        conflicts = conflicts or ["forced list refinement"]

    if mode == "list" and conflicts and not _has_context(answers, "list_refinement"):
        return PlanBuildResult(
            guidance=[
                GuidanceAsk(
                    question=(
                        "The todo list has conflicts that would fail post-list "
                        f"acceptance: {'; '.join(conflicts)}. "
                        "Reply with a conflict-free ordered list (text or "
                        "structured.instructions)."
                    ),
                    context_version="list_refinement",
                    choices=[
                        {"id": "revise", "label": "I will revise the list in text"},
                        {
                            "id": "accept_risk",
                            "label": "Proceed anyway (may fail post-accept)",
                        },
                    ],
                    recommendation="revise",
                    parent_node_id="refine_plan",
                )
            ]
        )

    # After list refinement, drop heuristic conflicts if driver chose accept_risk
    # or provided new texts; recompute.
    if mode == "list" and _has_context(answers, "list_refinement"):
        last = next(
            a for a in reversed(answers) if a.get("context_version") == "list_refinement"
        )
        if last.get("choice_id") == "accept_risk":
            conflicts = []
        else:
            conflicts = detect_conflicts(texts)

    if not texts:
        texts = [str(inputs.get("goal") or inputs.get("task") or "untitled")]

    per_item_ac = inputs.get("item_acceptances")
    items: list[TodoItem] = []
    for idx, text in enumerate(texts):
        ac = item_ac_default
        if isinstance(per_item_ac, list) and idx < len(per_item_ac):
            ac = _as_str_list(per_item_ac[idx]) or item_ac_default
        items.append(TodoItem(id=f"item-{idx + 1}", instruction=text, acceptance=ac))

    if mode == "oneshot":
        items = items[:1] or [
            TodoItem(id="item-1", instruction=texts[0], acceptance=item_ac_default)
        ]
        post_ac = post_ac or list(items[0].acceptance)

    return PlanBuildResult(
        plan=InstructionPlan(
            mode=mode,
            items=items,
            pre_acceptance=pre_ac or list(item_ac_default),
            post_acceptance=post_ac,
            conflicts=conflicts,
            refined=_has_context(answers, "list_refinement")
            or _has_context(answers, "scope_refinement"),
        )
    )


def verify_acceptance(
    criteria: list[str],
    *,
    evidence: str,
    checks: dict[str, bool] | None = None,
) -> tuple[bool, list[str]]:
    """Return (ok, failures). Prefer explicit ``checks`` map when provided."""
    failures: list[str] = []
    checks = checks or {}
    for crit in criteria:
        key = crit.strip()
        if not key:
            continue
        if key in checks:
            if not checks[key]:
                failures.append(key)
            continue
        # Soft evidence: criterion substring present in evidence text
        if key.lower() not in evidence.lower() and key not in checks:
            # Unknown criterion without check → pass if evidence non-empty
            if not evidence.strip():
                failures.append(key)
    return (not failures, failures)


def guidance_asks_to_payloads(asks: list[GuidanceAsk]) -> list[dict[str, Any]]:
    """JSON-able list for local_work ``request_guidance``."""
    out: list[dict[str, Any]] = []
    for ask in asks:
        payload: dict[str, Any] = {
            "question": ask.question,
            "context_version": ask.context_version,
            "requested_authority": ask.requested_authority,
            "choices": list(ask.choices),
        }
        if ask.recommendation is not None:
            payload["recommendation"] = ask.recommendation
        if ask.parent_node_id is not None:
            payload["parent_node_id"] = ask.parent_node_id
        out.append(payload)
    return out


__all__ = [
    "GuidanceAsk",
    "InstructionPlan",
    "PlanBuildResult",
    "PlanMode",
    "RefinementKind",
    "TodoItem",
    "build_instruction_plan",
    "classify_mode",
    "detect_conflicts",
    "extract_instruction_texts",
    "guidance_answers",
    "guidance_asks_to_payloads",
    "verify_acceptance",
]
