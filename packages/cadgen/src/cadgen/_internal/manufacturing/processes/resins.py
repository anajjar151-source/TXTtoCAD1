"""The resins a ``molding`` study names, and the moulder's hand formulas.

A resin is what a moulding's cooling and its warp need: density, conductivity and specific heat (handbook values at
room temperature, held constant through the run), the melt and mould temperature windows of a processing guide (a
study's defaults are the middle of each), the temperature it is ejected at, and, for a semi-crystalline resin, the
range it crystallises over on cooling and the heat that releases (none for an amorphous resin); then its mould
shrinkage range and the wall thicknesses design guides recommend for it. Units are the ones people write them in
(kg/m³ is converted to the engine's tonne/mm³ here; W/(m K), J/(kg K), J/kg, °C, %, mm). The sources of every value are
listed in the manufacturing-sim skill's molding reference.

:func:`plate_cooling` is the plate's cooling time by hand (the handbook formula, and its form for a mould contact of
finite h), :func:`linear_shrinkage` the share a point shrinks by how long it stayed hot. Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.fea.analyses.kinds import json_text

__all__ = [
    "RESINS", "Resin", "SolvedResin", "diffusivity", "linear_shrinkage", "lookup_resin", "plate_cooling",
]


@dataclass(frozen=True)
class Resin:
    key: str
    name: str
    #: tonne/mm³ (the engine's).
    density: float
    #: W/(m K): numerically the engine's mW/(mm K).
    conductivity: float
    #: J/(kg K), one value through the run.
    specific_heat: float
    #: The processing guide's windows, °C.
    melt_range: tuple[float, float]
    mold_range: tuple[float, float]
    #: The part is stiff enough to eject below this, °C.
    eject_C: float
    #: A semi-crystalline resin's crystallisation on cooling, (end, onset) °C; ``None`` for an amorphous one.
    crystallises: tuple[float, float] | None
    #: The heat its crystallisation releases, J/kg (0 for an amorphous resin).
    latent_heat: float
    #: The mould shrinkage range, % (linear).
    shrinkage: tuple[float, float]
    #: The wall thicknesses a design guide recommends, mm.
    wall_mm: tuple[float, float]

    @property
    def melt_C(self) -> float:
        return 0.5 * (self.melt_range[0] + self.melt_range[1])

    @property
    def mold_C(self) -> float:
        return 0.5 * (self.mold_range[0] + self.mold_range[1])

    @property
    def semi_crystalline(self) -> bool:
        return self.crystallises is not None

    def solved(self, melt_C: float, eject_C: float) -> "SolvedResin":
        """What the enthalpy march reads: an amorphous resin has no latent heat, and its "freezing range" is spread
        from the ejection temperature to the melt so the march's steps follow the whole cooling."""
        solidus, liquidus = self.crystallises if self.crystallises is not None else (eject_C, melt_C)
        return SolvedResin(self.name, self.density, self.conductivity, self.specific_heat, self.latent_heat,
                           solidus, liquidus)

    def as_dict(self) -> dict:
        return {"name": self.name, "density_kg_m3": round(self.density * 1e12, 3),
                "conductivity_W_mK": self.conductivity, "specific_heat_J_kgK": self.specific_heat,
                "melt_range_C": list(self.melt_range), "mold_range_C": list(self.mold_range),
                "ejection_temperature_C": self.eject_C,
                "crystallises_C": list(self.crystallises) if self.crystallises else None,
                "latent_heat_kJ_kg": round(self.latent_heat / 1000.0, 3), "shrinkage_percent": list(self.shrinkage),
                "wall_mm": list(self.wall_mm)}


@dataclass(frozen=True)
class SolvedResin:
    """A resin as :func:`cadgen._internal.manufacturing.processes.solidification.march` reads an alloy."""

    name: str
    density: float
    conductivity: float
    specific_heat: float
    latent_heat: float
    solidus: float
    liquidus: float
    pure: bool = False

    @property
    def freezing(self) -> tuple[float, float]:
        return self.solidus, self.liquidus


def _resin(key, name, kg_m3, k, c, melt, mold, eject, crystallises, kj_kg, shrinkage, wall) -> Resin:
    return Resin(key, name, kg_m3 * 1e-12, k, c, melt, mold, eject, crystallises, kj_kg * 1000.0, shrinkage, wall)


# Sources per value: the manufacturing-sim skill's molding reference ("The resins").
RESINS: dict[str, Resin] = {resin.key: resin for resin in (
    _resin("abs", "ABS", 1050, 0.17, 1400, (210, 241), (38, 71), 86, None, 0, (0.4, 0.7), (1.14, 3.56)),
    _resin("pc", "Polycarbonate (PC)", 1200, 0.20, 1200, (260, 310), (66, 121), 128, None, 0, (0.5, 0.7), (1.02, 3.81)),
    _resin("pc-abs", "PC/ABS", 1150, 0.19, 1300, (229, 260), (49, 71), 104, None, 0, (0.4, 0.6), (1.14, 3.56)),
    _resin("pp", "Polypropylene (PP)", 904, 0.16, 1800, (204, 232), (16, 49), 111, (100, 125), 93, (1.7, 2.2),
           (0.89, 3.81)),
    _resin("hdpe", "HDPE", 955, 0.48, 1900, (193, 232), (21, 66), 80, (105, 120), 190, (1.5, 2.5), (0.76, 5.08)),
    _resin("pa6", "Nylon 6 (PA6)", 1130, 0.26, 1700, (238, 277), (49, 82), 145, (175, 195), 69, (1.0, 1.4), (0.76, 2.92)),
    _resin("pa66", "Nylon 66 (PA66)", 1140, 0.25, 1670, (285, 302), (66, 96), 180, (220, 240), 75, (1.7, 2.2),
           (0.76, 2.92)),
    _resin("pa66-gf30", "Nylon 66, 30 % glass (PA66-GF30)", 1360, 0.23, 1410, (280, 300), (80, 90), 195, (220, 240), 52,
           (0.4, 0.9), (0.76, 2.92)),
    _resin("pom", "Acetal (POM)", 1410, 0.27, 1500, (188, 210), (60, 82), 110, (140, 155), 160, (1.8, 2.2), (0.76, 3.05)),
    _resin("pbt", "PBT", 1300, 0.21, 1300, (249, 271), (60, 100), 170, (180, 200), 50, (1.7, 2.0), (0.64, 3.18)),
    _resin("pmma", "Acrylic (PMMA)", 1180, 0.18, 1450, (182, 271), (49, 104), 94, None, 0, (0.2, 0.6), (0.64, 12.7)),
    _resin("tpu", "TPU", 1175, 0.26, 1800, (188, 210), (21, 71), 70, None, 0, (0.8, 2.5), (2.03, 19.05)),
)}

_ALIASES = {
    "acrylonitrile-butadiene-styrene": "abs", "polycarbonate": "pc", "pc-abs": "pc-abs", "pcabs": "pc-abs",
    "abs-pc": "pc-abs", "polypropylene": "pp", "pe-hd": "hdpe", "polyethylene": "hdpe", "high-density-polyethylene": "hdpe",
    "nylon-6": "pa6", "nylon6": "pa6", "pa-6": "pa6", "nylon-66": "pa66", "nylon66": "pa66", "nylon-6-6": "pa66",
    "pa-66": "pa66", "pa6.6": "pa66", "nylon": "pa66", "pa66gf30": "pa66-gf30", "pa66-gf": "pa66-gf30",
    "glass-filled-nylon": "pa66-gf30", "acetal": "pom", "delrin": "pom", "polyacetal": "pom",
    "polybutylene-terephthalate": "pbt", "acrylic": "pmma", "plexiglas": "pmma", "thermoplastic-polyurethane": "tpu",
}


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").replace("/", " ").split())


def lookup_resin(name) -> Resin:
    """A resin by its table name or an alias; a ValueError naming ``resin`` and listing the table otherwise."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"resin: name the resin, one of {', '.join(RESINS)}; got {json_text(name)}")
    key = _key(name)
    key = _ALIASES.get(key, key)
    if key not in RESINS:
        raise ValueError(f"resin: {name!r} is not a resin cadgen knows; use one of {', '.join(RESINS)}")
    return RESINS[key]


def diffusivity(resin, *, latent: float = 0.0, span_C: float = 0.0) -> float:
    """The resin's thermal diffusivity k / (ρ c), mm²/s; with ``latent`` J/kg released over ``span_C`` degrees of the
    cooling, the apparent one, its heat capacity raised by latent / span (the moulder's way to fold crystallisation in)."""
    c = resin.specific_heat + (latent / span_C if latent > 0 and span_C > 0 else 0.0)
    return resin.conductivity / (resin.density * 1e12 * c) * 1e6


def _biot_root(biot: float) -> float:
    """The first root of λ tan λ = Bi on (0, π/2), by bisection."""
    low, high = 0.0, math.pi / 2
    for _ in range(200):
        middle = 0.5 * (low + high)
        if middle * math.tan(middle) < biot:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def plate_cooling(s_mm: float, alpha_mm2_s: float, melt_C: float, mold_C: float, eject_C: float, *,
                  mean: bool, h: float | None = None, k: float | None = None) -> float:
    """The time a plate ``s_mm`` thick, cooled on both faces, takes from ``melt_C`` until its middle (``mean`` False)
    or its mean (``mean`` True) reaches ``eject_C``, s: the first term of the series solution.

    With perfect contact (``h`` None) it is the handbook's t = s² / (π² α) ln(C (T_melt - T_mould) / (T_eject - T_mould)),
    C = 4/π for the middle and 8/π² for the mean. With a contact coefficient ``h`` (W/(m² K)) and the resin's ``k``, the
    first eigenvalue λ of λ tan λ = Bi (Bi = h (s/2) / k) replaces π/2, and C = 4 sin λ / (2λ + sin 2λ), times sin λ / λ
    for the mean. Zero where the one-term series is not valid (the ejection temperature close to the melt's)."""
    if h is None:
        lam = math.pi / 2
    else:
        lam = _biot_root(h * (s_mm / 2000.0) / k)
    coefficient = 4.0 * math.sin(lam) / (2.0 * lam + math.sin(2.0 * lam))
    if mean:
        coefficient *= math.sin(lam) / lam
    ratio = coefficient * (melt_C - mold_C) / (eject_C - mold_C)
    if ratio <= 1.0:
        return 0.0
    return (s_mm / 2.0) ** 2 / (alpha_mm2_s * lam * lam) * math.log(ratio)


def linear_shrinkage(resin, stayed_hot: float) -> float:
    """The linear shrinkage, %, of a point that took ``stayed_hot`` times as long as the thinnest wall to reach the
    ejection temperature: the low end of the resin's range at the thinnest wall (and anything that cools sooner),
    rising toward the high end the longer it stayed hot, low + (high - low) (1 - 1 / ratio). This scaling is cadgen's
    own model, not a published law (the range's ends are the resin's published shrinkage): the warp it drives is an
    estimate."""
    low, high = resin.shrinkage
    if not stayed_hot > 1.0:
        return low
    return low + (high - low) * (1.0 - 1.0 / stayed_hot)
