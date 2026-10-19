"""Story ops for the durable graph-generator harness family."""

from __future__ import annotations

from pyiv.time import PythonDateTimeService

from mechaharness.core.events import InMemoryEventLog
from mechaharness.durable_graph_generator import (
    DurableGraphGenerator,
    GuidanceResponse,
    InMemoryGeneratorRunStore,
    ScriptedDriver,
)
from mechaharness.graph_templates import GraphTemplateRegistry, VerifyRepairTemplate
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.harness.base import StoryOpRunner, assert_expect


def _build_generator(
    store: InMemoryGeneratorRunStore | None = None,
) -> tuple[DurableGraphGenerator, InMemoryGeneratorRunStore]:
    registry = GraphTemplateRegistry([VerifyRepairTemplate()])
    runs = store or InMemoryGeneratorRunStore()
    gen = DurableGraphGenerator(
        registry=registry,
        run_store=runs,
        event_log=InMemoryEventLog(),
        datetime_service=PythonDateTimeService(),
    )
    return gen, runs


async def _run_complete_on_start(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    y = gen.start(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        controller_id=req.get("controller_id", "story"),
        run_id=req.get("run_id"),
    )
    recipes = [r.recipe_id for r in gen.list_recipes()]
    assert_expect(
        {
            "kind": y.kind,
            "sequence": y.sequence,
            "recipe_listed": req.get("recipe", "verify_repair") in recipes,
            "guidance_yields": gen.inspect(y.run_id).cost.get("guidance_yields"),
        },
        expect,
    )


async def _run_guidance_cycle(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    y = gen.start(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        controller_id=req.get("controller_id", "story"),
        run_id=req.get("run_id", "guidance-run"),
    )
    kinds = [y.kind]
    if y.kind == "advice_requested":
        answer = req.get("response") or {"choice_id": "precise"}
        resp = GuidanceResponse(
            request_id=y.request_id or answer.get("request_id", ""),
            choice_id=answer.get("choice_id"),
            text=answer.get("text"),
            structured=dict(answer.get("structured") or {}),
        )
        done = gen.resume(
            y.run_id,
            resp,
            expected_sequence=y.sequence,
            controller_id=req.get("controller_id", "story"),
            idempotency_key=req.get("idempotency_key", "story-key"),
        )
        kinds.append(done.kind)
        final = done
    else:
        final = y
    insp = gen.inspect(final.run_id)
    assert_expect(
        {
            "kinds": kinds,
            "final_kind": final.kind,
            "pending_cleared": insp.pending_request is None,
            "resumes": insp.cost.get("resumes"),
        },
        expect,
    )


async def _run_session_resume(case: StoryCase, backend: StoryBackend) -> None:
    """Start returns a yield; a separate resume call advances (no recursive callback)."""
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    first = gen.start(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        controller_id="session",
        run_id="session-1",
    )
    second = gen.resume(
        first.run_id,
        GuidanceResponse(
            request_id=first.request_id or "",
            choice_id=(req.get("response") or {}).get("choice_id", "a"),
        ),
        expected_sequence=first.sequence,
        controller_id="session",
    )
    assert_expect(
        {
            "start_kind": first.kind,
            "resume_kind": second.kind,
            "separate_calls": first.sequence != second.sequence,
        },
        expect,
    )


async def _run_scripted_replay(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    driver = ScriptedDriver(gen)
    strict = bool(req.get("strict_unexpected_advice", True))
    unexpected_failed = False
    kinds: list[str] = []
    try:
        yields = driver.run(
            req.get("recipe", "verify_repair"),
            req.get("inputs") or {},
            responses=list(req.get("responses") or ()),
            expected_kinds=req.get("expected_kinds"),
            strict_unexpected_advice=strict,
        )
        kinds = [y.kind for y in yields]
    except AssertionError:
        unexpected_failed = True
    assert_expect(
        {
            "kinds": kinds,
            "unexpected_advice_failed": unexpected_failed,
        },
        expect,
    )


async def _run_survive_restart(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    store = InMemoryGeneratorRunStore()
    gen1, _ = _build_generator(store)
    y = gen1.start(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        controller_id="c1",
        run_id="restart-1",
    )
    gen2, _ = _build_generator(store)
    insp = gen2.inspect("restart-1")
    assert_expect(
        {
            "start_kind": y.kind,
            "pending_question": (
                insp.pending_request.question if insp.pending_request else None
            ),
            "same_request_id": (
                insp.pending_request.request_id == y.request_id
                if insp.pending_request
                else False
            ),
            "phase": insp.phase,
        },
        expect,
    )


async def _run_resume_idempotent(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    y = gen.start(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        controller_id="c1",
        run_id="idem-1",
    )
    resp = GuidanceResponse(
        request_id=y.request_id or "",
        choice_id=(req.get("response") or {}).get("choice_id", "a"),
    )
    a = gen.resume(
        "idem-1",
        resp,
        expected_sequence=y.sequence,
        controller_id="c1",
        idempotency_key="same",
    )
    b = gen.resume(
        "idem-1",
        resp,
        expected_sequence=y.sequence,
        controller_id="c1",
        idempotency_key="same",
    )
    stale_rejected = False
    try:
        gen.resume(
            "idem-1",
            resp,
            expected_sequence=y.sequence + 100,
            controller_id="c1",
            idempotency_key="other",
        )
    except ValueError:
        stale_rejected = True
    assert_expect(
        {
            "first_kind": a.kind,
            "second_kind": b.kind,
            "same_sequence": a.sequence == b.sequence,
            "stale_rejected": stale_rejected,
        },
        expect,
    )


async def _run_controller_auth(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    y = gen.start(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        controller_id="owner",
        run_id="auth-1",
    )
    intruder_rejected = False
    try:
        gen.resume(
            "auth-1",
            GuidanceResponse(
                request_id=y.request_id or "",
                choice_id=(req.get("response") or {}).get("choice_id", "a"),
            ),
            expected_sequence=y.sequence,
            controller_id="intruder",
        )
    except PermissionError:
        intruder_rejected = True
    approval_rejected = False
    if req.get("final_approval"):
        gen2, _ = _build_generator()
        y2 = gen2.start(
            "verify_repair",
            {
                "guidance": [
                    {
                        "question": "Ship?",
                        "requested_authority": "final_approval",
                        "choices": [{"id": "yes", "label": "Yes"}],
                    }
                ]
            },
            controller_id="owner",
            run_id="auth-2",
        )
        try:
            gen2.resume(
                "auth-2",
                GuidanceResponse(request_id=y2.request_id or "", choice_id="yes"),
                expected_sequence=y2.sequence,
                controller_id="owner",
            )
        except PermissionError:
            approval_rejected = True
    assert_expect(
        {
            "intruder_rejected": intruder_rejected,
            "final_approval_rejected": approval_rejected,
            "inspect_ok": gen.inspect("auth-1").controller_id == "owner",
        },
        expect,
    )


async def _run_cost_budget(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    req = case.load_json("request.json")
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    driver = ScriptedDriver(gen)
    responses = [
        GuidanceResponse.model_validate(r) if isinstance(r, dict) else r
        for r in (req.get("responses") or [])
    ]
    # Fill request_ids after start via driver internals — use explicit ids in fixture.
    yields = driver.run(
        req.get("recipe", "verify_repair"),
        req.get("inputs") or {},
        responses=responses,
        controller_id="ops",
        run_id="cost-1",
        strict_unexpected_advice=False,
    )
    insp = gen.inspect(yields[0].run_id)
    assert_expect(
        {
            "guidance_yields": insp.cost.get("guidance_yields"),
            "resumes": insp.cost.get("resumes"),
            "local_steps": insp.cost.get("local_steps"),
            "final_kind": yields[-1].kind,
        },
        expect,
    )


async def _run_mcp_gap(case: StoryCase, backend: StoryBackend) -> None:
    """Gap story: MCP stdio adapter is not shipped in M1."""
    del backend
    expect = case.load_json("expect.json")
    try:
        import mechaharness.mcp_graph_driver  # type: ignore  # noqa: F401
        mcp_shipped = True
    except ImportError:
        mcp_shipped = False
    assert_expect({"mcp_adapter_shipped": mcp_shipped}, expect)


async def _run_shared_driver_contract(case: StoryCase, backend: StoryBackend) -> None:
    """Core ops + MCP adapter; human CLI/TUI client remains gap."""
    del backend
    expect = case.load_json("expect.json")
    gen, _ = _build_generator()
    ops = ["start", "resume", "inspect", "cancel", "list_recipes"]
    present = all(hasattr(gen, name) for name in ops)
    try:
        import mechaharness.mcp_graph_driver  # noqa: F401

        mcp_present = True
    except ImportError:
        mcp_present = False
    assert_expect(
        {
            "core_ops_present": present,
            "mcp_adapter_present": mcp_present,
            "cli_client_gap": True,
            "scripted_driver_present": True,
        },
        expect,
    )


RUNNERS: dict[str, StoryOpRunner] = {
    "durable_complete_on_start": _run_complete_on_start,
    "durable_guidance_cycle": _run_guidance_cycle,
    "durable_session_resume": _run_session_resume,
    "durable_scripted_replay": _run_scripted_replay,
    "durable_survive_restart": _run_survive_restart,
    "durable_resume_idempotent": _run_resume_idempotent,
    "durable_controller_auth": _run_controller_auth,
    "durable_cost_budget": _run_cost_budget,
    "durable_mcp_gap": _run_mcp_gap,
    "durable_shared_driver_contract": _run_shared_driver_contract,
}
