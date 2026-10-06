from mechaharness.core.access import AccessPolicy, GraphExecute, InMemoryAccessControl
from mechaharness.core.environment import NoOpInferenceEnvironment
from mechaharness.core.events import InMemoryEventLog
from mechaharness.graph import ExecutionGraph, GraphNode
from mechaharness.graph import NodeStatus
from mechaharness.graph_executor import CallableGraphNodeRunner, GraphNodeRunnerRegistry, NodeOutcome
from mechaharness.inference_capture import EvaluationOnlyCapture, TrainingGradeCapture
from mechaharness.linkage_resolver import DefaultLinkageResolver


def test_evaluation_only_not_trainable() -> None:
    rec = EvaluationOnlyCapture().capture({"text": "hi"})
    assert not rec.trainable
    assert "token_ids" in rec.unsupported_fields


def test_linkage_rejects_training_grade_when_eval_only() -> None:
    reg = GraphNodeRunnerRegistry()

    async def ok(node, context):
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    reg.register(CallableGraphNodeRunner(["compute"], ok))
    access = InMemoryAccessControl(
        InMemoryEventLog(), AccessPolicy(grants=[GraphExecute])
    )
    resolver = DefaultLinkageResolver(
        reg, access, NoOpInferenceEnvironment(), inference_capture=EvaluationOnlyCapture()
    )
    graph = ExecutionGraph(goal="g")
    graph.add_node(GraphNode(id="a", kind="compute"))
    report = resolver.resolve(
        graph, fingerprint_parts={"required_inference_capture": "training_grade"}
    )
    assert not report.ok
    assert any(e.code == "inference_capture_unsupported" for e in report.edges)
    ok_report = DefaultLinkageResolver(
        reg, access, NoOpInferenceEnvironment(), inference_capture=TrainingGradeCapture()
    ).resolve(graph, fingerprint_parts={"required_inference_capture": "training_grade"})
    assert ok_report.ok
