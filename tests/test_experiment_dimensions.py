from mechaharness.experiment_dimensions import (
    ExperimentDimensions,
    require_dimension_trace_fields,
)


def test_dimension_digest_stable() -> None:
    dims = ExperimentDimensions(
        fixed={"model_revision": "m@1"},
        varying={"tool_surface": ["Read", "Edit"]},
    )
    assert dims.fingerprint_parts()["varying"]["tool_surface"] == ["Edit", "Read"]
    fields = require_dimension_trace_fields({"assignment": "treatment"}, dimensions=dims)
    assert fields["experiment_dimensions_digest"] == dims.digest()
