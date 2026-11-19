"""Runtime expansion of a single child at each level of a project plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.external_effect import ArmedCrashProbe, InjectedProcessCrash
from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphRunContext,
    NodeOutcome,
    RunControl,
)
from mechaharness.host_kit import host_graph_executor


async def walk_project_frames(
    directory: Path,
    depth: int,
    *,
    crash: bool = False,
    fail_leaf: bool = False,
    missing_output: bool = False,
    stepped: bool = False,
    policy: BudgetPolicy | None = None,
) -> dict[str, Any]:
    visited: list[int] = []
    finished: list[int] = []
    leaf_calls = 0

    def graph() -> ExecutionGraph:
        frame = ExecutionGraph(goal="verify project slice")
        frame.add_node(GraphNode(id="plan", kind="plan"))
        frame.add_node(GraphNode(id="work", kind="leaf", depends_on=["plan"], max_attempts=1))
        frame.add_node(GraphNode(id="accept", kind="accept", depends_on=["work"]))
        return frame

    def handle(node: GraphNode, ctx: GraphRunContext) -> NodeOutcome:
        nonlocal leaf_calls
        level = len(ctx.graph.frame_path)
        assert ctx.graph.frame_path[-1] == ctx.run_id
        dispatched = executor.store.latest(run_id=ctx.run_id)
        assert dispatched is not None and dispatched.frame_path == ctx.graph.frame_path
        assert dispatched.frame_return is None
        if node.kind == "plan":
            visited.append(level)
            # Discover the next child at runtime; graph construction never recurses.
            if level < depth:
                child = ctx.graph.nodes["work"]
                child.subgraph = graph().checkpoint()
                child.payload.update(
                    bag_inputs={"in.goal": "in.goal"},
                    bag_outputs={"acc.proof": "out.absent" if missing_output else "out.proof"},
                )
        elif node.kind == "leaf":
            leaf_calls += 1
            assert ctx.bag.path_get("in.goal") == "project"
            ctx.bag.path_put("in.goal", "private child edit")
            ctx.bag.path_put("acc.proof", 0)
            if fail_leaf:
                return NodeOutcome(status=NodeStatus.FAILED, error="leaf check failed")
        else:
            ctx.bag.path_put("out.proof", 1 + ctx.bag.path_get("acc.proof"))
            finished.append(level)
        return NodeOutcome()

    runner = CallableGraphNodeRunner(["plan", "leaf", "accept"], handle)
    path = directory / "frames.sqlite"
    root = graph()
    root.walk_bag = {"in": {"goal": "project"}}
    root_id = "project"
    executor = host_graph_executor(
        runners=[runner],
        checkpoint_path=path,
        crash_probe=ArmedCrashProbe("after_final_commit") if crash else None,
    )
    options = {"run_id": root_id, "budget_policy": policy or BudgetPolicy.unlimited()}
    recovered = False
    pauses = []
    try:
        control = RunControl(mode="one_step") if stepped else RunControl()
        result = await executor.run(root, control=control, **options)
        while result.status == "paused":
            assert result.frame_path[0] == root_id
            assert result.frame_path[-1] == result.active_run_id
            pauses.append(len(result.frame_path))
            executor = host_graph_executor(runners=[runner], checkpoint_path=path)
            result = await executor.run(root, resume=True, control=control, **options)
    except InjectedProcessCrash:
        assert crash
        executor = host_graph_executor(runners=[runner], checkpoint_path=path)
        leaf = executor.store.latest(run_id=root_id + ":work" * (depth - 1))
        assert leaf is not None and leaf.frame_return and not leaf.frame_path
        result = await executor.run(root, resume=True, **options)
        recovered = True
    return {
        "status": result.status,
        "leaf_calls": leaf_calls,
        "visited": visited,
        "accepted": finished,
        "root_bag": result.graph.walk_bag,
        "root_stack": result.graph.frame_path,
        "recovered": recovered,
        "spent": result.graph.frame_spent,
        "pauses": pauses,
    }
