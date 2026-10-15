"""The casting alloys and the moulds a ``casting`` study names.

An alloy is what solidification needs: density, conductivity, specific heat, latent heat, liquidus and solidus, and the
critical Niyama value below which shrinkage porosity is likely where one is published for it (``None`` where none is).
Units are the ones people write them in (kg/m³ is converted to the engine's tonne/mm³ here; W/(m K), J/(kg K), J/kg,
°C, (°C s)^½/mm). The values are handbook room-temperature ones, constant through the run; their sources are listed
in the manufacturing-sim skill's casting reference. A pure metal freezes at one temperature; it is given a freezing
range of :data:`PURE_RANGE_C` so the enthalpy is a function of temperature.

A mould (the study's ``mold``: sand, investment, a permanent mould or a die) is its temperature, the pour's usual superheat, and how it takes heat out. A sand or investment
mould heats up as it takes heat in, so its heat transfer coefficient falls with time as a semi-infinite body's does,
h(t) = e / √(π t) for a mould of effusivity e = √(k ρ c) (:func:`mould_h`), the contact with the metal taken as
perfect; this is what makes the freezing time grow with the square of the section (Chvorinov's rule). A metal mould
(permanent or die) is a constant coefficient, and the freezing time grows with the section itself. Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.fea.analyses.kinds import json_text

__all__ = [
    "ALLOYS", "CastingAlloy", "MOLDS", "Mold", "PURE_RANGE_C", "chvorinov", "lookup_alloy", "lookup_mold",
    "mould_h",
]

#: A pure metal (fine silver) freezes over this many degrees here, so its enthalpy is a function of temperature.
PURE_RANGE_C = 1.0


@dataclass(frozen=True)
class CastingAlloy:
    key: str
    name: str
    #: tonne/mm³ (the engine's): mass = density x volume in mm³ is in tonnes.
    density: float
    #: W/(m K): numerically the engine's mW/(mm K), which :func:`cadgen._internal.fea.operators.conduction` reads.
    conductivity: float
    #: J/(kg K), one value for liquid and solid.
    specific_heat: float
    #: J/kg.
    latent_heat: float
    liquidus: float
    solidus: float
    #: The critical Niyama value, (°C s)^½/mm, below which shrinkage porosity is likely; ``None`` where none is published.
    niyama: float | None
    #: "precious", "copper", "aluminium", "zinc", "iron" or "steel".
    family: str

    @property
    def pure(self) -> bool:
        return self.liquidus - self.solidus < PURE_RANGE_C

    @property
    def freezing(self) -> tuple[float, float]:
        """(solidus, liquidus) as solved: a pure metal's spread over :data:`PURE_RANGE_C` about its melting point."""
        if self.pure:
            middle = 0.5 * (self.liquidus + self.solidus)
            return middle - PURE_RANGE_C / 2, middle + PURE_RANGE_C / 2
        return self.solidus, self.liquidus

    def as_dict(self) -> dict:
        return {"name": self.name, "density_kg_m3": round(self.density * 1e12, 3), "conductivity_W_mK": self.conductivity,
                "specific_heat_J_kgK": self.specific_heat, "latent_heat_kJ_kg": round(self.latent_heat / 1000, 3),
                "liquidus_C": self.liquidus, "solidus_C": self.solidus, "niyama_critical": self.niyama}


def _alloy(key, name, kg_m3, k, c, kj_kg, liquidus, solidus, niyama, family) -> CastingAlloy:
    return CastingAlloy(key, name, kg_m3 * 1e-12, k, c, kj_kg * 1000.0, liquidus, solidus, niyama, family)


# Sources per value: the manufacturing-sim skill's casting reference ("The alloys").
ALLOYS: dict[str, CastingAlloy] = {alloy.key: alloy for alloy in (
    _alloy("sterling-silver-925", "Sterling silver 925", 10_360, 350, 246, 112, 892, 810, None, "precious"),
    _alloy("fine-silver", "Fine silver 999", 10_490, 429, 235, 104.6, 961.8, 961.8, None, "precious"),
    _alloy("gold-14k-yellow", "14k yellow gold", 13_000, 66, 222, 109, 870, 830, None, "precious"),
    _alloy("gold-18k-yellow", "18k yellow gold", 15_300, 66, 174, 87, 900, 860, None, "precious"),
    _alloy("tin-bronze", "Tin bronze C90500", 8_720, 74.8, 377, 192, 999, 854, None, "copper"),
    _alloy("silicon-bronze", "Silicon bronze C87300", 8_360, 28.4, 377, 236, 971, 821, None, "copper"),
    _alloy("yellow-brass", "Yellow brass C85400", 8_440, 87.9, 377, 172, 941, 927, None, "copper"),
    _alloy("a356", "A356 aluminium", 2_685, 151, 963, 425, 615, 555, 0.3, "aluminium"),
    _alloy("a380", "A380 aluminium", 2_710, 96.2, 963, 400, 593, 538, None, "aluminium"),
    _alloy("zamak-3", "Zamak 3", 6_600, 113, 419, 120, 387, 381, None, "zinc"),
    _alloy("grey-iron", "Grey iron (class 30)", 7_150, 46, 490, 230, 1200, 1150, None, "iron"),
    _alloy("ductile-iron", "Ductile iron 65-45-12", 7_100, 36, 460, 230, 1160, 1120, None, "iron"),
    _alloy("wcb-steel", "Cast carbon steel WCB", 7_850, 50, 486, 247, 1502, 1462, 0.775, "steel"),
    _alloy("cf8m-stainless", "CF8M stainless", 8_000, 16.3, 500, 290, 1430, 1375, 1.0, "steel"),
)}

_ALIASES = {
    "sterling": "sterling-silver-925", "sterling-silver": "sterling-silver-925", "925": "sterling-silver-925",
    "silver-925": "sterling-silver-925", "fine-silver-999": "fine-silver", "999": "fine-silver", "silver": "fine-silver",
    "14k": "gold-14k-yellow", "14k-gold": "gold-14k-yellow", "14k-yellow-gold": "gold-14k-yellow",
    "18k": "gold-18k-yellow", "18k-gold": "gold-18k-yellow", "18k-yellow-gold": "gold-18k-yellow",
    "c90500": "tin-bronze", "gunmetal": "tin-bronze", "bronze": "tin-bronze", "c87300": "silicon-bronze",
    "brass": "yellow-brass", "c85400": "yellow-brass", "a356.0": "a356", "a356-aluminium": "a356", "a356-aluminum": "a356",
    "a380.0": "a380", "a380-aluminium": "a380", "a380-aluminum": "a380", "zamak3": "zamak-3", "zamak": "zamak-3",
    "gray-iron": "grey-iron", "cast-iron": "grey-iron", "class-30": "grey-iron", "nodular-iron": "ductile-iron",
    "65-45-12": "ductile-iron", "sg-iron": "ductile-iron", "wcb": "wcb-steel", "cast-steel": "wcb-steel",
    "carbon-steel": "wcb-steel", "cf8m": "cf8m-stainless", "316": "cf8m-stainless", "stainless": "cf8m-stainless",
}


@dataclass(frozen=True)
class Mold:
    key: str
    #: How a sentence names the mould: "a sand mould".
    words: str
    #: The mould's temperature at the pour, °C.
    mold_C: float
    #: How far above the liquidus it is usually poured, °C.
    superheat_C: float
    #: A metal mould's heat transfer coefficient, W/(m² K), constant; ``None`` for an insulating mould.
    h: float | None = None
    #: An insulating mould's thermal effusivity √(k ρ c), W s^½/(m² K): it heats up as it takes heat in, and its
    #: coefficient falls as e / √(π t); ``None`` for a metal mould.
    effusivity: float | None = None
    #: The fill time estimate: this many seconds per √kg poured (gravity), or ``fill_s`` flat (a die).
    fill_s_per_sqrt_kg: float | None = None
    fill_s: float | None = None

    def fill_estimate(self, mass_kg: float) -> float:
        """The time the mould takes to fill, an estimate: K √(mass) for a gravity pour, a fixed time for a die."""
        if self.fill_s is not None:
            return self.fill_s
        return self.fill_s_per_sqrt_kg * math.sqrt(max(mass_kg, 0.0))


# Sources per value: the manufacturing-sim skill's casting reference ("The moulds").
MOLDS: dict[str, Mold] = {mold.key: mold for mold in (
    Mold("sand", "a sand mould", 25.0, 100.0, effusivity=1000.0, fill_s_per_sqrt_kg=2.0),
    Mold("investment", "an investment (lost-wax) mould", 600.0, 100.0, effusivity=600.0, fill_s_per_sqrt_kg=2.0),
    Mold("permanent_mold", "a permanent (gravity die) mould", 300.0, 100.0, h=1000.0, fill_s_per_sqrt_kg=2.0),
    Mold("die", "a die (high-pressure die casting)", 200.0, 60.0, h=5000.0, fill_s=0.05),
)}


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").split())


def lookup_alloy(name) -> CastingAlloy:
    """A casting alloy by its table name or an alias; a ValueError naming ``alloy`` and listing the table otherwise."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"alloy: name the casting alloy, one of {', '.join(ALLOYS)}; got {json_text(name)}")
    key = _key(name)
    key = _ALIASES.get(key, key)
    if key not in ALLOYS:
        raise ValueError(f"alloy: {name!r} is not a casting alloy cadgen knows; use one of {', '.join(ALLOYS)}")
    return ALLOYS[key]


def lookup_mold(name) -> Mold:
    """A casting mould by name; a ValueError naming ``mold`` and listing them otherwise."""
    key = _key(name).replace("-", "_") if isinstance(name, str) else None
    key = {"permanent_mould": "permanent_mold", "gravity_die": "permanent_mold", "lost_wax": "investment",
           "high_pressure_die": "die", "die_casting": "die"}.get(key, key)
    if key not in MOLDS:
        raise ValueError(f"mold: {json_text(name)} is not a casting mould cadgen knows; use one of "
                         f"{', '.join(MOLDS)}")
    return MOLDS[key]


def mould_h(h: float | None, effusivity: float | None, t0: float, t1: float) -> float:
    """The mould's mean heat transfer coefficient over [t0, t1] s, W/(m² K): a metal mould's ``h`` throughout; an
    insulating mould's e / √(π t) averaged over the step, 2 e (√t1 - √t0) / (√π (t1 - t0)), finite from t = 0, so a
    step takes the heat a face held at one temperature would pass in it whatever its length."""
    if effusivity is None:
        return float(h)
    a, b = math.sqrt(max(t0, 0.0)), math.sqrt(max(t1, 0.0))
    if b <= a:
        return effusivity / math.sqrt(math.pi * max(t1, 1e-12))
    return 2.0 * effusivity / (math.sqrt(math.pi) * (a + b))


def chvorinov(alloy: CastingAlloy, mold: Mold, *, pour_C: float, mold_C: float, h: float | None,
              modulus_mm: float) -> dict:
    """The casting's freezing time by hand, from its modulus V/A (mm): Chvorinov's rule, an estimate.

    The heat to take out per kg is the latent heat and everything above the solidus, L' = L + c (T_pour - T_solidus),
    through a face at the middle of the freezing range, ΔT = (T_liquidus + T_solidus) / 2 - T_mould. An insulating
    mould (``h`` None and an effusivity e): t = B (V/A)², B = (π / 4) (ρ L' / (e ΔT))², the rule's own derivation
    for a semi-infinite mould. A metal mould, or a study's own ``h``: the contact and the metal's own conduction in
    series, t = (ρ L' / ΔT) ((V/A) / h + (V/A)² / (2 k)): n = 1 where the contact controls, 2 where the metal does.
    """
    rho = alloy.density * 1e12
    heat = alloy.latent_heat + alloy.specific_heat * (pour_C - alloy.solidus)
    drop = 0.5 * (alloy.liquidus + alloy.solidus) - mold_C
    M = modulus_mm / 1000.0
    if h is None and mold.effusivity is not None:
        B = math.pi / 4.0 * (rho * heat / (mold.effusivity * drop)) ** 2
        return {"rule": "B (V/A)^2", "B_s_per_mm2": B * 1e-6, "modulus_mm": modulus_mm, "estimate_s": B * M * M}
    coefficient = float(h if h is not None else mold.h)
    contact = rho * heat * M / (coefficient * drop)
    conduction = rho * heat * M * M / (2.0 * alloy.conductivity * drop)
    return {"rule": "(V/A) / h + (V/A)^2 / 2k", "modulus_mm": modulus_mm, "estimate_s": contact + conduction,
            "contact_s": contact, "conduction_s": conduction}
