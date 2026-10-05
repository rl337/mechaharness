from mechaharness.environment_delta import EnvironmentSnapshot, apply_deltas, emit_delta

def test_delta():
    a=EnvironmentSnapshot(version=1,data={"cwd":"/a"})
    b=EnvironmentSnapshot(version=2,data={"cwd":"/b"})
    assert apply_deltas(a,[emit_delta(a,b)]).data["cwd"]=="/b"
