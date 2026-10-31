"""Deterministic discovery hard-node runners (gastronomic M4 P0).

Each capability is a :class:`~mechaharness.graph_executor.GraphNodeRunner` kind
with declared bag ``reads`` / ``writes`` in the node payload. Operations are
read-only on the workspace; bag mutations are atomic via
:meth:`~mechaharness.walk_bag.WalkBag.staged_writes`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyiv.files import Filesystem, RealFilesystem

from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.project_coding_tools import WorkspacePaths
from mechaharness.walk_bag import WalkBag, WalkBagPathError, WalkBagSerializeError

DISCOVERY_HARD_KINDS: tuple[str, ...] = (
    "bag_project",
    "bag_validate",
    "workspace_manifest",
    "file_search",
    "source_extract",
    "evidence_resolve",
    "coverage_measure",
)

_DEFAULT_EXCLUDES = frozenset(
    {".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv"}
)


class DiscoveryHardNodeError(ValueError):
    """Typed failure for a discovery hard-node capability."""


def _as_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DiscoveryHardNodeError(f"{label} must be a mapping")
    return value


def _payload_section(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    raw = payload.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise DiscoveryHardNodeError(f"payload.{key} must be a mapping")
    return {str(k): v for k, v in raw.items()}


def _read_path(bag: WalkBag, path: str, *, required: bool = True) -> Any:
    try:
        return bag.path_get(path)
    except WalkBagPathError:
        if required:
            raise DiscoveryHardNodeError(f"missing required bag path {path!r}") from None
        return None


def _project_fields(
    source: Any,
    *,
    fields: Sequence[str],
    rename: Mapping[str, str] | None = None,
    defaults: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    src = _as_mapping(source, label="bag_project source")
    rename = rename or {}
    defaults = defaults or {}
    out: dict[str, Any] = {}
    for field in fields:
        dest = str(rename.get(field, field))
        if field in src:
            out[dest] = WalkBag.copy_value(src[field])
        elif field in defaults:
            out[dest] = WalkBag.copy_value(defaults[field])
        else:
            raise DiscoveryHardNodeError(f"bag_project missing field {field!r}")
    return out


def _validate_required_fields(value: Any, *, required_fields: Sequence[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "ok": False,
            "errors": [{"path": "", "message": "value is not a mapping"}],
        }
    errors: list[dict[str, str]] = []
    for field in required_fields:
        if field not in value:
            errors.append({"path": str(field), "message": "missing required field"})
    return {"ok": not errors, "errors": errors, "fields_checked": list(required_fields)}


def _resolve_workspace_root(
    workspace_value: Any,
    *,
    default_workspace: Path | None,
) -> Path:
    if isinstance(workspace_value, Mapping):
        raw = workspace_value.get("root")
    else:
        raw = workspace_value
    if raw is None or raw == "":
        if default_workspace is None:
            raise DiscoveryHardNodeError("workspace root not configured")
        return Path(default_workspace).expanduser().resolve()
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        if default_workspace is None:
            raise DiscoveryHardNodeError(
                f"relative workspace root {raw!r} needs a host workspace"
            )
        path = Path(default_workspace).expanduser().resolve() / path
    return path.resolve()


def _file_sha256(fs: Filesystem, path: str) -> str:
    digest = hashlib.sha256()
    digest.update(fs.read_bytes(path))
    return digest.hexdigest()


def _should_exclude(rel: str, excludes: frozenset[str]) -> bool:
    parts = Path(rel).parts
    return any(part in excludes for part in parts)


def build_workspace_manifest(
    *,
    fs: Filesystem,
    root: Path,
    max_files: int = 100,
    excludes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Enumerate confined workspace files with size/hash/classification."""
    paths = WorkspacePaths(root)
    exclude_set = frozenset(excludes) if excludes is not None else _DEFAULT_EXCLUDES
    files: list[dict[str, Any]] = []
    omissions: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    truncated = False

    root_s = str(paths.root)
    if not fs.exists(root_s) or not fs.is_dir(root_s):
        raise DiscoveryHardNodeError(f"workspace root missing or not a directory: {root}")

    for dirpath, dirnames, filenames in fs.walk(root_s):
        # Prune excluded directories in-place for walk.
        kept: list[str] = []
        for name in list(dirnames):
            child = str((Path(dirpath) / name).relative_to(paths.root))
            if _should_exclude(child, exclude_set):
                omissions.append({"path": child, "reason": "excluded"})
            else:
                kept.append(name)
        dirnames[:] = kept

        for name in filenames:
            if truncated or len(files) >= max_files:
                truncated = True
                break
            abs_path = Path(dirpath) / name
            try:
                rel = str(Path(dirpath).relative_to(paths.root) / name).replace("\\", "/")
            except ValueError:
                # Symlink / walk root drift: resolve through WorkspacePaths.
                try:
                    confined = paths.resolve(name if Path(dirpath) == paths.root else str(abs_path))
                    rel = str(confined.relative_to(paths.root)).replace("\\", "/")
                except ValueError:
                    errors.append({"path": str(abs_path), "reason": "symlink_or_escape"})
                    continue
            if _should_exclude(rel, exclude_set):
                omissions.append({"path": rel, "reason": "excluded"})
                continue
            try:
                confined = paths.resolve(rel)
            except ValueError as exc:
                errors.append({"path": rel, "reason": f"escape:{exc}"})
                continue
            target = str(confined)
            if not fs.is_file(target):
                continue
            try:
                size = int(fs.get_size(target))
                digest = _file_sha256(fs, target)
            except OSError as exc:
                errors.append({"path": rel, "reason": f"unreadable:{exc}"})
                continue
            kind = "text"
            if Path(rel).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bin"}:
                kind = "binary"
            files.append(
                {
                    "path": rel,
                    "size": size,
                    "sha256": digest,
                    "kind": kind,
                }
            )
        if truncated:
            break

    files.sort(key=lambda row: str(row["path"]))
    return {
        "root": str(paths.root),
        "files": files,
        "omissions": omissions,
        "errors": errors,
        "coverage": {
            "file_count": len(files),
            "max_files": max_files,
            "truncated": truncated,
        },
    }


def search_manifest_files(
    *,
    fs: Filesystem,
    root: Path,
    manifest: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any] | str],
    max_matches: int = 50,
) -> dict[str, Any]:
    """Literal/regex search over manifest paths; record provenance + truncation."""
    paths = WorkspacePaths(root)
    by_path = {
        str(row["path"]): row
        for row in (manifest.get("files") or [])
        if isinstance(row, Mapping) and row.get("path")
    }
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    truncated = False

    for raw_q in queries:
        if truncated:
            break
        if isinstance(raw_q, str):
            pattern = raw_q
            mode = "literal"
            query_id = raw_q
        else:
            pattern = str(raw_q.get("pattern") or "")
            mode = str(raw_q.get("mode") or "literal")
            query_id = str(raw_q.get("id") or pattern)
        if not pattern:
            errors.append({"query": query_id, "reason": "empty_pattern"})
            continue
        try:
            rx = re.compile(re.escape(pattern) if mode == "literal" else pattern)
        except re.error as exc:
            errors.append({"query": query_id, "reason": f"invalid_regex:{exc}"})
            continue
        for rel, meta in by_path.items():
            if truncated or len(matches) >= max_matches:
                truncated = True
                break
            try:
                target = paths.resolve(rel)
            except ValueError as exc:
                errors.append({"query": query_id, "path": rel, "reason": f"escape:{exc}"})
                continue
            target_s = str(target)
            if not fs.exists(target_s) or not fs.is_file(target_s):
                errors.append({"query": query_id, "path": rel, "reason": "missing"})
                continue
            try:
                current_hash = _file_sha256(fs, target_s)
            except OSError as exc:
                errors.append({"query": query_id, "path": rel, "reason": f"unreadable:{exc}"})
                continue
            expected = str(meta.get("sha256") or "")
            if expected and current_hash != expected:
                errors.append({"query": query_id, "path": rel, "reason": "stale_hash"})
                continue
            try:
                text = fs.read_text(target_s)
            except (OSError, UnicodeDecodeError) as exc:
                errors.append({"query": query_id, "path": rel, "reason": f"decode:{exc}"})
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if truncated or len(matches) >= max_matches:
                    truncated = True
                    break
                if rx.search(line):
                    matches.append(
                        {
                            "query": query_id,
                            "path": rel,
                            "line": i,
                            "text": line[:240],
                            "sha256": current_hash,
                        }
                    )
    return {
        "matches": matches,
        "errors": errors,
        "coverage": {
            "match_count": len(matches),
            "max_matches": max_matches,
            "truncated": truncated,
            "query_count": len(list(queries)),
        },
    }


def extract_source_spans(
    *,
    fs: Filesystem,
    root: Path,
    manifest: Mapping[str, Any],
    requests: Sequence[Mapping[str, Any]],
    max_lines: int = 80,
) -> dict[str, Any]:
    """Extract exact line spans when path+hash still match the manifest."""
    paths = WorkspacePaths(root)
    by_path = {
        str(row["path"]): row
        for row in (manifest.get("files") or [])
        if isinstance(row, Mapping) and row.get("path")
    }
    excerpts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for req in requests:
        rel = str(req.get("path") or "")
        start = int(req.get("start_line") or 1)
        end = int(req.get("end_line") or start)
        if not rel:
            rejected.append({**dict(req), "reason": "missing_path"})
            continue
        if end < start:
            rejected.append({**dict(req), "reason": "invalid_span"})
            continue
        if end - start + 1 > max_lines:
            rejected.append({**dict(req), "reason": "span_too_large", "max_lines": max_lines})
            continue
        meta = by_path.get(rel)
        if meta is None:
            rejected.append({**dict(req), "reason": "not_in_manifest"})
            continue
        try:
            target = paths.resolve(rel)
        except ValueError as exc:
            rejected.append({**dict(req), "reason": f"escape:{exc}"})
            continue
        target_s = str(target)
        if not fs.exists(target_s):
            rejected.append({**dict(req), "reason": "missing"})
            continue
        try:
            current_hash = _file_sha256(fs, target_s)
            text = fs.read_text(target_s)
        except (OSError, UnicodeDecodeError) as exc:
            rejected.append({**dict(req), "reason": f"unreadable:{exc}"})
            continue
        if current_hash != str(meta.get("sha256") or ""):
            rejected.append({**dict(req), "reason": "stale_hash"})
            continue
        lines = text.splitlines()
        if start < 1 or end > len(lines):
            rejected.append(
                {
                    **dict(req),
                    "reason": "out_of_bounds",
                    "line_count": len(lines),
                }
            )
            continue
        excerpt_lines = lines[start - 1 : end]
        excerpts.append(
            {
                "path": rel,
                "start_line": start,
                "end_line": end,
                "text": "\n".join(excerpt_lines),
                "sha256": current_hash,
            }
        )
    return {"excerpts": excerpts, "rejected": rejected}


def resolve_evidence_refs(
    *,
    proposals: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    manifest: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Accept only refs that exist in the manifest (and optional excerpts)."""
    by_path = {
        str(row["path"]): row
        for row in (manifest.get("files") or [])
        if isinstance(row, Mapping) and row.get("path")
    }
    excerpt_keys = {
        (str(row.get("path")), int(row.get("start_line") or 0), int(row.get("end_line") or 0))
        for row in (excerpts or [])
        if isinstance(row, Mapping)
    }
    if isinstance(proposals, Mapping):
        # Common model shape: {files: [...], hypotheses: [...]}
        items: list[Mapping[str, Any]] = []
        files = proposals.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str):
                    items.append({"path": item})
                elif isinstance(item, Mapping):
                    items.append(item)
        refs = proposals.get("refs")
        if isinstance(refs, list):
            for item in refs:
                if isinstance(item, Mapping):
                    items.append(item)
        if not items and proposals.get("path"):
            items.append(proposals)
    else:
        items = [p for p in proposals if isinstance(p, Mapping)]

    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in items:
        rel = str(item.get("path") or "")
        if not rel or rel not in by_path:
            rejected.append({**dict(item), "reason": "unknown_path"})
            continue
        start = item.get("start_line")
        end = item.get("end_line")
        if start is not None or end is not None:
            key = (rel, int(start or 0), int(end or start or 0))
            if excerpts is not None and key not in excerpt_keys:
                rejected.append({**dict(item), "reason": "unverified_span"})
                continue
        verified.append(
            {
                "path": rel,
                "sha256": by_path[rel].get("sha256"),
                "start_line": start,
                "end_line": end,
            }
        )
    return {
        "verified": verified,
        "rejected": rejected,
        "ok": not rejected,
    }


def measure_discovery_coverage(
    *,
    manifest: Mapping[str, Any],
    search: Mapping[str, Any] | None = None,
    min_files_scanned: int = 1,
) -> dict[str, Any]:
    """Quantify scanned scope / truncation (not model confidence)."""
    files = list(manifest.get("files") or [])
    man_cov = _as_mapping(manifest.get("coverage") or {}, label="manifest.coverage")
    search_cov = _as_mapping((search or {}).get("coverage") or {}, label="search.coverage")
    truncated = bool(man_cov.get("truncated")) or bool(search_cov.get("truncated"))
    file_count = int(man_cov.get("file_count") or len(files))
    match_count = int(search_cov.get("match_count") or 0)
    sufficient = file_count >= min_files_scanned and not truncated
    status = "sufficient" if sufficient else ("inconclusive" if truncated else "insufficient")
    return {
        "status": status,
        "file_count": file_count,
        "match_count": match_count,
        "truncated": truncated,
        "min_files_scanned": min_files_scanned,
        "omissions": list(manifest.get("omissions") or []),
    }


class DiscoveryHardNodeRunner(GraphNodeRunner):
    """Run P0 discovery hard-node kinds with atomic declared bag writes."""

    def __init__(
        self,
        kinds: Sequence[str] | None = None,
        *,
        filesystem: Filesystem | None = None,
        default_workspace: Path | str | None = None,
    ) -> None:
        selected = list(kinds) if kinds is not None else list(DISCOVERY_HARD_KINDS)
        unknown = [k for k in selected if k not in DISCOVERY_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown discovery hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("DiscoveryHardNodeRunner requires at least one kind")
        self._kinds = selected
        self._fs = filesystem if filesystem is not None else RealFilesystem()
        self._default_workspace = (
            Path(default_workspace).expanduser().resolve()
            if default_workspace is not None
            else None
        )

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        payload = node.payload if isinstance(node.payload, Mapping) else {}
        try:
            reads = _payload_section(payload, "reads")
            writes = _payload_section(payload, "writes")
            parameters = _payload_section(payload, "parameters")
            on_error = _payload_section(payload, "on_error")
            result = self._dispatch(
                str(node.kind),
                bag=context.bag,
                reads=reads,
                parameters=parameters,
            )
            dest = writes.get("destination")
            if not isinstance(dest, str) or not dest.strip():
                raise DiscoveryHardNodeError("writes.destination is required")
            batch = context.bag.staged_writes()
            batch.put(dest, result)
            batch.commit()
            return NodeOutcome(status=NodeStatus.SUCCEEDED)
        except (DiscoveryHardNodeError, WalkBagPathError, WalkBagSerializeError) as exc:
            err_dest = (
                on_error.get("destination") if isinstance(on_error, Mapping) else None
            )
            policy = (
                str(on_error.get("policy") or "fail")
                if isinstance(on_error, Mapping)
                else "fail"
            )
            if isinstance(err_dest, str) and err_dest.strip():
                try:
                    batch = context.bag.staged_writes()
                    batch.put(
                        err_dest,
                        {"ok": False, "kind": str(node.kind), "error": str(exc)},
                    )
                    batch.commit()
                except (WalkBagPathError, WalkBagSerializeError, DiscoveryHardNodeError):
                    pass
            if policy == "report":
                return NodeOutcome(status=NodeStatus.SUCCEEDED)
            return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

    def _dispatch(
        self,
        kind: str,
        *,
        bag: WalkBag,
        reads: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> Any:
        if kind == "bag_project":
            source_path = str(reads.get("source") or "")
            if not source_path:
                raise DiscoveryHardNodeError("reads.source is required")
            fields = parameters.get("fields") or []
            if not isinstance(fields, list) or not fields:
                raise DiscoveryHardNodeError("parameters.fields must be a non-empty list")
            rename_raw = parameters.get("rename")
            rename: dict[str, str] = (
                {str(k): str(v) for k, v in rename_raw.items()}
                if isinstance(rename_raw, Mapping)
                else {}
            )
            defaults_raw = parameters.get("defaults")
            defaults: dict[str, Any] = (
                dict(defaults_raw) if isinstance(defaults_raw, Mapping) else {}
            )
            return _project_fields(
                _read_path(bag, source_path),
                fields=[str(f) for f in fields],
                rename=rename,
                defaults=defaults,
            )

        if kind == "bag_validate":
            source_path = str(reads.get("source") or "")
            if not source_path:
                raise DiscoveryHardNodeError("reads.source is required")
            required = parameters.get("required_fields") or []
            if not isinstance(required, list):
                raise DiscoveryHardNodeError("parameters.required_fields must be a list")
            report = _validate_required_fields(
                _read_path(bag, source_path),
                required_fields=[str(f) for f in required],
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "bag_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        if kind == "workspace_manifest":
            workspace_path = str(reads.get("workspace") or "in.workspace")
            root = _resolve_workspace_root(
                _read_path(bag, workspace_path),
                default_workspace=self._default_workspace,
            )
            max_files = int(parameters.get("max_files") or 100)
            excludes = parameters.get("excludes")
            exclude_list = (
                [str(x) for x in excludes] if isinstance(excludes, list) else None
            )
            return build_workspace_manifest(
                fs=self._fs,
                root=root,
                max_files=max_files,
                excludes=exclude_list,
            )

        if kind == "file_search":
            workspace_path = str(reads.get("workspace") or "in.workspace")
            manifest_path = str(reads.get("manifest") or "acc.discovery.manifest")
            queries_path = str(reads.get("queries") or "ask.search_queries")
            root = _resolve_workspace_root(
                _read_path(bag, workspace_path),
                default_workspace=self._default_workspace,
            )
            manifest = _as_mapping(_read_path(bag, manifest_path), label="manifest")
            queries_raw = _read_path(bag, queries_path)
            if isinstance(queries_raw, list):
                queries: Sequence[Any] = queries_raw
            elif isinstance(queries_raw, Mapping):
                nested = queries_raw.get("queries")
                queries = nested if isinstance(nested, list) else [queries_raw]
            else:
                raise DiscoveryHardNodeError("search queries must be a list or mapping")
            return search_manifest_files(
                fs=self._fs,
                root=root,
                manifest=manifest,
                queries=queries,
                max_matches=int(parameters.get("max_matches") or 50),
            )

        if kind == "source_extract":
            workspace_path = str(reads.get("workspace") or "in.workspace")
            manifest_path = str(reads.get("manifest") or "acc.discovery.manifest")
            requests_path = str(reads.get("requests") or "ask.source_requests")
            root = _resolve_workspace_root(
                _read_path(bag, workspace_path),
                default_workspace=self._default_workspace,
            )
            manifest = _as_mapping(_read_path(bag, manifest_path), label="manifest")
            requests_raw = _read_path(bag, requests_path)
            if not isinstance(requests_raw, list):
                raise DiscoveryHardNodeError("source requests must be a list")
            return extract_source_spans(
                fs=self._fs,
                root=root,
                manifest=manifest,
                requests=[r for r in requests_raw if isinstance(r, Mapping)],
                max_lines=int(parameters.get("max_lines") or 80),
            )

        if kind == "evidence_resolve":
            proposals_path = str(reads.get("proposals") or "out.discovery")
            manifest_path = str(reads.get("manifest") or "acc.discovery.manifest")
            excerpts_path = reads.get("excerpts")
            manifest = _as_mapping(_read_path(bag, manifest_path), label="manifest")
            proposals = _read_path(bag, proposals_path)
            excerpts = None
            if isinstance(excerpts_path, str) and excerpts_path.strip():
                excerpts_raw = _read_path(bag, excerpts_path, required=False)
                if isinstance(excerpts_raw, Mapping):
                    excerpts = list(excerpts_raw.get("excerpts") or [])
                elif isinstance(excerpts_raw, list):
                    excerpts = excerpts_raw
            if not isinstance(proposals, (Mapping, list)):
                raise DiscoveryHardNodeError("proposals must be a mapping or list")
            return resolve_evidence_refs(
                proposals=proposals,
                manifest=manifest,
                excerpts=excerpts,
            )

        if kind == "coverage_measure":
            manifest_path = str(reads.get("manifest") or "acc.discovery.manifest")
            search_path = reads.get("search")
            manifest = _as_mapping(_read_path(bag, manifest_path), label="manifest")
            search = None
            if isinstance(search_path, str) and search_path.strip():
                search_raw = _read_path(bag, search_path, required=False)
                if isinstance(search_raw, Mapping):
                    search = search_raw
            return measure_discovery_coverage(
                manifest=manifest,
                search=search,
                min_files_scanned=int(parameters.get("min_files_scanned") or 1),
            )

        raise DiscoveryHardNodeError(f"unsupported hard-node kind {kind!r}")


__all__ = [
    "DISCOVERY_HARD_KINDS",
    "DiscoveryHardNodeError",
    "DiscoveryHardNodeRunner",
    "build_workspace_manifest",
    "extract_source_spans",
    "measure_discovery_coverage",
    "resolve_evidence_refs",
    "search_manifest_files",
]
