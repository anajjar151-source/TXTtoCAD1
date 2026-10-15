"""The steels and quenchants a ``heat_treatment`` study names, and how a cooling rate becomes a hardness.

A steel grade is what its hardening needs: its nominal composition (the middle of its AISI/SAE range), its usual
austenitising temperature, its Jominy curve (as-quenched hardness, HRC, against distance from the quenched end), and
its annealed yield strength (the strength a quench's stress is judged against, scaled to the temperature by
:data:`HOT_STRENGTH`). The Jominy curve of a low-alloy grade (1045, 4140, 4340, 8620) is Just's regression from its
composition (:func:`just_curve`); a grade outside that formula's range (52100 and O1, past its carbon; D2, H13 and 410,
past its chromium) carries an estimated curve, said so in every result.

A quenchant is a constant heat transfer coefficient and its bath temperature. The part itself is austenite through the
quench: :data:`AUSTENITE` holds its properties (Eurocode 3's for carbon steel above the transformation), one set for
every grade, so the cooling is the grade's own only through its austenitising temperature.

A point's hardness: its cooling rate at 700 °C is the cooling rate of one place on a Jominy bar
(:data:`JOMINY_RATES`, the end-quench test's own table), whose distance reads the grade's curve. The hand check
(:func:`centre_cooling`) is the exact series solution of a round's (or a block's) centre cooling with the same
coefficient, the conduction Grossmann's severity H and ideal critical diameter rest on. Units: mm, s, °C, W/(m² K),
W/(m K), J/(kg K), MPa, HRC. Stdlib only at import; the hand check imports scipy inside its functions. Every value's
source is in the manufacturing-sim skill's heat-treatment reference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.fea.analyses.kinds import json_text

__all__ = [
    "AUSTENITE", "GRADES", "Grade", "HOT_STRENGTH", "JOMINY_RATES", "QUENCHANTS", "Quenchant", "Austenite",
    "centre_cooling", "critical_diameters", "grossmann_H", "hot_strength", "jominy_distance", "jominy_rate",
    "just_curve", "lookup_grade", "lookup_quenchant", "martensite_50", "martensite_start", "QUENCHANT_ORDER",
]

#: Below the eutectoid temperature steel is not austenite, and nothing hardens.
A1_C = 727.0
#: The Rockwell C scale's floor: a curve never reads below it (softer steel is quoted on other scales).
HRC_FLOOR = 20.0


@dataclass(frozen=True)
class Austenite:
    """The part's properties through the quench, held constant: austenite, which a part quenched faster than it
    transforms stays until it does."""

    #: kg/m³, W/(m K), J/(kg K), 1/K.
    density: float
    conductivity: float
    specific_heat: float
    expansion: float
    #: MPa: room temperature's, so the elastic stress is an upper bound (the modulus falls as the steel heats).
    E: float
    nu: float

    @property
    def diffusivity_mm2_s(self) -> float:
        return self.conductivity / (self.density * self.specific_heat) * 1e6


AUSTENITE = Austenite(density=7850.0, conductivity=27.3, specific_heat=650.0, expansion=20e-6, E=200_000.0, nu=0.30)

#: The end-quench test: the cooling rate at 700 °C (°C/s) at each distance from the quenched end (mm): its
#: 1/16-inch stations, 1 to 32.
JOMINY_RATES: tuple[tuple[float, float], ...] = (
    (1.6, 270.0), (3.2, 170.0), (4.8, 108.0), (6.4, 70.0), (7.9, 43.0), (9.5, 31.0), (11.1, 23.0), (12.7, 18.0),
    (14.3, 14.0), (15.9, 12.0), (19.1, 9.0), (22.2, 6.9), (25.4, 5.6), (28.6, 4.6), (31.8, 3.9), (38.1, 2.8),
    (44.5, 2.2), (50.8, 2.0),
)

#: Eurocode 3's reduction of a carbon steel's yield strength with temperature (°C, factor).
HOT_STRENGTH: tuple[tuple[float, float], ...] = (
    (20.0, 1.0), (400.0, 1.0), (500.0, 0.78), (600.0, 0.47), (700.0, 0.23), (800.0, 0.11), (900.0, 0.06),
    (1000.0, 0.04), (1100.0, 0.02), (1200.0, 0.0),
)


def _interp(points, x: float) -> float:
    """Piecewise linear through ``points`` (x ascending), held at the ends."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def hot_strength(annealed_yield_MPa: float, celsius: float) -> float:
    """The grade's yield strength at ``celsius``: its annealed room-temperature yield scaled by :data:`HOT_STRENGTH`."""
    return annealed_yield_MPa * _interp(HOT_STRENGTH, celsius)


def jominy_distance(rate_C_s: float) -> float:
    """The distance from a Jominy bar's quenched end (mm) that cools at ``rate_C_s`` at 700 °C: log-log between the
    stations; nearer than the first station reads it, and slower than the last carries the last two stations' slope
    on (the bar is no longer: the grade's curve holds its last value there)."""
    table = JOMINY_RATES
    if rate_C_s >= table[0][1]:
        return table[0][0]
    for (d0, r0), (d1, r1) in zip(table, table[1:]):
        if rate_C_s >= r1:
            share = math.log(r0 / rate_C_s) / math.log(r0 / r1)
            return math.exp(math.log(d0) + share * math.log(d1 / d0))
    (d0, r0), (d1, r1) = table[-2], table[-1]
    slope = math.log(r1 / r0) / math.log(d1 / d0)
    return d1 * (max(rate_C_s, 1e-9) / r1) ** (1.0 / slope)


def jominy_rate(distance_mm: float) -> float:
    """The cooling rate at 700 °C (°C/s) at ``distance_mm`` from the quenched end: :func:`jominy_distance`'s inverse."""
    table = JOMINY_RATES
    if distance_mm <= table[0][0]:
        return table[0][1]
    for (d0, r0), (d1, r1) in zip(table, table[1:]):
        if distance_mm <= d1:
            share = math.log(distance_mm / d0) / math.log(d1 / d0)
            return math.exp(math.log(r0) + share * math.log(r1 / r0))
    (d0, r0), (d1, r1) = table[-2], table[-1]
    slope = math.log(r1 / r0) / math.log(d1 / d0)
    return r1 * (distance_mm / d1) ** slope


def martensite_start(composition: dict[str, float]) -> float:
    """Ms, °C: where martensite starts to form, Andrews' linear formula (1965),
    539 - 423 C - 30.4 Mn - 17.7 Ni - 12.1 Cr - 7.5 Mo, the carbon taken at 0.6 % at most (what a hypereutectoid grade
    dissolves at its hardening heat; the formula's own range)."""
    return (539.0 - 423.0 * min(composition.get("C", 0.0), 0.6) - 30.4 * composition.get("Mn", 0.0)
            - 17.7 * composition.get("Ni", 0.0) - 12.1 * composition.get("Cr", 0.0) - 7.5 * composition.get("Mo", 0.0))


def martensite_50(carbon: float) -> float:
    """The hardness of half martensite, HRC, from the carbon (wt %): Just's 44 √C + 14, the hardness a critical
    diameter is measured to."""
    return 44.0 * math.sqrt(carbon) + 14.0


# -- the grades ---------------------------------------------------------------------------------------

#: Just's formula's stations, mm: the quenched end, then 6 to 80 mm, the formula's range.
JUST_STATIONS = (1.5, 3.0, 4.5, 6.0, 8.0, 10.0, 13.0, 16.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0, 70.0, 80.0)
#: ASTM grain size and phosphorus Just's formula takes, when the grade does not say: a fine-grained steel's.
GRAIN_SIZE, PHOSPHORUS = 7.0, 0.015


def just_curve(composition: dict[str, float]) -> tuple[tuple[float, float], ...]:
    """The Jominy curve (mm, HRC) of a low-alloy steel from its composition (wt %), Just's regression (1969):

        J(E) = 95 √C - 0.00276 E² √C + 20 Cr + 38 Mo + 14 Mn + 5.5 Ni + 6.1 Si + 39 V + 96 P - 0.81 K
               - 12.28 √E + 0.898 E - 13,

    E the distance in mm (6 to 80), K the ASTM grain size, capped at the quenched end's 60 √C + 20. Nearer than 6 mm
    it runs straight from the quenched end's hardness at 1.5 mm; it never rises with distance and never reads under
    the C scale's 20."""
    c = composition.get("C", 0.0)
    root = math.sqrt(c)
    base = (95 * root + 20 * composition.get("Cr", 0.0) + 38 * composition.get("Mo", 0.0)
            + 14 * composition.get("Mn", 0.0) + 5.5 * composition.get("Ni", 0.0) + 6.1 * composition.get("Si", 0.0)
            + 39 * composition.get("V", 0.0) + 96 * composition.get("P", PHOSPHORUS) - 0.81 * GRAIN_SIZE - 13)
    top = 60 * root + 20

    def at(e: float) -> float:
        return base - 0.00276 * e * e * root - 12.28 * math.sqrt(e) + 0.898 * e

    six = min(top, at(6.0))
    points, lowest = [], top
    for e in JUST_STATIONS:
        value = top + (six - top) * (e - 1.5) / 4.5 if e < 6.0 else min(top, at(e))
        lowest = min(lowest, max(HRC_FLOOR, value))
        points.append((e, round(lowest, 2)))
    return tuple(points)


@dataclass(frozen=True)
class Grade:
    key: str
    name: str
    #: wt %, the middle of the grade's range.
    composition: dict
    austenitize_C: float
    #: "water", "oil" or "air": the quench it is made for.
    hardens_in: str
    #: (mm from the quenched end, HRC), distance ascending, never rising.
    jominy: tuple
    #: "Just's formula from its composition", or "estimated" (a grade outside the formula).
    jominy_source: str
    annealed_yield_MPa: float
    #: A carburising grade: the result is its core's hardness alone.
    core_only: bool = False

    @property
    def estimated(self) -> bool:
        return self.jominy_source != "just"

    @property
    def carbon(self) -> float:
        return self.composition["C"]

    @property
    def hardest(self) -> float:
        return self.jominy[0][1]

    def hardness(self, distance_mm: float) -> float:
        """HRC at ``distance_mm`` along its Jominy bar, held at the curve's ends."""
        return _interp(self.jominy, distance_mm)

    def as_dict(self) -> dict:
        return {"name": self.name, "composition_wt_pct": dict(self.composition), "austenitize_C": self.austenitize_C,
                "hardens_in": self.hardens_in, "jominy_source": self.jominy_source,
                "jominy_mm_hrc": [list(point) for point in self.jominy], "annealed_yield_MPa": self.annealed_yield_MPa}


def _grade(key, name, composition, austenitize, hardens_in, yield_MPa, jominy=None, core_only=False) -> Grade:
    if jominy is None:
        return Grade(key, name, composition, austenitize, hardens_in, just_curve(composition), "just", yield_MPa,
                     core_only)
    return Grade(key, name, composition, austenitize, hardens_in, tuple(jominy), "estimated", yield_MPa, core_only)


# Sources per value: the manufacturing-sim skill's heat-treatment reference ("The steels").
GRADES: dict[str, Grade] = {grade.key: grade for grade in (
    _grade("1045", "AISI 1045", {"C": 0.465, "Mn": 0.75, "Si": 0.25}, 845.0, "water", 310.0),
    _grade("4140", "AISI 4140", {"C": 0.405, "Mn": 0.875, "Si": 0.25, "Cr": 0.95, "Mo": 0.20}, 845.0, "oil", 417.0),
    _grade("4340", "AISI 4340", {"C": 0.405, "Mn": 0.70, "Si": 0.25, "Ni": 1.825, "Cr": 0.80, "Mo": 0.25}, 845.0,
           "oil", 470.0),
    _grade("8620", "AISI 8620 (core)", {"C": 0.205, "Mn": 0.80, "Si": 0.25, "Ni": 0.55, "Cr": 0.50, "Mo": 0.20},
           845.0, "oil", 385.0, core_only=True),
    _grade("52100", "AISI 52100", {"C": 1.04, "Mn": 0.35, "Si": 0.25, "Cr": 1.45}, 845.0, "oil", 550.0,
           jominy=((1.5, 65.0), (6.0, 64.0), (9.0, 58.0), (12.0, 48.0), (16.0, 42.0), (20.0, 39.0), (30.0, 36.0),
                   (50.0, 33.0))),
    _grade("o1", "AISI O1 tool steel", {"C": 0.90, "Mn": 1.20, "Si": 0.30, "Cr": 0.50, "W": 0.50, "V": 0.15}, 800.0,
           "oil", 400.0,
           jominy=((1.5, 65.0), (6.0, 64.0), (10.0, 60.0), (14.0, 52.0), (18.0, 46.0), (25.0, 41.0), (35.0, 38.0),
                   (50.0, 35.0))),
    _grade("d2", "AISI D2 tool steel", {"C": 1.55, "Mn": 0.35, "Si": 0.35, "Cr": 12.0, "Mo": 0.95, "V": 0.90},
           1010.0, "air", 450.0, jominy=((1.5, 62.0), (80.0, 62.0))),
    _grade("h13", "AISI H13 tool steel", {"C": 0.39, "Mn": 0.35, "Si": 1.0, "Cr": 5.13, "Mo": 1.43, "V": 1.0},
           1010.0, "air", 400.0, jominy=((1.5, 53.0), (80.0, 53.0))),
    _grade("410", "AISI 410 stainless", {"C": 0.12, "Mn": 0.50, "Si": 0.50, "Cr": 12.5}, 980.0, "air", 275.0,
           jominy=((1.5, 42.0), (80.0, 42.0))),
)}

_GRADE_ALIASES = {
    "aisi-1045": "1045", "sae-1045": "1045", "c45": "1045", "aisi-4140": "4140", "sae-4140": "4140", "42crmo4": "4140",
    "aisi-4340": "4340", "sae-4340": "4340", "aisi-8620": "8620", "sae-8620": "8620", "aisi-52100": "52100",
    "sae-52100": "52100", "100cr6": "52100", "aisi-o1": "o1", "o-1": "o1", "aisi-d2": "d2", "d-2": "d2",
    "aisi-h13": "h13", "h-13": "h13", "aisi-410": "410", "410-stainless": "410", "ss410": "410",
    "stainless-410": "410",
}


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").split())


def lookup_grade(name) -> Grade:
    """A steel grade by its table name or an alias; a ValueError naming ``steel`` and listing the table otherwise."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"steel: name the steel grade, one of {', '.join(GRADES)}; got {json_text(name)}")
    key = _key(name)
    key = _GRADE_ALIASES.get(key, key)
    if key not in GRADES:
        raise ValueError(f"steel: {name!r} is not a steel grade cadgen knows; use one of {', '.join(GRADES)}")
    return GRADES[key]


# -- the quenchants ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Quenchant:
    key: str
    #: How a sentence names it: "still water at 32 °C".
    words: str
    #: W/(m² K), constant through the quench.
    h: float
    bath_C: float


# Sources per value: the manufacturing-sim skill's heat-treatment reference ("The quenchants"). Slowest first.
QUENCHANTS: dict[str, Quenchant] = {quenchant.key: quenchant for quenchant in (
    Quenchant("still_air", "still air", 200.0, 27.0),
    Quenchant("forced_air", "forced air (about 5 m/s)", 350.0, 27.0),
    Quenchant("slow_oil", "a slow (conventional) oil, still", 1100.0, 65.0),
    Quenchant("fast_oil", "a fast quench oil, still", 2000.0, 60.0),
    Quenchant("polymer_10", "a 10 % polymer solution, still", 3500.0, 43.0),
    Quenchant("still_water", "still water", 5000.0, 32.0),
    Quenchant("brine", "brine, still", 9000.0, 32.0),
    Quenchant("agitated_water", "agitated water (about 0.5 m/s)", 12000.0, 32.0),
)}
#: The quenchants slowest to fastest: what a fix moves along.
QUENCHANT_ORDER: tuple[str, ...] = tuple(QUENCHANTS)

_QUENCHANT_ALIASES = {
    "water": "still_water", "air": "still_air", "polymer": "polymer_10", "pag": "polymer_10", "polymer_10%": "polymer_10",
    "salt_water": "brine", "oil": None, "conventional_oil": "slow_oil", "accelerated_oil": "fast_oil",
}


def lookup_quenchant(name) -> Quenchant:
    """A quenchant by name; a ValueError naming ``quenchant`` and listing them otherwise."""
    key = _key(name).replace("-", "_") if isinstance(name, str) else None
    if key in _QUENCHANT_ALIASES:
        key = _QUENCHANT_ALIASES[key]
        if key is None:
            raise ValueError("quenchant: \"oil\" is two quenchants here; use fast_oil (an accelerated quench oil) or "
                             "slow_oil (a conventional one)")
    if key not in QUENCHANTS:
        raise ValueError(f"quenchant: {json_text(name)} is not a quenchant cadgen knows; use one of "
                         f"{', '.join(QUENCHANTS)}")
    return QUENCHANTS[key]


def grossmann_H(h: float, conductivity: float = AUSTENITE.conductivity) -> float:
    """Grossmann's quench severity H = h / 2k, per inch, with the part's conductivity."""
    return h / (2.0 * conductivity) * 0.0254


# -- the hand check: a round's (or a block's) centre ---------------------------------------------------

#: Terms of each series.
TERMS = 200


def _slab_roots(biot: float):
    """λ_n of a slab, λ tan λ = Bi (Bi = inf: (2n - 1) π / 2), and each term's centre weight."""
    import numpy as np
    from scipy.optimize import brentq

    n = np.arange(1, TERMS + 1)
    if math.isinf(biot):
        roots = (2 * n - 1) * math.pi / 2
    else:
        roots = np.array([brentq(lambda x: x * math.sin(x) - biot * math.cos(x), (k - 1) * math.pi + 1e-12,
                                 (k - 1) * math.pi + math.pi / 2 - 1e-12) for k in n])
    weights = 4 * np.sin(roots) / (2 * roots + np.sin(2 * roots))
    return roots, weights


def _cylinder_roots(biot: float):
    """λ_n of a long cylinder, λ J1(λ) = Bi J0(λ) (Bi = inf: the zeros of J0), and each term's centre weight."""
    import numpy as np
    from scipy.optimize import brentq
    from scipy.special import j0, j1, jn_zeros

    zeros0 = jn_zeros(0, TERMS)
    if math.isinf(biot):
        roots = zeros0
    else:
        zeros1 = np.concatenate([[0.0], jn_zeros(1, TERMS - 1)])
        roots = np.array([brentq(lambda x: x * j1(x) - biot * j0(x), low + 1e-12, high - 1e-12)
                          for low, high in zip(zeros1, zeros0)])
    weights = 2 * j1(roots) / (roots * (j0(roots) ** 2 + j1(roots) ** 2))
    return roots, weights


def centre_cooling(shape: str, dims_mm, h: float, *, start_C: float, bath_C: float,
                   steel: Austenite = AUSTENITE) -> dict:
    """The centre of a round or a block cooling in a quench of constant ``h`` (``inf``: an ideal quench): the exact
    series solution of the conduction (a finite round, or a block, is the product of its long round's and its
    slabs'), Grossmann's own. ``shape`` "round": ``dims_mm`` (diameter, length or ``inf``); "block": its three sides.

    Returns when the centre passes 800, 700 and 500 °C, its cooling rate at 700 °C, and t8/5; ``None`` for a
    temperature it never reaches (a bath above it, or a start below it)."""
    import numpy as np
    from scipy.optimize import brentq

    k, a = steel.conductivity, steel.diffusivity_mm2_s
    factors = []  # (roots, weights, half-size mm)
    if shape == "round":
        diameter, length = dims_mm
        radius = diameter / 2.0
        factors.append((*_cylinder_roots(h * radius / 1000.0 / k if math.isfinite(h) else math.inf), radius))
        if math.isfinite(length):
            factors.append((*_slab_roots(h * length / 2000.0 / k if math.isfinite(h) else math.inf), length / 2.0))
    elif shape == "block":
        for side in dims_mm:
            factors.append((*_slab_roots(h * side / 2000.0 / k if math.isfinite(h) else math.inf), side / 2.0))
    else:
        raise ValueError(f"centre_cooling: shape {shape!r} is not 'round' or 'block'")

    def theta(t: float) -> tuple[float, float]:
        value, slope_sum = 1.0, 0.0
        parts = []
        for roots, weights, half in factors:
            decay = roots ** 2 * a / (half * half)
            terms = weights * np.exp(-decay * t)
            parts.append((float(terms.sum()), float(-(decay * terms).sum())))
        for part, _ in parts:
            value *= part
        for i, (part, slope) in enumerate(parts):
            rest = 1.0
            for j, (other, _) in enumerate(parts):
                if j != i:
                    rest *= other
            slope_sum += slope * rest
        return value, slope_sum

    span = start_C - bath_C
    largest = max(half for _, _, half in factors)
    late = 50.0 * largest * largest / a

    def when(celsius: float) -> float | None:
        if not bath_C < celsius < start_C:
            return 0.0 if celsius >= start_C else None
        target = (celsius - bath_C) / span
        early = 1e-6 * min(half for _, _, half in factors) ** 2 / a
        while theta(early)[0] < target and early > 1e-15:
            early /= 10.0
        return brentq(lambda t: theta(t)[0] - target, early, late, xtol=1e-12, rtol=1e-10)

    times = {celsius: when(celsius) for celsius in (800.0, 700.0, 500.0)}
    rate = None
    if times[700.0]:
        rate = -span * theta(times[700.0])[1]
    t85 = times[500.0] - times[800.0] if times[500.0] is not None and times[800.0] is not None else None
    return {"t_800_s": times[800.0], "t_700_s": times[700.0], "t_500_s": times[500.0], "rate_700_C_s": rate,
            "t85_s": t85}


def critical_diameters(grade: Grade, h: float, *, start_C: float, bath_C: float) -> dict:
    """Grossmann's ideal critical diameter D_I and this quench's critical diameter (mm): the largest long round whose
    centre is half martensite (:func:`martensite_50`), quenched ideally (h = inf) and by ``h``. The centre must cool at
    700 °C as fast as the Jominy bar does where the grade's curve reads half martensite. ``None`` where the curve
    never falls to it (an air-hardening grade): larger than a Jominy bar can show."""
    from scipy.optimize import brentq

    # Just's 50 % martensite holds to 0.6 % carbon, about what a hypereutectoid grade dissolves at its hardening heat.
    half = martensite_50(min(grade.carbon, 0.6))
    distance = None
    for (d0, h0), (d1, h1) in zip(grade.jominy, grade.jominy[1:]):
        if h0 >= half > h1:
            distance = d0 + (d1 - d0) * (h0 - half) / (h0 - h1)
            break
    if distance is None:
        return {"half_martensite_HRC": round(half, 2), "jominy_mm": None, "ideal_mm": None, "this_quench_mm": None}
    needed = jominy_rate(distance)

    def diameter(coefficient: float) -> float | None:
        def gap(d: float) -> float:
            rate = centre_cooling("round", (d, math.inf), coefficient, start_C=start_C, bath_C=bath_C)["rate_700_C_s"]
            return (rate or 0.0) - needed

        low, high = 0.5, 2000.0
        if gap(low) < 0:
            return 0.0
        if gap(high) > 0:
            return None
        return brentq(gap, low, high, xtol=1e-3)

    return {"half_martensite_HRC": round(half, 2), "jominy_mm": distance, "ideal_mm": diameter(math.inf),
            "this_quench_mm": diameter(h)}
