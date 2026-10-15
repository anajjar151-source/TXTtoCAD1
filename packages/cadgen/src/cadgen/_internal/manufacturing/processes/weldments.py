"""The base metals and welding processes a ``welding`` study names, and the shrinkage relations its welds follow.

A weld leaves the metal beside it shorter than it was: a weld's inherent strain (:mod:`.inherent_strain`). Its
size comes from the heat put in per mm of weld, Q (J/mm, the net heat input: EN 1011-1's arc energy times the process's
thermal efficiency), through the classical relations, each for steel and scaled to another metal by its own
expansion over its heat capacity, α / (c ρ), which they are in proportion to (Okerblom):

- **Longitudinal**: the tendon force F_T = 0.2 kN per J/mm of Q (White et al.; Nakatani), the force the yielded zone
  beside the weld pulls with; scaled by E α / (c ρ). It acts over the zone it yields, of area F_T / σ_y, whose
  inherent strain along the weld is then -σ_y / E.
- **Transverse and angular**: Satoh and Terasaki's relations in the heat input parameter Q / h² (J/mm³) for a plate
  h thick (as Nakatani gives them): the transverse shrinkage S and the angular distortion θ of a 200 mm weld. A plate
  barely heated through turns most; one heated through shrinks evenly and turns less (θ peaks near Q / h² = 10.6).
  A fillet weld's heat is shared between the plate it lies on, conducting it both ways, and the one that meets it:
  2 h_F / (2 h_F + h_W) of it to the first (Nakatani's eq. 3).

Units: MPa, 1/K, W/(m K), J/(kg K), kg/m³, mm, J/mm (kJ/mm in a study). Sources per value: the manufacturing-sim
skill's welding reference. Stdlib only, and :func:`thickness_along` and :func:`outward_normal` import numpy inside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cadgen._internal.fea.analyses.kinds import json_text

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "METALS", "PROCESSES", "BaseMetal", "WeldProcess", "angular_200", "heat_shares", "lookup_metal", "lookup_process",
    "angle_words", "outward_normal", "tendon_force_N", "thickness_along", "transverse_200",
]


@dataclass(frozen=True)
class BaseMetal:
    key: str
    name: str
    #: Young's modulus and yield strength, MPa; Poisson's ratio.
    E: float
    nu: float
    yield_strength: float
    #: Expansion, 1/K; conductivity, W/(m K); specific heat, J/(kg K); density, kg/m³.
    expansion: float
    conductivity: float
    specific_heat: float
    density: float

    @property
    def heat_capacity(self) -> float:
        """c ρ, J/(mm³ K)."""
        return self.specific_heat * self.density * 1e-9

    @property
    def shrink(self) -> float:
        """α / (c ρ), mm³/J: how much a joule of heat swells the metal it is in."""
        return self.expansion / self.heat_capacity

    def as_dict(self) -> dict:
        return {"name": self.name, "youngs_GPa": round(self.E / 1000.0, 6), "poisson": self.nu,
                "yield_MPa": self.yield_strength, "expansion_per_K": self.expansion,
                "conductivity_W_mK": self.conductivity, "specific_heat_J_kgK": self.specific_heat,
                "density_kg_m3": self.density}


# Sources per value: the manufacturing-sim skill's welding reference ("The base metals").
METALS: dict[str, BaseMetal] = {metal.key: metal for metal in (
    BaseMetal("s235", "Structural steel S235", 210_000, 0.3, 235, 12e-6, 53.3, 440, 7850),
    BaseMetal("a36", "Structural steel A36", 200_000, 0.26, 250, 11.7e-6, 51.9, 486, 7850),
    BaseMetal("s355", "Structural steel S355", 210_000, 0.3, 355, 12e-6, 53.3, 440, 7850),
    BaseMetal("304", "Stainless steel 304", 193_000, 0.29, 215, 17.3e-6, 16.2, 500, 8000),
    BaseMetal("6061-t6", "Aluminium 6061-T6", 68_900, 0.33, 276, 23.6e-6, 167, 896, 2700),
)}
#: The relations' own metal: the steel their coefficients were measured on.
REFERENCE = METALS["s235"]

_METAL_ALIASES = {
    "s235jr": "s235", "mild-steel": "s235", "steel": "s235", "astm-a36": "a36", "s355jr": "s355", "s355j2": "s355",
    "stainless": "304", "stainless-304": "304", "ss304": "304", "6061": "6061-t6", "aluminium": "6061-t6",
    "aluminum": "6061-t6", "6061t6": "6061-t6", "aluminum-6061-t6": "6061-t6",
}


@dataclass(frozen=True)
class WeldProcess:
    key: str
    words: str
    #: The thermal efficiency k: the share of the arc's (or the beam's) energy that goes into the work.
    efficiency: float
    #: How its energy is given besides a heat input: "arc" (volts, amps) or "beam" (power).
    source: str = "arc"


PROCESSES: dict[str, WeldProcess] = {process.key: process for process in (
    WeldProcess("gmaw", "gas metal arc (MIG/MAG)", 0.8),
    WeldProcess("gtaw", "gas tungsten arc (TIG)", 0.6),
    WeldProcess("smaw", "manual metal arc (stick)", 0.8),
    WeldProcess("laser", "laser beam", 0.7, source="beam"),
)}
_PROCESS_ALIASES = {"mig": "gmaw", "mag": "gmaw", "tig": "gtaw", "stick": "smaw", "mma": "smaw", "lbw": "laser"}


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").split())


def lookup_metal(name) -> BaseMetal:
    """A base metal by its table name or an alias; a ValueError naming ``alloy`` and listing the table otherwise."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"alloy: name the base metal, one of {', '.join(METALS)}; got {json_text(name)}")
    key = _key(name)
    key = _METAL_ALIASES.get(key, key)
    if key not in METALS:
        raise ValueError(f"alloy: {name!r} is not a base metal cadgen knows for welding; use one of {', '.join(METALS)}")
    return METALS[key]


def lookup_process(name, where: str) -> WeldProcess:
    """A welding process by name; a ValueError at ``where`` listing them otherwise."""
    key = _key(name).replace("-", "_") if isinstance(name, str) else None
    key = _PROCESS_ALIASES.get(key, key)
    if key not in PROCESSES:
        raise ValueError(f"{where}: {json_text(name)} is not a welding process cadgen knows; use one of "
                         f"{', '.join(PROCESSES)} (mig, tig and stick name the first three)")
    return PROCESSES[key]


# -- the relations -------------------------------------------------------------------------------------


def tendon_force_N(metal: BaseMetal, heat_J_mm: float) -> float:
    """The longitudinal shrinkage force of a weld of net heat input ``heat_J_mm``, N: 0.2 kN per J/mm for steel,
    scaled by E α / (c ρ)."""
    scale = (metal.E * metal.shrink) / (REFERENCE.E * REFERENCE.shrink)
    return 200.0 * heat_J_mm * scale


def _parameter(metal: BaseMetal, heat_J_mm: float, thickness_mm: float) -> float:
    """Q / h², J/mm³, as steel would take it: the heat scaled by the metal's α / (c ρ) over steel's."""
    return heat_J_mm * metal.shrink / REFERENCE.shrink / thickness_mm ** 2


def angular_200(metal: BaseMetal, heat_J_mm: float, thickness_mm: float) -> float:
    """Satoh and Terasaki's angular distortion of a 200 mm weld on a plate ``thickness_mm`` thick, radians:
    1.44e-3 Q/h² up to Q/h² = 6.27, then 0.1061 (Q/h²) / ((Q/h² - 6.16)² + 73.6)."""
    x = _parameter(metal, heat_J_mm, thickness_mm)
    if x <= 6.27:
        return 1.44e-3 * x
    return 0.1061 * x / ((x - 6.16) ** 2 + 73.6)


def transverse_200(metal: BaseMetal, heat_J_mm: float, thickness_mm: float, *, fillet: bool) -> float:
    """The transverse shrinkage across a 200 mm weld, mm. A fillet's (Satoh and Terasaki): 1.16e-3 Q/h up to
    Q/h² = 6.27, [1.44e-4 ((Q/h²)² - Q/h²) + 0.0025] h up to 20, then 2.85e-3 Q/h. A butt weld's: 2.85e-3 Q/h."""
    x = _parameter(metal, heat_J_mm, thickness_mm)
    h = thickness_mm
    if not fillet or x > 20.0:
        return 2.85e-3 * x * h
    if x <= 6.27:
        return 1.16e-3 * x * h
    return (1.44e-4 * (x * x - x) + 0.0025) * h


def heat_shares(thicknesses: list[float]) -> list[float]:
    """How a weld's heat divides between the plates it joins: all of it to one plate; for two (the plate it lies on,
    then the one that meets it) 2 h_F / (2 h_F + h_W) to the first and the rest to the second."""
    if len(thicknesses) == 1:
        return [1.0]
    flange, web = thicknesses[0], thicknesses[1]
    first = 2.0 * flange / (2.0 * flange + web)
    return [first, 1.0 - first]


# -- the geometry on the mesh --------------------------------------------------------------------------


def outward_normal(space, rows: "np.ndarray") -> "np.ndarray":
    """The area-weighted outward unit normal of the boundary triangles ``rows``: each oriented away from the corner of
    its element that is not on it."""
    import numpy as np

    points = space.dof_locations
    triangles = np.asarray(space.boundary_quadratic)[rows][:, :3]
    corners = points[triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    facets = space.facets_of_rows(rows)
    elements = space.mesh.f2t[0, facets]
    inner = space.mesh.t[:, elements].T                                # (rows, 4)
    opposite = np.array([[v for v in tet if v not in tri][0] for tet, tri in zip(inner, triangles)])
    inward = points[opposite] - corners[:, 0]
    sign = np.where((normals * inward).sum(axis=1) > 0, -1.0, 1.0)
    total = (normals * sign[:, None]).sum(axis=0)
    return total / max(float(np.linalg.norm(total)), 1e-300)


def thickness_along(space, starts: "np.ndarray", direction: "np.ndarray") -> float | None:
    """The median distance from each of ``starts`` (points on the boundary) along ``direction`` (into the part) to
    the boundary on the far side: a plate's thickness. ``None`` when no ray finds a far side."""
    import numpy as np

    points = space.dof_locations
    triangles = points[np.asarray(space.boundary_quadratic)[:, :3]]
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    e1, e2 = b - a, c - a
    d = np.asarray(direction, dtype=float)
    p = np.cross(d, e2)
    det = (e1 * p).sum(axis=1)
    usable = np.abs(det) > 1e-12
    hits = []
    for origin in np.asarray(starts, dtype=float):
        s = origin - a
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (s * p).sum(axis=1) / det
            q = np.cross(s, e1)
            v = (q @ d) / det
            t = (q * e2).sum(axis=1) / det
            ok = usable & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-6)
        if ok.any():
            hits.append(float(t[ok].min()))
    return float(np.median(hits)) if hits else None


def angle_words(radians: float) -> str:
    return f"{math.degrees(radians):.2g}°"
