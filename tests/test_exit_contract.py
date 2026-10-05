from mechaharness.exit_contract import CleanStateContract, evaluate_exit


def test_exit_ok() -> None:
    report = evaluate_exit(
        CleanStateContract(require_handoff_record=True),
        pending_nodes=[],
        checkpoint_durable=True,
        unresolved_effects=[],
        handoff_record_ref="h",
    )
    assert report.ok
