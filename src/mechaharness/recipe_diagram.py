"""Pure-Python SVG layout for Agentic Recipe execution graphs.

Owns boxes, circles, ER-style field tables, titled loop containers, and
arrow routing. No Mermaid or Graphviz — layout is deterministic and
host-independent so CLI ``recipes render`` does not need a system binary.

Loop interiors pack ~3 steps per row in a serpentine (boustrophedon) grid:
even rows left→right, odd rows right→left. Row wraps use a C-shaped path on
the shared side so the connector does not slash diagonally across the box.

Parallel fan-out / fan-in (N edges that share a source+label or sink+label)
collapse into one **stack band**: members draw as a tight vertical stack, and
the N outer edges become a single arrow into / out of the band so lines never
cross unrelated sibling boxes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

FONT_SIZE = 12
CHAR_W = 7.0
PAD = 10.0
ROW_H = 20.0
CELL_GAP_X = 36.0
CELL_GAP_Y = 44.0
NODE_GAP_Y = 48.0
STACK_GAP_Y = 8.0
CONTAINER_PAD = 18.0
TITLE_H = 26.0
STACK_MEMBER_H = TITLE_H + PAD
CIRCLE_R = 18.0
MAX_PER_ROW = 3
# Horizontal gutter outside the step grid for C-wrap elbows.
WRAP_GUTTER = 22.0
Stroke = "#2a3340"
Ink = "#1a1f27"
Muted = "#5a6573"
Fill = "#ffffff"
TitleFill = "#e7edf3"
HeaderFill = "#d5dee8"
Accent = "#3d4f63"


@dataclass
class FieldRow:
    name: str
    type: str
    value: str


@dataclass
class StepSpec:
    """One interior step (or start/end sentinel)."""

    id: str
    label: str
    kind: Literal["circle", "rect", "round"] = "rect"


@dataclass
class NodeSpec:
    """Top-level graph node to place.

    When ``members`` is non-empty this is a parallel **stack band** (fan-out /
    fan-in siblings drawn as one unit with a single outer arrow).
    """

    id: str
    kind: str
    title: str
    subtitle: str = ""
    fields: list[FieldRow] = field(default_factory=list)
    steps: list[StepSpec] = field(default_factory=list)
    members: list[NodeSpec] = field(default_factory=list)


@dataclass
class EdgeSpec:
    src: str
    dst: str
    label: str = ""


@dataclass
class _Placed:
    id: str
    x: float
    y: float
    w: float
    h: float
    anchor: str = "box"  # box | cluster


def _esc(text: Any) -> str:
    s = str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _tw(text: str) -> float:
    return max(len(text), 1) * CHAR_W


def _chunk(items: Sequence[Any], size: int) -> list[list[Any]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _measure_table(
    title: str, subtitle: str, fields: Sequence[FieldRow]
) -> tuple[float, float, list[float]]:
    cols = ["name", "type", "value"]
    widths = [_tw(c) + 2 * PAD for c in cols]
    for row in fields:
        widths[0] = max(widths[0], _tw(row.name) + 2 * PAD)
        widths[1] = max(widths[1], _tw(row.type) + 2 * PAD)
        widths[2] = max(widths[2], _tw(row.value) + 2 * PAD)
    body_w = sum(widths)
    title_w = _tw(title) + 2 * PAD
    sub_w = _tw(subtitle) + 2 * PAD if subtitle else 0.0
    w = max(body_w, title_w, sub_w, 160.0)
    # Stretch value column to absorb extra width.
    extra = w - body_w
    if extra > 0:
        widths[2] += extra
    h = TITLE_H + (ROW_H if subtitle else 0.0) + ROW_H * (1 + len(fields)) + 2
    return w, h, widths


def _measure_step(step: StepSpec) -> tuple[float, float]:
    if step.kind == "circle":
        d = 2 * CIRCLE_R
        return d, d
    w = max(_tw(step.label) + 2 * PAD, 72.0)
    h = ROW_H + PAD
    return w, h


def _measure_stack(title: str, members: Sequence[NodeSpec]) -> tuple[float, float]:
    member_ws = [
        max(_tw(m.title) + 2 * PAD, 120.0) for m in members
    ] or [120.0]
    inner_w = max(member_ws)
    w = max(inner_w + 2 * CONTAINER_PAD, _tw(title) + 2 * CONTAINER_PAD, 160.0)
    body_h = (
        len(members) * STACK_MEMBER_H
        + STACK_GAP_Y * max(len(members) - 1, 0)
    )
    h = TITLE_H + CONTAINER_PAD + body_h + CONTAINER_PAD
    return w, h


def coalesce_parallel_bands(
    nodes: Sequence[NodeSpec],
    edges: Sequence[EdgeSpec],
) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    """Collapse N-way fan-out / fan-in into stack bands with single arrows.

    A set of ≥2 nodes that share the same ``(src, label)`` fan-out and/or the
    same ``(dst, label)`` fan-in becomes one band. Outer edges are rewritten to
    attach to the band id so arrows do not thread through sibling boxes.
    """
    by_id = {n.id: n for n in nodes}
    outs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    ins: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for e in edges:
        if e.src in by_id and e.dst in by_id:
            outs[e.src][e.label].append(e.dst)
            ins[e.dst][e.label].append(e.src)

    candidates: list[frozenset[str]] = []
    for _src, by_label in outs.items():
        for _label, dsts in by_label.items():
            if len(dsts) >= 2:
                candidates.append(frozenset(dsts))
    for _dst, by_label in ins.items():
        for _label, srcs in by_label.items():
            if len(srcs) >= 2:
                candidates.append(frozenset(srcs))

    # Largest first; skip overlapping sets.
    candidates.sort(key=len, reverse=True)
    claimed: set[str] = set()
    bands: list[tuple[str, list[str], str]] = []  # band_id, members, title
    for cand in candidates:
        if len(cand) < 2 or cand & claimed:
            continue
        members = sorted(cand)
        # Prefer a fan-out label for the band title when present.
        title_label = "parallel"
        for _src, by_label in outs.items():
            for label, dsts in by_label.items():
                if set(dsts) == set(members):
                    title_label = label or "parallel"
                    break
            else:
                continue
            break
        else:
            for _dst, by_label in ins.items():
                for label, srcs in by_label.items():
                    if set(srcs) == set(members):
                        title_label = label or "parallel"
                        break
                else:
                    continue
                break
        band_id = f"band:{members[0]}..{members[-1]}×{len(members)}"
        bands.append((band_id, members, f"{title_label} ×{len(members)}"))
        claimed.update(members)

    if not bands:
        return list(nodes), list(edges)

    member_to_band = {
        mid: band_id for band_id, members, _ in bands for mid in members
    }
    new_nodes: list[NodeSpec] = []
    for n in nodes:
        if n.id in claimed:
            continue
        new_nodes.append(n)
    for band_id, members, title in bands:
        new_nodes.append(
            NodeSpec(
                id=band_id,
                kind="parallel_band",
                title=title,
                members=[by_id[m] for m in members],
            )
        )

    def _map_endpoint(nid: str) -> str:
        return member_to_band.get(nid, nid)

    # Collapse edges that touch the band to one arrow per (src, dst, label).
    seen_edge: set[tuple[str, str, str]] = set()
    new_edges: list[EdgeSpec] = []
    for e in edges:
        src = _map_endpoint(e.src)
        dst = _map_endpoint(e.dst)
        if src == dst:
            continue  # drop intra-band / collapsed self edges
        key = (src, dst, e.label)
        if key in seen_edge:
            continue
        seen_edge.add(key)
        new_edges.append(EdgeSpec(src=src, dst=dst, label=e.label))
    return new_nodes, new_edges


def _measure_container(
    title: str, steps: Sequence[StepSpec], per_row: int = MAX_PER_ROW
) -> tuple[float, float, list[list[tuple[StepSpec, float, float]]]]:
    ordered = list(steps)
    rows_raw = _chunk(ordered, per_row) if ordered else [[]]
    measured: list[list[tuple[StepSpec, float, float]]] = []
    row_widths: list[float] = []
    row_heights: list[float] = []
    for row in rows_raw:
        cells: list[tuple[StepSpec, float, float]] = []
        rh = 0.0
        rw = 0.0
        for i, step in enumerate(row):
            sw, sh = _measure_step(step)
            cells.append((step, sw, sh))
            rh = max(rh, sh)
            rw += sw + (CELL_GAP_X if i else 0.0)
        measured.append(cells)
        row_widths.append(rw)
        row_heights.append(rh)
    inner_w = max(row_widths) if row_widths else 80.0
    # Room on both sides for serpentine C-wrap elbows.
    wrap_pad = WRAP_GUTTER if len(measured) > 1 else 0.0
    inner_h = sum(row_heights) + CELL_GAP_Y * max(len(row_heights) - 1, 0)
    w = max(
        inner_w + 2 * CONTAINER_PAD + 2 * wrap_pad,
        _tw(title) + 2 * CONTAINER_PAD,
        200.0,
    )
    h = TITLE_H + CONTAINER_PAD + inner_h + CONTAINER_PAD
    return w, h, measured


class RecipeDiagram:
    """Layout + SVG emit for a recipe execution diagram."""

    def __init__(
        self,
        *,
        title: str,
        nodes: Sequence[NodeSpec],
        edges: Sequence[EdgeSpec],
        per_row: int = MAX_PER_ROW,
    ) -> None:
        self.title = title
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.per_row = per_row
        self._placed: dict[str, _Placed] = {}
        self._parts: list[str] = []
        self._width = 0.0
        self._height = 0.0

    def layout(self) -> None:
        self.nodes, self.edges = coalesce_parallel_bands(self.nodes, self.edges)
        order = self._topo_order()
        by_id = {n.id: n for n in self.nodes}
        y = 36.0  # room for diagram title
        max_w = 0.0
        cursor_x = 24.0
        for nid in order:
            node = by_id[nid]
            if node.members:
                w, h = _measure_stack(node.title, node.members)
                self._draw_stack(node, cursor_x, y, w, h)
            elif node.steps:
                w, h, measured = _measure_container(
                    node.title, node.steps, per_row=self.per_row
                )
                self._draw_container(node, cursor_x, y, w, h, measured)
            elif node.fields:
                w, h, widths = _measure_table(node.title, node.subtitle, node.fields)
                self._draw_table(node, cursor_x, y, w, h, widths)
            else:
                w = max(_tw(node.title) + 2 * PAD, 120.0)
                h = TITLE_H + PAD
                self._draw_plain(node, cursor_x, y, w, h)
            self._placed[nid] = _Placed(id=nid, x=cursor_x, y=y, w=w, h=h)
            max_w = max(max_w, cursor_x + w)
            y += h + NODE_GAP_Y
        self._width = max_w + 24.0
        self._height = y - NODE_GAP_Y + 24.0
        self._draw_edges()

    def _topo_order(self) -> list[str]:
        ids = [n.id for n in self.nodes]
        indeg = {i: 0 for i in ids}
        outs: dict[str, list[str]] = {i: [] for i in ids}
        for e in self.edges:
            if e.src in indeg and e.dst in indeg:
                outs[e.src].append(e.dst)
                indeg[e.dst] += 1
        queue = [i for i in ids if indeg[i] == 0]
        ordered: list[str] = []
        seen = set(queue)
        while queue:
            cur = queue.pop(0)
            ordered.append(cur)
            for nxt in outs[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0 and nxt not in seen:
                    queue.append(nxt)
                    seen.add(nxt)
        for i in ids:
            if i not in seen:
                ordered.append(i)
        return ordered

    def _draw_plain(self, node: NodeSpec, x: float, y: float, w: float, h: float) -> None:
        rx = 4 if node.kind.endswith("loop") else 2
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{Fill}" stroke="{Stroke}" stroke-width="1.5"/>'
        )
        self._parts.append(
            f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + 4:.1f}" '
            f'text-anchor="middle" font-family="ui-monospace, Menlo, monospace" '
            f'font-size="{FONT_SIZE}" fill="{Ink}">{_esc(node.title)}</text>'
        )

    def _draw_stack(
        self, node: NodeSpec, x: float, y: float, w: float, h: float
    ) -> None:
        """Titled band containing tightly stacked sibling nodes (no inner arrows)."""
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="10" fill="{Fill}" stroke="{Stroke}" stroke-width="1.8"/>'
        )
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{TITLE_H:.1f}" '
            f'rx="10" fill="{TitleFill}" stroke="none"/>'
        )
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y + TITLE_H - 10:.1f}" width="{w:.1f}" '
            f'height="10" fill="{TitleFill}" stroke="none"/>'
        )
        self._parts.append(
            f'<line x1="{x:.1f}" y1="{y + TITLE_H:.1f}" x2="{x + w:.1f}" '
            f'y2="{y + TITLE_H:.1f}" stroke="{Stroke}" stroke-width="1"/>'
        )
        self._parts.append(
            f'<text x="{x + CONTAINER_PAD:.1f}" y="{y + TITLE_H - 8:.1f}" '
            f'font-family="ui-monospace, Menlo, monospace" font-size="{FONT_SIZE}" '
            f'font-weight="600" fill="{Ink}">{_esc(node.title)}</text>'
        )
        inner_w = w - 2 * CONTAINER_PAD
        cy = y + TITLE_H + CONTAINER_PAD
        for member in node.members:
            mw = min(max(_tw(member.title) + 2 * PAD, 120.0), inner_w)
            mx = x + (w - mw) / 2.0
            self._parts.append(
                f'<rect x="{mx:.1f}" y="{cy:.1f}" width="{mw:.1f}" '
                f'height="{STACK_MEMBER_H:.1f}" rx="3" fill="{Fill}" '
                f'stroke="{Stroke}" stroke-width="1.2"/>'
            )
            self._parts.append(
                f'<text x="{mx + mw / 2:.1f}" y="{cy + STACK_MEMBER_H / 2 + 4:.1f}" '
                f'text-anchor="middle" font-family="ui-monospace, Menlo, monospace" '
                f'font-size="{FONT_SIZE - 1}" fill="{Ink}">{_esc(member.title)}</text>'
            )
            cy += STACK_MEMBER_H + STACK_GAP_Y

    def _draw_table(
        self,
        node: NodeSpec,
        x: float,
        y: float,
        w: float,
        h: float,
        widths: list[float],
    ) -> None:
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="3" fill="{Fill}" stroke="{Stroke}" stroke-width="1.5"/>'
        )
        # Title band
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{TITLE_H:.1f}" '
            f'rx="3" fill="{TitleFill}" stroke="none"/>'
        )
        self._parts.append(
            f'<line x1="{x:.1f}" y1="{y + TITLE_H:.1f}" x2="{x + w:.1f}" '
            f'y2="{y + TITLE_H:.1f}" stroke="{Stroke}" stroke-width="1"/>'
        )
        self._parts.append(
            f'<text x="{x + PAD:.1f}" y="{y + TITLE_H - 8:.1f}" '
            f'font-family="ui-monospace, Menlo, monospace" font-size="{FONT_SIZE}" '
            f'font-weight="600" fill="{Ink}">{_esc(node.title)}</text>'
        )
        cy = y + TITLE_H
        if node.subtitle:
            self._parts.append(
                f'<text x="{x + PAD:.1f}" y="{cy + ROW_H - 6:.1f}" '
                f'font-family="ui-monospace, Menlo, monospace" '
                f'font-size="{FONT_SIZE - 1}" fill="{Muted}">{_esc(node.subtitle)}</text>'
            )
            cy += ROW_H
            self._parts.append(
                f'<line x1="{x:.1f}" y1="{cy:.1f}" x2="{x + w:.1f}" '
                f'y2="{cy:.1f}" stroke="{Stroke}" stroke-width="0.75"/>'
            )
        # Header
        self._parts.append(
            f'<rect x="{x:.1f}" y="{cy:.1f}" width="{w:.1f}" height="{ROW_H:.1f}" '
            f'fill="{HeaderFill}" stroke="none"/>'
        )
        headers = ["name", "type", "value"]
        cx = x
        for i, head in enumerate(headers):
            self._parts.append(
                f'<text x="{cx + PAD:.1f}" y="{cy + ROW_H - 6:.1f}" '
                f'font-family="ui-monospace, Menlo, monospace" '
                f'font-size="{FONT_SIZE - 1}" font-weight="600" fill="{Muted}">'
                f"{_esc(head)}</text>"
            )
            if i < len(headers) - 1:
                cx += widths[i]
                self._parts.append(
                    f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" '
                    f'y2="{y + h:.1f}" stroke="{Stroke}" stroke-width="0.6"/>'
                )
        cy += ROW_H
        self._parts.append(
            f'<line x1="{x:.1f}" y1="{cy:.1f}" x2="{x + w:.1f}" '
            f'y2="{cy:.1f}" stroke="{Stroke}" stroke-width="0.75"/>'
        )
        for row in node.fields:
            cx = x
            vals = [row.name, row.type, row.value]
            for i, val in enumerate(vals):
                self._parts.append(
                    f'<text x="{cx + PAD:.1f}" y="{cy + ROW_H - 6:.1f}" '
                    f'font-family="ui-monospace, Menlo, monospace" '
                    f'font-size="{FONT_SIZE - 1}" fill="{Ink}">{_esc(val)}</text>'
                )
                cx += widths[i]
            cy += ROW_H
            if cy < y + h - 1:
                self._parts.append(
                    f'<line x1="{x:.1f}" y1="{cy:.1f}" x2="{x + w:.1f}" '
                    f'y2="{cy:.1f}" stroke="{Stroke}" stroke-width="0.4" '
                    f'opacity="0.5"/>'
                )

    def _draw_container(
        self,
        node: NodeSpec,
        x: float,
        y: float,
        w: float,
        h: float,
        measured: list[list[tuple[StepSpec, float, float]]],
    ) -> None:
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="14" fill="{Fill}" stroke="{Stroke}" stroke-width="1.8"/>'
        )
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{TITLE_H:.1f}" '
            f'rx="14" fill="{TitleFill}" stroke="none"/>'
        )
        # Squared bottom of title band
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y + TITLE_H - 10:.1f}" width="{w:.1f}" '
            f'height="10" fill="{TitleFill}" stroke="none"/>'
        )
        self._parts.append(
            f'<line x1="{x:.1f}" y1="{y + TITLE_H:.1f}" x2="{x + w:.1f}" '
            f'y2="{y + TITLE_H:.1f}" stroke="{Stroke}" stroke-width="1"/>'
        )
        self._parts.append(
            f'<text x="{x + CONTAINER_PAD:.1f}" y="{y + TITLE_H - 8:.1f}" '
            f'font-family="ui-monospace, Menlo, monospace" font-size="{FONT_SIZE}" '
            f'font-weight="600" fill="{Ink}">{_esc(node.title)}</text>'
        )

        # Serpentine rows: even L→R, odd R→L; C-wrap on the shared side.
        # Each entry: (cx, cy, w, h, row_index)
        centers: list[tuple[float, float, float, float, int]] = []
        inner_top = y + TITLE_H + CONTAINER_PAD
        row_widths = [
            sum(sw for _, sw, _ in row) + CELL_GAP_X * max(len(row) - 1, 0)
            for row in measured
        ]
        content_w = max(row_widths) if row_widths else 0.0
        wrap_pad = WRAP_GUTTER if len(measured) > 1 else 0.0
        # Stable grid; WRAP_GUTTER lives in the side pad for C elbows.
        grid_left = x + CONTAINER_PAD + wrap_pad
        grid_right = grid_left + content_w
        cy = inner_top
        for ri, row in enumerate(measured):
            rtl = ri % 2 == 1
            rh = max((sh for _, _, sh in row), default=CIRCLE_R * 2)
            rw = row_widths[ri]
            if not rtl:
                # LTR: first row right-aligns for a right-side C; later LTR
                # rows enter from the left after an odd-row wrap.
                if ri == 0:
                    sx0 = grid_right - rw
                else:
                    sx0 = grid_left
                cx = sx0
                for step, sw, sh in row:
                    sy = cy + (rh - sh) / 2.0
                    self._draw_step(step, cx, sy, sw, sh)
                    centers.append((cx + sw / 2, sy + sh / 2, sw, sh, ri))
                    cx += sw + CELL_GAP_X
            else:
                # RTL: first step of the row sits on the right (same side as
                # the previous row's exit) and flow runs leftward.
                cx = grid_right
                for step, sw, sh in row:
                    cx -= sw
                    sy = cy + (rh - sh) / 2.0
                    self._draw_step(step, cx, sy, sw, sh)
                    centers.append((cx + sw / 2, sy + sh / 2, sw, sh, ri))
                    cx -= CELL_GAP_X
            cy += rh + CELL_GAP_Y

        for i in range(len(centers) - 1):
            ax, ay, aw, ah, ra = centers[i]
            bx, by, bw, bh, rb = centers[i + 1]
            if ra == rb:
                # Horizontal along the row (either direction).
                if ax <= bx:
                    x1, x2 = ax + aw / 2, bx - bw / 2
                else:
                    x1, x2 = ax - aw / 2, bx + bw / 2
                self._arrow(x1, ay, x2, by, label="then")
            else:
                # C-wrap on the side shared by row exit and next-row entry.
                side: Literal["left", "right"] = "right" if ra % 2 == 0 else "left"
                if side == "right":
                    x1, y1 = ax + aw / 2, ay
                    x2, y2 = bx + bw / 2, by
                else:
                    x1, y1 = ax - aw / 2, ay
                    x2, y2 = bx - bw / 2, by
                self._c_arrow(x1, y1, x2, y2, side=side, label="then")

    def _draw_step(self, step: StepSpec, x: float, y: float, w: float, h: float) -> None:
        if step.kind == "circle":
            cx, cy = x + w / 2, y + h / 2
            self._parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{CIRCLE_R:.1f}" '
                f'fill="{Fill}" stroke="{Stroke}" stroke-width="1.5"/>'
            )
            self._parts.append(
                f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" '
                f'font-family="ui-monospace, Menlo, monospace" '
                f'font-size="{FONT_SIZE - 1}" fill="{Ink}">{_esc(step.label)}</text>'
            )
            return
        rx = 12 if step.kind == "round" else 3
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{Fill}" stroke="{Stroke}" stroke-width="1.4"/>'
        )
        self._parts.append(
            f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + 4:.1f}" text-anchor="middle" '
            f'font-family="ui-monospace, Menlo, monospace" '
            f'font-size="{FONT_SIZE - 1}" fill="{Ink}">{_esc(step.label)}</text>'
        )

    def _draw_edges(self) -> None:
        for e in self.edges:
            a = self._placed.get(e.src)
            b = self._placed.get(e.dst)
            if a is None or b is None:
                continue
            x1 = a.x + a.w / 2
            y1 = a.y + a.h
            x2 = b.x + b.w / 2
            y2 = b.y
            self._arrow(x1, y1, x2, y2, label=e.label, exterior=True)

    def _c_arrow(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        side: Literal["left", "right"],
        label: str = "",
    ) -> None:
        """Orthogonal C-shaped connector; endpoints share ``side``."""
        pad = 2.0
        if side == "right":
            elbow = max(x1, x2) + WRAP_GUTTER
            sx, sy = x1 + pad, y1
            ex, ey = x2 + pad, y2
            d = (
                f"M {sx:.1f} {sy:.1f} L {elbow:.1f} {sy:.1f} "
                f"L {elbow:.1f} {ey:.1f} L {ex:.1f} {ey:.1f}"
            )
            label_x = elbow + 10.0
        else:
            elbow = min(x1, x2) - WRAP_GUTTER
            sx, sy = x1 - pad, y1
            ex, ey = x2 - pad, y2
            d = (
                f"M {sx:.1f} {sy:.1f} L {elbow:.1f} {sy:.1f} "
                f"L {elbow:.1f} {ey:.1f} L {ex:.1f} {ey:.1f}"
            )
            label_x = elbow - 10.0
        self._parts.append(
            f'<path d="{d}" fill="none" stroke="{Stroke}" stroke-width="1.2" '
            f'marker-end="url(#arrow)"/>'
        )
        if label:
            label_y = (sy + ey) / 2 + 4.0
            self._parts.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                f'font-family="ui-monospace, Menlo, monospace" '
                f'font-size="{FONT_SIZE - 2}" fill="{Muted}">{_esc(label)}</text>'
            )

    def _arrow(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        label: str = "",
        exterior: bool = False,
    ) -> None:
        # Shorten ends so the shaft clears shapes; exterior targets leave room
        # for the arrowhead so the tip sits on the border (not inside the box).
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        pad_start = 2.0
        pad_end = 10.0 if exterior else 2.0
        sx, sy = x1 + ux * pad_start, y1 + uy * pad_start
        ex, ey = x2 - ux * pad_end, y2 - uy * pad_end
        stroke = Accent if exterior else Stroke
        self._parts.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
            f'stroke="{stroke}" stroke-width="{"1.6" if exterior else "1.2"}" '
            f'marker-end="url(#arrow)"/>'
        )
        if label:
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            # Offset label slightly off the line.
            ox, oy = (-uy * 10, ux * 10) if exterior else (0.0, -10.0)
            self._parts.append(
                f'<text x="{mx + ox:.1f}" y="{my + oy:.1f}" text-anchor="middle" '
                f'font-family="ui-monospace, Menlo, monospace" '
                f'font-size="{FONT_SIZE - 2}" fill="{Muted}">{_esc(label)}</text>'
            )

    def to_svg(self) -> str:
        if not self._placed:
            self.layout()
        title_el = (
            f'<text x="24" y="22" font-family="ui-monospace, Menlo, monospace" '
            f'font-size="14" font-weight="600" fill="{Ink}">'
            f"recipe: {_esc(self.title)}</text>"
        )
        body = "\n  ".join(self._parts)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self._width:.0f}" height="{self._height:.0f}" '
            f'viewBox="0 0 {self._width:.0f} {self._height:.0f}">\n'
            f"  <defs>\n"
            f'    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">\n'
            f'      <path d="M 0 0 L 10 5 L 0 10 z" fill="{Accent}"/>\n'
            f"    </marker>\n"
            f"  </defs>\n"
            f'  <rect width="100%" height="100%" fill="#f7f8fa"/>\n'
            f"  {title_el}\n"
            f"  {body}\n"
            f"</svg>\n"
        )


def build_recipe_svg(
    *,
    title: str,
    nodes: Sequence[NodeSpec],
    edges: Sequence[EdgeSpec],
    per_row: int = MAX_PER_ROW,
) -> str:
    """Layout ``nodes``/``edges`` and return a complete SVG document."""
    diagram = RecipeDiagram(title=title, nodes=nodes, edges=edges, per_row=per_row)
    return diagram.to_svg()


__all__ = [
    "EdgeSpec",
    "FieldRow",
    "NodeSpec",
    "RecipeDiagram",
    "StepSpec",
    "build_recipe_svg",
    "coalesce_parallel_bands",
]
