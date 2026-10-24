"""Read-only viewer exports of a specified document, never a source build.

Only the worker imports this module's geometry helpers. The HTTP job declares one
output in managed temporary storage; capabilities inspect geometry without writing.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def fingerprint(structure: dict) -> str:
    """Content identity of a live document, independent of its served address/version."""
    fields = ("name", "units", "prototypes", "instances", "tree", "kinematics", "pmi")
    return hashlib.sha256(json.dumps({k: structure.get(k) for k in fields},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check(source, expected: dict) -> None:
    from cadgen.engine.export import ExportRefused

    if "digest" in expected:
        matches = fingerprint(source.structure) == expected["digest"]
    else:
        path = source.path
        stat = path.stat() if path else None
        matches = (stat is not None and f"{stat.st_mtime_ns}-{stat.st_size}" == expected.get("version")
                   and source.structure.get("version") == expected.get("version"))
    if not matches:
        raise ExportRefused("The source changed. Open Export again to use the displayed revision.")


def options(source, *, pose=None, part=None, original_allowed=True) -> list[dict]:
    from cadgen.engine import pmi
    from cadgen.engine.export import ExportRefused
    from cadgen.engine.export.dxf import dxf_bytes

    view = source.view(pose=pose, part=part)
    rows = [{"format": kind, "label": label, "extension": extension, "reason": None}
            for kind, label, extension in (("step", "STEP (AP242)", ".step"), ("glb", "GLB", ".glb"),
                                           ("stl", "STL", ".stl"), ("threemf", "3MF", ".3mf"),
                                           ("dxf", "DXF", ".dxf"), ("xbf", "XBF", ".xbf"))]
    for row in rows:
        if row["format"] == "step":
            # Whether the STEP carries PMI: its GD&T, a note being the xbf's alone; and what the
            # document holds that stays in it, which the panel says (a notes library is notes too).
            entries = source.structure.get("pmi") or []
            row["pmi"] = bool(pmi.step_entries(entries))
            notes = any(entry.get("kind") == "note" for entry in entries) or bool(source.structure.get("pmi_library"))
            row["kept"] = [kind for kind, held in (("notes", notes), ("views", bool(source.structure.get("pmi_views"))))
                           if held]
            try:
                pmi.refuse_dropped(view, "step")
            except ExportRefused as error:
                row["reason"] = str(error)
        if row["format"] == "dxf":
            try:
                dxf_bytes(view)
            except ExportRefused as error:
                row["reason"] = str(error)
        if row["format"] == "xbf":
            # Whether the PMI decided this row: only an XBF made again, a part extracted or a
            # document converted, is one, and its views and notes library are the PMI's too.
            row["pmi"] = False
            if pose is not None:
                row["reason"] = "XBF stores the authored document, not a requested pose."
            elif source.path and source.path.suffix.lower() == ".xbf" and part is None and not source.foreign:
                row["reason"] = "Use Download original XBF, or select a part to extract."
            else:
                row["pmi"] = any(source.structure.get(key) for key in ("pmi", "pmi_views", "pmi_library"))
                try:
                    pmi.refuse_dropped(view, "xbf")
                except ExportRefused as error:
                    row["reason"] = str(error)
    if original_allowed and source.path and source.path.suffix.lower() == ".xbf" and part is None and pose is None:
        rows.append({"format": "original", "label": "Download original XBF", "extension": ".xbf", "reason": None})
    return rows


def original(source, target: Path, expected: dict) -> int:
    from cadgen.engine.export import ExportRefused

    if "version" not in expected or source.path is None or source.path.suffix.lower() != ".xbf":
        raise ExportRefused("Only an existing XBF has original XBF bytes to download.")
    check(source, expected)
    try:
        shutil.copyfile(source.path, target)
        check(source, expected)
        return target.stat().st_size
    except BaseException:
        target.unlink(missing_ok=True)
        raise
