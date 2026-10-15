"""What ``cadgen.manufacturing.check`` does, end to end: :func:`check_part`.

The study names its process (``"process": "casting"``), an analysis of fea's protocol held in :mod:`.processes`. The run
reads the study with it (fea's parser, the process named by ``process`` where an fea study names its ``analysis``),
removes what an earlier check of the same process left beside the part, and hands the parsed study to fea's pipeline
(:func:`cadgen._internal.fea.run.solve_study`): the mesh, the fit-the-budget ladder, the solve, and the GLB and its
sidecar, ``<stem>.<process>.glb`` and ``<stem>.<process>.result.json`` beside the part (the study itself is
``<stem>.<process>.json`` there, as a CAM job is ``<stem>.cam.json``, so the result never takes its name). What it
returns is the process's
findings, held to its closed set (:func:`cadgen._internal.manufacturing.processes.base.closed`), their verdict, and the
gate ``fail_on`` sets (:mod:`cadgen._internal.checklist`).

A check that cannot run raises in a sentence naming what to change and leaves no result beside the part, never the last
check's "Ready".
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import ManufacturingCheckResult

__all__ = ["check_part", "process_of", "read_study"]


def process_of(document: dict):
    """The process a study names (its ``process``); a ValueError naming the key when it names none, another, or an
    ``analysis`` (``cadgen fea solve``'s)."""
    from cadgen._internal.manufacturing.processes import PROCESS_NAMES, get_process

    if "analysis" in document:
        raise ValueError(f"study.analysis: a manufacturing study names its process with \"process\", one of "
                         f"{', '.join(PROCESS_NAMES)}; an analysis is `cadgen fea solve`'s")
    if "process" not in document:
        raise ValueError(f"study.process: the process to check, one of {', '.join(PROCESS_NAMES)}")
    return get_process(document["process"])


def _study_path(study) -> Path | None:
    """The file a study was read from, resolved; ``None`` for a dict or inline JSON."""
    if isinstance(study, Path) or (isinstance(study, str) and not study.strip().startswith("{")):
        return Path(study).expanduser().resolve()
    return None


def read_study(study):
    """The study (a path, inline JSON or a dict) parsed with the process it names: fea's :class:`Study`, whose
    ``analysis_object`` is the process. Stdlib only."""
    from cadgen._internal.fea.study import load_document, parse_study

    source = load_document(study)
    return parse_study(source, analysis=process_of(source), named_by="process")


def check_part(target: Path, *, study, occurrence: str | None = None, mesh_size: float | None = None,
               fail_on: str | None = None, verbose: bool = False) -> ManufacturingCheckResult:
    from cadgen._internal.checklist import fail_on_value, gate_failed
    from cadgen._internal.fea.study import load_document, parse_study
    from cadgen._internal.manufacturing.processes.base import closed

    fail_on_value(fail_on)
    document = Path(target)
    if study is None:
        raise ValueError("a study is required: --study part.<process>.json (or inline JSON) naming the process and "
                         "what it reads; run `cadgen fea faces IN.step` to list face refs")
    source = load_document(study)
    process = process_of(source)
    glb = document.with_name(f"{document.stem}.{process.name}.glb")
    sidecar = document.with_name(f"{document.stem}.{process.name}.result.json")
    written = (glb, sidecar)
    named = _study_path(study)
    if named is not None and any(named == path.resolve() for path in written):
        raise ValueError(f"study: {named.name} is where the check writes its result; name the study "
                         f"{document.stem}.{process.name}.json")
    for stale in written:
        stale.unlink(missing_ok=True)
    parsed = parse_study(source, analysis=process, named_by="process")  # stdlib, before any heavy import

    from cadgen._internal.fea.run import solve_study

    solved = solve_study(document, glb, study=parsed, occurrence=occurrence, mesh_size=mesh_size, verbose=verbose,
                         sidecar=sidecar)
    if not solved.ok:  # only an assembly stops before its solve, and a process solves one part
        raise ValueError(f"{process.name}: {document.name} holds several parts and a {process.name} check solves one: "
                         "name it with --occurrence")
    try:
        closed(process.name, solved.findings)
    except ValueError:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return ManufacturingCheckResult(
        ok=True, document=document, occurrence=solved.occurrence, process=process.name, glb=solved.glb,
        sidecar=solved.sidecar, summary=solved.summary, verdict=solved.verdict, findings=solved.findings,
        gate_failed=gate_failed(solved.verdict, fail_on), fail_on=fail_on, fit=solved.fit,
        limits=tuple(process.limits), mesh=solved.mesh, timings=solved.timings, warnings=solved.warnings,
    )
