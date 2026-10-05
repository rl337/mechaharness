from mechaharness.workspace_isolation import (
    InMemoryWorkspaceIsolationProvider,
    WorkspaceIsolationRequest,
)


def test_acquire_release():
    p = InMemoryWorkspaceIsolationProvider()
    h = p.acquire(WorkspaceIsolationRequest(label="x"))
    assert h.provider_kind == "memory"
    p.release(h)
