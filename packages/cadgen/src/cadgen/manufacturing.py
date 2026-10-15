"""The public ``manufacturing`` namespace: what happens to a part while it is made, checked as CI checks code.

One verb, mirrored by a generated CLI (``cadgen manufacturing check``; README law 6): ``check`` reads a study that
names its process (casting, molding, heat_treatment, machining, printing, welding or sheet_metal), simulates the part
being made on fea's mesh and solvers, and writes ``<stem>.<process>.glb`` (what the viewer draws, coloured by what
the process judges) and its sidecar ``<stem>.<process>.result.json`` beside the part, where the study is
``<stem>.<process>.json``. Its findings read as a CI check: each says what it
measured against its limit and the fix that makes it pass, and the verdict is ready or fix; ``fail_on`` makes a
failing verdict exit 3 from the CLI.

There is no decorator: a check is about a document (the saved STEP), and CLIs take documents only (law 7). A check
that cannot run writes nothing.

``check`` requires the ``fea`` extra (``pip install 'cadgen[fea]'``). Import discipline: nothing here may pull in OCP,
build123d or the solver stack at module scope (see :mod:`cadgen.step`) -- ``--help`` must stay cheap. The verb imports
the engine (:mod:`cadgen._internal.manufacturing.run`) inside its body.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import ManufacturingCheckResult

__all__ = ["check"]


def check(target: Path, *, study: str | dict | None = None, occurrence: str | None = None,
          mesh_size: float | None = None, fail_on: str | None = None, verbose: bool = False) -> ManufacturingCheckResult:
    """Check how a part fares while it is made: simulate its process, judge it, and write the result GLB and sidecar.

    target: the STEP/STP document holding the part.
    study: the study: a JSON file path, inline JSON, or (library callers) a dict. Its "process" names what is checked
        (casting, molding, heat_treatment, machining, printing, welding or sheet_metal), and the rest is that process's
        own keys (an alloy and its mould, a resin, a steel and its quenchant, the cut, the printer, the welds, the
        sheet); see the manufacturing-sim skill for each. Face refs are the ones ``cadgen fea faces`` prints. Writes
        ``<stem>.<process>.glb`` and its sidecar ``<stem>.<process>.result.json`` beside the document, replacing an
        earlier check's.
    occurrence: check only this part occurrence (``#o1.2``) when the document holds several parts; a process checks
        one part.
    mesh_size: target element size in mm, overriding the study's mesh.size_mm. Omitted, the study's, else one
        picked from the part.
    fail_on: the severity that fails the check, as CI fails a build: ``error`` (any error) or ``warning`` (any error
        or warning). A check that ran and failed it exits 3 from the CLI; omitted, it exits 0 whatever it found.
    verbose: show every progress line and the timings on stderr. Without it, a check that runs long still says how
        far it has got on stderr, about every 10 s.
    """
    from cadgen._internal.manufacturing.run import check_part

    return check_part(Path(target), study=study, occurrence=occurrence, mesh_size=mesh_size, fail_on=fail_on,
                      verbose=verbose)
