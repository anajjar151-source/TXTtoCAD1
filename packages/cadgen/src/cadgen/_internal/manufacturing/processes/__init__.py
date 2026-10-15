"""Every process ``cadgen manufacturing check`` knows, by name.

The registry is written once, here: each entry names its module (``processes/<name>.py``) and class (a
:class:`~cadgen._internal.manufacturing.processes.base.Process`), its plain word and whether it is ``lite`` (a
simulation with stated limits) or an ``estimate`` (hand formulas on the part). The class repeats ``name`` and ``word``;
a test keeps the two, the skill's router and its checks page in step. The modules beside the processes (``foundry``,
``solidification``, ``resins``, ``warp``, ``hardening``, ``quench``, ``cutting``, ``inherent_strain``, ``additive``,
``weldments``, ``brake``, ``bends``) are their physics, never a process of their own.

Stdlib only: the modules import lazily, so ``PROCESS_NAMES`` costs nothing (fea's registry reads it to refuse a process
named as an analysis).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cadgen._internal.manufacturing.processes.base import Process

__all__ = ["Entry", "PROCESS_NAMES", "REGISTRY", "get_process"]

_PACKAGE = "cadgen._internal.manufacturing.processes"


@dataclass(frozen=True)
class Entry:
    name: str
    module: str          # "cadgen._internal.manufacturing.processes.casting"
    cls: str             # "CastingProcess"
    word: str            # "Casting"
    status: str          # "lite" | "estimate"


def _entry(name: str, cls: str, word: str, status: str = "lite") -> Entry:
    return Entry(name, f"{_PACKAGE}.{name}", cls, word, status)


REGISTRY: dict[str, Entry] = {entry.name: entry for entry in (
    # A casting freezing in its mould, pour to solid: hot spots, feeding, Niyama, misruns.
    _entry("casting", "CastingProcess", "Casting"),
    # A plastic part cooling in its injection mould from the melt to ejection, and how it warps.
    _entry("molding", "MoldingProcess", "Injection molding"),
    # A steel part quench hardened: its cooling, its hardness through the Jominy curve, the quench's stress.
    _entry("heat_treatment", "HeatTreatmentProcess", "Heat treatment"),
    # CNC milling or turning: the part's deflection under the cut, and whether the cut chatters (stability lobes).
    _entry("machining", "MachiningProcess", "Machining"),
    # A part 3D printed band by band, each band's inherent strain shrinking it on the part below: warp and stress.
    _entry("printing", "PrintingProcess", "3D printing"),
    # Welds shrinking the part they join, by the inherent strain of their zones: angular distortion, bowing, stress.
    _entry("welding", "WeldingProcess", "Welding"),
    # A bent sheet off the press brake, per bend by hand formulas: springback, cracking, the flat pattern.
    _entry("sheet_metal", "SheetMetalProcess", "Sheet metal", "estimate"),
)}
PROCESS_NAMES: tuple[str, ...] = tuple(REGISTRY)

_INSTANCES: dict[str, "Process"] = {}


def get_process(name) -> "Process":
    """The process's instance. A name that is not one: a ValueError listing :data:`PROCESS_NAMES`, or saying that an
    analysis is ``cadgen fea solve``'s."""
    if isinstance(name, str) and name in _INSTANCES:
        return _INSTANCES[name]
    entry = REGISTRY.get(name) if isinstance(name, str) else None
    if entry is None:
        from cadgen._internal.fea.analyses import ANALYSIS_NAMES  # stdlib only
        from cadgen._internal.fea.analyses.kinds import json_text

        if name in ANALYSIS_NAMES:
            raise ValueError(f"process: {name!r} is an analysis, not a manufacturing process: solve it with "
                             f"`cadgen fea solve part.step --study study.json`, the study naming \"analysis\": \"{name}\"")
        raise ValueError(f"process: {json_text(name)} is not a process cadgen checks; use one of "
                         f"{', '.join(PROCESS_NAMES)}")
    instance = getattr(importlib.import_module(entry.module), entry.cls)()
    _INSTANCES[name] = instance
    return instance
