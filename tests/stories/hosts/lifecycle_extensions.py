"""Story-host lifecycle extension fixtures (not library product demos)."""

from __future__ import annotations

from mechaharness.lifecycle_extension import (
    BeforeGraphNode,
    BeforeTool,
    Block,
    ExtensionEffect,
    LifecycleExtension,
    LifecycleExtensionContext,
    ObserveBefore,
    Replace,
    Rewrite,
)

__all__ = [
    "BlockWrite",
    "GraphWatch",
    "ReplaceWrite",
    "SandboxRewrite",
    "WatchA",
    "WatchB",
    "STORY_LIFECYCLE_EXTENSIONS",
]


class WatchA(LifecycleExtension):
    extension_id = "acme:watch_a"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key(), notes={"tag": "a"})


class WatchB(LifecycleExtension):
    extension_id = "acme:watch_b"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key(), notes={"tag": "b"})


class SandboxRewrite(LifecycleExtension):
    extension_id = "acme:sandbox_rewrite"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Rewrite})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        path = str(context.arguments.get("path", ""))
        return ExtensionEffect(
            mode=Rewrite.key(),
            rewrite_arguments={"path": f"/sandbox/{path}"},
        )


class BlockWrite(LifecycleExtension):
    extension_id = "acme:block_write"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Block})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Block.key(),
            block=True,
            block_message="blocked by host extension",
        )


class ReplaceWrite(LifecycleExtension):
    extension_id = "acme:replace_write"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Replace})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Replace.key(),
            replace_content="hand-off: skipped write",
        )


class GraphWatch(LifecycleExtension):
    extension_id = "acme:graph_watch"
    version = "1"
    boundary = BeforeGraphNode
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key())


STORY_LIFECYCLE_EXTENSIONS: dict[str, type[LifecycleExtension]] = {
    WatchA.extension_id: WatchA,
    WatchB.extension_id: WatchB,
    SandboxRewrite.extension_id: SandboxRewrite,
    BlockWrite.extension_id: BlockWrite,
    ReplaceWrite.extension_id: ReplaceWrite,
    GraphWatch.extension_id: GraphWatch,
}
