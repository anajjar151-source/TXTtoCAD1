"""The sheets a ``sheet_metal`` study names, and the press brake's hand formulas: springback, cracking, bend allowance.

A sheet is what a bend needs: Young's modulus and Poisson's ratio, the yield and tensile strength, the strain-hardening
exponent n, the elongation, and the smallest inside radius it bends to 90° without cracking, as a multiple of the
thickness (R/t), by thickness where its source tabulates it so. Units are the ones people write them in: MPa, %, mm.
The values are handbook ones; their sources are listed in the manufacturing-sim skill's sheet metal reference, which
also says which could not be verified.

The formulas, each an estimate for one bend of inside radius R, thickness t and angle θ:

- springback (:func:`gardiner`): Gardiner's elastic-perfectly-plastic relation for the radius after release,
  R / R_f = 4 (R Y / (E t))³ - 3 (R Y / (E t)) + 1, and the angle it keeps, K_s = θ_f / θ = (2R/t + 1) / (2R_f/t + 1),
  the mid-thickness's length held (Kalpakjian and Schmid's form);
- the same with work hardening (:func:`hosford_caddell`): a power-law sheet, σ = K ε^n in plane strain, unloads its
  bending moment elastically, Δ(1/ρ) = 6 K' (t / 2ρ)^n / ((n + 2) E' t) at the mid-thickness radius ρ;
- the outer fibre's strain (:func:`outer_strain`), e = 1 / (2R/t + 1), against the sheet's at its minimum R/t;
- the K-factor (:func:`k_factor`, DIN 6935's k = 0.65 + 0.5 lg(R/t), K = k / 2), the bend allowance
  BA = θ (R + K t) and the bend deduction BD = 2 (R + t) tan(θ / 2) - BA (:func:`allowance`).

Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.fea.analyses.kinds import json_text, number

__all__ = [
    "SHEETS", "SheetMaterial", "allowance", "gardiner", "hosford_caddell", "k_factor", "lookup_sheet", "outer_strain",
    "sheet_from_spec", "strain_limit",
]

#: The Aluminum Association's tabulated thicknesses, inches to mm: 1/64, 1/32, 1/16, 1/8, 3/16, 1/4, 3/8, 1/2.
_AA_MM = (0.397, 0.794, 1.588, 3.175, 4.763, 6.35, 9.525, 12.7)


def _aa(*ratios: float) -> tuple[tuple[float, float], ...]:
    return tuple(zip(_AA_MM, ratios))


@dataclass(frozen=True)
class SheetMaterial:
    key: str
    name: str
    #: Young's modulus, MPa.
    E: float
    nu: float
    #: Yield and ultimate tensile strength, MPa (typical, as each source gives them).
    yield_strength: float
    uts: float
    #: The strain-hardening exponent of σ = K ε^n.
    n: float
    #: Elongation at break, %.
    elongation: float
    #: The smallest inside radius over thickness for a 90° bend without cracking: (thickness mm, R/t) pairs,
    #: interpolated in thickness and held beyond the ends; one pair is one value for every thickness.
    min_r_t: tuple[tuple[float, float], ...]
    #: The same for a bend along the grain (its bend line parallel to the rolling direction), where a source gives
    #: one; ``None`` where the source gives one value for either direction.
    min_r_t_along: tuple[tuple[float, float], ...] | None = None
    #: "steel", "stainless", "aluminium" or "copper".
    family: str = ""

    def min_ratio(self, thickness_mm: float, along_grain: bool = False) -> float:
        """The minimum R/t at this thickness: the along-the-grain table for a bend along it where there is one."""
        table = self.min_r_t_along if along_grain and self.min_r_t_along is not None else self.min_r_t
        return _interpolate(table, thickness_mm)

    def as_dict(self) -> dict:
        return {"name": self.name, "E_MPa": self.E, "nu": self.nu, "yield_MPa": self.yield_strength,
                "uts_MPa": self.uts, "n": self.n, "elongation_percent": self.elongation,
                "min_r_t": [list(pair) for pair in self.min_r_t],
                **({} if self.min_r_t_along is None else {"min_r_t_along_grain": [list(p) for p in self.min_r_t_along]})}


def _interpolate(table: tuple[tuple[float, float], ...], x: float) -> float:
    if len(table) == 1 or x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def _sheet(key, name, E_GPa, nu, yield_MPa, uts_MPa, n, elongation, min_r_t, family) -> SheetMaterial:
    table = min_r_t if isinstance(min_r_t, tuple) else ((0.0, float(min_r_t)),)
    return SheetMaterial(key, name, E_GPa * 1000.0, nu, yield_MPa, uts_MPa, n, elongation, table, None, family)


# Sources per value: the manufacturing-sim skill's sheet metal reference ("The sheets").
SHEETS: dict[str, SheetMaterial] = {sheet.key: sheet for sheet in (
    _sheet("crs-1008", "Mild steel CRS 1008/1010", 200, 0.29, 205, 330, 0.22, 30, 0.0, "steel"),
    _sheet("hsla-50", "HSLA grade 50", 200, 0.29, 345, 450, 0.15, 22, 0.5, "steel"),
    _sheet("stainless-304", "Stainless 304 (annealed)", 193, 0.29, 215, 505, 0.45, 70, 0.5, "stainless"),
    _sheet("stainless-316", "Stainless 316 (annealed)", 193, 0.29, 290, 580, 0.45, 50, 0.5, "stainless"),
    _sheet("aluminum-5052-h32", "Aluminium 5052-H32", 70.3, 0.33, 193, 228, 0.13, 12,
           _aa(0.0, 0.0, 1.0, 1.5, 1.5, 1.5, 1.5, 2.0), "aluminium"),
    _sheet("aluminum-6061-t6", "Aluminium 6061-T6", 68.9, 0.33, 276, 310, 0.05, 12,
           _aa(1.0, 1.0, 1.5, 2.5, 3.0, 3.5, 4.5, 5.0), "aluminium"),
    _sheet("aluminum-6061-o", "Aluminium 6061-O", 68.9, 0.33, 55, 124, 0.20, 25,
           _aa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.5, 2.0), "aluminium"),
    _sheet("aluminum-3003-h14", "Aluminium 3003-H14", 68.9, 0.33, 145, 150, 0.05, 8,
           ((0.8, 0.0), (1.6, 0.0), (3.2, 1.0), (4.8, 1.0), (6.0, 1.5)), "aluminium"),
    _sheet("copper-c110-h02", "Copper C110 (H02, half hard)", 117, 0.34, 255, 290, 0.10, 14, 0.5, "copper"),
    _sheet("brass-c260-h02", "Brass C260 (H02, half hard)", 110, 0.33, 358, 427, 0.20, 23, 1.0, "copper"),
)}

_ALIASES = {
    "crs": "crs-1008", "cold-rolled-steel": "crs-1008", "mild-steel": "crs-1008", "1008": "crs-1008", "1010": "crs-1008",
    "crs-1010": "crs-1008", "steel": "crs-1008", "a1008": "crs-1008", "hsla": "hsla-50", "hsla-grade-50": "hsla-50",
    "hslas-50": "hsla-50", "304": "stainless-304", "ss304": "stainless-304", "304-stainless": "stainless-304",
    "stainless": "stainless-304", "316": "stainless-316", "ss316": "stainless-316", "316-stainless": "stainless-316",
    "5052-h32": "aluminum-5052-h32", "5052": "aluminum-5052-h32", "aluminium-5052-h32": "aluminum-5052-h32",
    "6061-t6": "aluminum-6061-t6", "6061": "aluminum-6061-t6", "aluminium-6061-t6": "aluminum-6061-t6",
    "6061-o": "aluminum-6061-o", "aluminium-6061-o": "aluminum-6061-o", "3003-h14": "aluminum-3003-h14",
    "3003": "aluminum-3003-h14", "aluminium-3003-h14": "aluminum-3003-h14", "c110": "copper-c110-h02",
    "copper": "copper-c110-h02", "copper-c110": "copper-c110-h02", "c260": "brass-c260-h02", "brass": "brass-c260-h02",
    "brass-c260": "brass-c260-h02", "cartridge-brass": "brass-c260-h02",
}


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").split())


def lookup_sheet(name) -> SheetMaterial:
    """A sheet by its table name or an alias; a ValueError naming ``material`` and listing the table otherwise."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"material: name the sheet, one of {', '.join(SHEETS)}; got {json_text(name)}")
    key = _key(name)
    key = _ALIASES.get(key, key)
    if key not in SHEETS:
        raise ValueError(f"material: {name!r} is not a sheet cadgen knows; use one of {', '.join(SHEETS)}, or an object "
                         'extending one with your own numbers, like {"name": "5052-h32", "yield_MPa": 200}')
    return SHEETS[key]


#: The keys a material object may give, beside ``name``.
SHEET_OBJECT_KEYS = ("E_MPa", "nu", "yield_MPa", "uts_MPa", "n", "elongation_percent", "min_r_t", "min_r_t_along_grain")


def _ratio_table(value, where: str) -> tuple[tuple[float, float], ...]:
    """A minimum R/t: one number, or ``[[thickness_mm, R/t], ...]`` in rising thickness."""
    if not isinstance(value, list):
        ratio = number(value, where=where)
        if ratio < 0:
            raise ValueError(f"{where}: zero or more, got {ratio:g}")
        return ((0.0, ratio),)
    pairs = []
    for index, pair in enumerate(value):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"{where}[{index}]: a [thickness_mm, R/t] pair, like [1.6, 1.0]")
        pairs.append((number(pair[0], where=f"{where}[{index}]", positive=True), number(pair[1], where=f"{where}[{index}]")))
    if not pairs or any(b[0] <= a[0] for a, b in zip(pairs, pairs[1:])) or any(p[1] < 0 for p in pairs):
        raise ValueError(f"{where}: [thickness_mm, R/t] pairs in rising thickness, each R/t zero or more")
    return tuple(pairs)


def sheet_from_spec(spec) -> SheetMaterial:
    """The study's ``material``: a table name, or an object that extends a table entry (``{"name": "5052-h32",
    "yield_MPa": 200}``) or gives every number itself (E_MPa, nu, yield_MPa, uts_MPa, n, min_r_t)."""
    if isinstance(spec, str):
        return lookup_sheet(spec)
    if not isinstance(spec, dict):
        raise ValueError(f"material: a sheet's name ({', '.join(SHEETS)}) or an object with its numbers")
    unknown = set(spec) - {"name", *SHEET_OBJECT_KEYS}
    if unknown:
        raise ValueError(f"material: unknown keys {sorted(unknown)}; a sheet object takes name and "
                         f"{', '.join(SHEET_OBJECT_KEYS)}")
    base = None
    if isinstance(spec.get("name"), str):
        try:
            base = lookup_sheet(spec["name"])
        except ValueError:
            base = None
    needed = ("E_MPa", "nu", "yield_MPa", "uts_MPa", "n", "min_r_t")
    if base is None and not set(needed) <= set(spec):
        missing = [key for key in needed if key not in spec]
        raise ValueError(f"material: an object that names no sheet in the table needs {', '.join(needed)}; "
                         f"missing {', '.join(missing)}")

    def value(key: str, fallback, positive: bool = True):
        return number(spec[key], where=f"material.{key}", positive=positive) if key in spec else fallback

    name = spec.get("name") if isinstance(spec.get("name"), str) and spec["name"].strip() else "Custom sheet"
    sheet = SheetMaterial(
        key=base.key if base else _key(name),
        name=base.name + " (the study's numbers)" if base and set(spec) - {"name"} else (base.name if base else name),
        E=value("E_MPa", base.E if base else None),
        nu=value("nu", base.nu if base else None),
        yield_strength=value("yield_MPa", base.yield_strength if base else None),
        uts=value("uts_MPa", base.uts if base else None),
        n=value("n", base.n if base else None, positive=False),
        elongation=value("elongation_percent", base.elongation if base else 0.0),
        min_r_t=_ratio_table(spec["min_r_t"], "material.min_r_t") if "min_r_t" in spec else base.min_r_t,
        min_r_t_along=(_ratio_table(spec["min_r_t_along_grain"], "material.min_r_t_along_grain")
                       if "min_r_t_along_grain" in spec else (base.min_r_t_along if base else None)),
        family=base.family if base else "",
    )
    if not 0 <= sheet.nu < 0.5:
        raise ValueError(f"material.nu: between 0 and 0.5, got {sheet.nu:g}")
    if not 0 <= sheet.n < 1:
        raise ValueError(f"material.n: the strain-hardening exponent, between 0 and 1, got {sheet.n:g}")
    if sheet.uts < sheet.yield_strength:
        raise ValueError(f"material: uts_MPa ({sheet.uts:g}) is below yield_MPa ({sheet.yield_strength:g})")
    return sheet


# -- the formulas -------------------------------------------------------------------------------------------------


def gardiner(radius: float, thickness: float, sheet: SheetMaterial) -> dict:
    """Gardiner's springback of a bend to inside radius ``radius``: the radius after release R_f, and the share of the
    angle kept, K_s = (2R/t + 1) / (2R_f/t + 1). ``elastic`` when the bend is too gentle to yield (R Y / (E t) at or
    past 1/2): it springs back flat, K_s = 0."""
    x = radius * sheet.yield_strength / (sheet.E * thickness)
    ratio = 4.0 * x ** 3 - 3.0 * x + 1.0          # R / R_f
    if ratio <= 0.0 or x >= 0.5:
        return {"x": x, "final_radius_mm": math.inf, "kept": 0.0, "elastic": True}
    final = radius / ratio
    kept = (2.0 * radius / thickness + 1.0) / (2.0 * final / thickness + 1.0)
    return {"x": x, "final_radius_mm": final, "kept": kept, "elastic": False}


def hosford_caddell(radius: float, thickness: float, sheet: SheetMaterial) -> float:
    """The share of the angle kept with work hardening (Hosford and Caddell): a power-law sheet σ = K ε^n, K from the
    tensile strength at the strain n (K = UTS (e / n)^n), bent in plane strain (K' = (2/√3)^(n+1) K,
    E' = E / (1 - ν²)) unloads Δ(1/ρ) = 6 K' (t / 2ρ)^n / ((n + 2) E' t) at the mid-thickness radius ρ = R + t/2, and
    the mid-thickness keeps its length: K_s = ρ / ρ_f. 0 when it springs back flat."""
    n = sheet.n
    K = sheet.uts * (math.e / n) ** n if n > 0 else sheet.uts
    K_plane = (2.0 / math.sqrt(3.0)) ** (n + 1.0) * K
    E_plane = sheet.E / (1.0 - sheet.nu ** 2)
    rho = radius + thickness / 2.0
    unload = 6.0 * K_plane * (thickness / (2.0 * rho)) ** n / ((n + 2.0) * E_plane * thickness)
    after = 1.0 / rho - unload
    return 0.0 if after <= 0.0 else rho * after


def outer_strain(radius: float, thickness: float) -> float:
    """The outer fibre's engineering strain at inside radius R: e = 1 / (2R/t + 1), the neutral axis mid-thickness."""
    return 1.0 / (2.0 * radius / thickness + 1.0)


def strain_limit(min_r_t: float) -> float:
    """The outer strain at the sheet's minimum R/t: what it takes without cracking."""
    return 1.0 / (2.0 * min_r_t + 1.0)


#: K-factors held within the range bend tables give (SendCutSend: typically 0.30 to 0.50).
K_RANGE = (0.30, 0.50)


def k_factor(r_over_t: float) -> float:
    """DIN 6935's neutral-fibre factor, k = 0.65 + 0.5 lg(R/t) (1 from R/t = 5), as a K-factor K = k / 2 (the neutral
    fibre's distance from the inside over t), held within :data:`K_RANGE`."""
    k = 1.0 if r_over_t >= 5.0 else 0.65 + 0.5 * math.log10(max(r_over_t, 1e-9))
    return min(max(k / 2.0, K_RANGE[0]), K_RANGE[1])


def allowance(radius: float, thickness: float, angle_deg: float, K: float) -> dict:
    """The flat length a bend takes: the bend allowance BA = θ (R + K t), the outside setback (R + t) tan(θ/2) and the
    bend deduction BD = 2 setback - BA (``None`` from 180°, where the setback has no end)."""
    theta = math.radians(angle_deg)
    ba = theta * (radius + K * thickness)
    if angle_deg >= 179.999:
        return {"bend_allowance_mm": ba, "outside_setback_mm": None, "bend_deduction_mm": None}
    setback = (radius + thickness) * math.tan(theta / 2.0)
    return {"bend_allowance_mm": ba, "outside_setback_mm": setback, "bend_deduction_mm": 2.0 * setback - ba}
