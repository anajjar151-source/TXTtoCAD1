"""The workpiece materials a ``machining`` study names, the cutting force on them, and the chatter stability lobes.

A material is what a cut needs on top of what the solver needs: Kienzle's specific cutting force k_c1.1 (N/mm², at a
chip 1 mm thick and 1 mm wide) and its exponent m_c, so the specific cutting force at a chip h mm thick is
k_c = k_c1.1 h^(-m_c) and the force on a chip b mm wide is F_c = k_c b h = k_c1.1 b h^(1 - m_c); and the ratio K_r of
the force pushing the tool off the cut face (radial in milling, passive in turning) to that cutting force. A
:class:`CuttingMaterial` is a :class:`~cadgen._internal.fea.materials.Material` (E, ν, yield, density for the solver)
that carries them. Sources per value: the manufacturing-sim skill's machining reference ("The materials").

Milling (straight flutes, Altintas's convention): the cutter turns clockwise, a tooth's angle φ is measured from the
cut face's normal, its chip is f_z sin φ thick while it is engaged (from φ_st to φ_ex), and its tangential and radial
forces are Kienzle's and K_r times it. The stability of the cut is the zero-order (average) solution of Altintas and
Budak in the one direction the part is flexible in here, the cut face's normal: averaged over the engagement the
directional factor is α_yy, and the force along the normal per unit change of chip thickness is
K = -N K_t α_yy / (4π) (the tangential coefficient K_t is the specific cutting force at the mean chip thickness).
Turning is Tlusty's orthogonal cut: K = K_r k_c at the feed. Either way the limiting depth at a chatter frequency ω is
a_lim = -1 / (2 K Re G(ω)) where it is positive, G the part's transfer function at the cut along the normal, and the
spindle speeds that put it there are n = 60 ω / (z (ε + 2πk)) rpm with ε = π + 2 atan(Im G / Re G), k = 0, 1, 2, ...
(z the teeth, 1 for turning). Stdlib only at import; numeric imports live inside the functions.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any

from cadgen._internal.fea.analyses.kinds import json_text, number
from cadgen._internal.fea.materials import MATERIALS, Material

__all__ = [
    "CuttingMaterial", "KR_DEFAULT", "Lobes", "MILLING", "WORK_MATERIALS", "directional_yy", "engagement",
    "lookup_work_material", "mean_chip_mm", "milling_forces", "stability", "turning_forces", "work_material_from_spec",
]

#: The radial (milling) or passive (turning) force over the tangential: Altintas et al. (2008), Fig. 4, cut aluminium
#: with K_t = 900 and K_r = 270 N/mm², 0.3. One value for every material here (none of the tables gives it).
KR_DEFAULT = 0.3
#: Down (climb) milling, the default for finishing a wall, or up (conventional).
MILLING = ("down", "up")
_TWO_PI = 2.0 * math.pi


@dataclass(frozen=True)
class CuttingMaterial(Material):
    """A workpiece material: the solver's numbers and the cut's."""

    key: str = ""
    #: Kienzle's specific cutting force at h = b = 1 mm, N/mm² (MPa).
    kc11: float = 0.0
    #: Kienzle's exponent: k_c = k_c1.1 h^(-m_c).
    mc: float = 0.0
    #: The radial (passive) force over the tangential.
    kr: float = KR_DEFAULT
    #: The machinability group its k_c1.1 and m_c are read from, in words.
    group: str = ""
    #: k_c1.1 and m_c are an estimate, not a table's (no published Kienzle values for it).
    estimated: bool = False

    def kc(self, h_mm: float) -> float:
        """The specific cutting force at a chip ``h_mm`` thick, N/mm²: k_c1.1 h^(-m_c)."""
        return self.kc11 * h_mm ** (-self.mc)

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update({"kc11_MPa": self.kc11, "mc": self.mc, "kr": self.kr, "group": self.group,
                    "cutting_force_estimated": self.estimated})
        return out


def _from_fea(key: str, table_key: str, kc11: float, mc: float, group: str) -> CuttingMaterial:
    """A material the solver's table already has (E, ν, yield, density and the rest from it)."""
    base = MATERIALS[table_key]
    values = {f.name: getattr(base, f.name) for f in dataclasses.fields(Material)}
    return CuttingMaterial(**values, key=key, kc11=kc11, mc=mc, group=group)


def _own(key: str, name: str, E: float, nu: float, yield_MPa: float, kg_m3: float, kc11: float, mc: float, group: str,
         estimated: bool = False) -> CuttingMaterial:
    return CuttingMaterial(name, E, nu, yield_MPa, kg_m3 * 1e-12, key=key, kc11=kc11, mc=mc, group=group,
                           estimated=estimated)


_WROUGHT_AL = "wrought aluminium, hardenable (VDI 3323 group 22)"
_AUSTENITIC = "austenitic stainless steel (VDI 3323 group 14)"
# Sources per value: the manufacturing-sim skill's machining reference ("The materials").
WORK_MATERIALS: dict[str, CuttingMaterial] = {material.key: material for material in (
    _from_fea("aluminum-6061-t6", "aluminum-6061-t6", 800.0, 0.25, _WROUGHT_AL),
    _from_fea("aluminum-7075-t6", "aluminum-7075-t6", 800.0, 0.25, _WROUGHT_AL),
    _own("steel-1018", "Steel 1018", 205_000.0, 0.29, 370.0, 7_870, 1350.0, 0.21,
         "non-alloy steel under 0.25 % C (VDI 3323 group 1)"),
    _own("steel-1045", "Steel 1045", 200_000.0, 0.29, 310.0, 7_870, 1500.0, 0.22,
         "non-alloy steel, 0.25 % C and over (VDI 3323 group 2)"),
    _own("steel-4140", "Steel 4140 (annealed)", 205_000.0, 0.29, 415.0, 7_850, 1775.0, 0.24,
         "low-alloy steel, annealed (VDI 3323 group 6)"),
    _from_fea("stainless-304", "stainless-304", 2150.0, 0.20, _AUSTENITIC),
    _own("stainless-316", "Stainless steel 316", 193_000.0, 0.29, 200.0, 8_000, 2150.0, 0.20, _AUSTENITIC),
    _from_fea("titanium-6al-4v", "titanium-6al-4v", 2110.0, 0.22, "titanium, alpha-beta alloys (VDI 3323 group 37)"),
    _from_fea("brass-c360", "brass", 700.0, 0.27, "copper alloys, free cutting, over 1 % Pb (VDI 3323 group 26)"),
    _own("delrin", "Delrin (acetal, POM-H)", 3_103.0, 0.35, 75.8, 1_410, 200.0, 0.25,
         "a plastic: no published Kienzle values (an estimate)", estimated=True),
)}

_ALIASES = {
    **dict.fromkeys(("6061", "6061-t6", "al6061", "aluminium-6061-t6", "aluminum", "aluminium"), "aluminum-6061-t6"),
    **dict.fromkeys(("7075", "7075-t6", "al7075", "aluminium-7075-t6"), "aluminum-7075-t6"),
    **dict.fromkeys(("1018", "aisi-1018", "mild-steel", "low-carbon-steel"), "steel-1018"),
    **dict.fromkeys(("1045", "aisi-1045", "c45", "ck45"), "steel-1045"),
    **dict.fromkeys(("4140", "aisi-4140", "42crmo4"), "steel-4140"),
    **dict.fromkeys(("304", "ss304", "stainless", "1.4301"), "stainless-304"),
    **dict.fromkeys(("316", "316l", "ss316", "1.4401"), "stainless-316"),
    **dict.fromkeys(("titanium", "ti-6al-4v", "ti6al4v", "ti64", "grade-5-titanium"), "titanium-6al-4v"),
    **dict.fromkeys(("brass", "c360", "c36000", "free-cutting-brass", "cuzn39pb3"), "brass-c360"),
    **dict.fromkeys(("pom", "pom-h", "acetal", "delrin-150"), "delrin"),
}
#: The material object's keys: the solver's four, and the cut's three.
_OBJECT_KEYS = ("name", "E_MPa", "nu", "yield_MPa", "density_t_per_mm3", "kc11_MPa", "mc", "kr")


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").split())


def lookup_work_material(name: Any) -> CuttingMaterial:
    """A workpiece material by its table name or an alias; a ValueError naming ``material`` and the table otherwise."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"material: name the workpiece material, one of {', '.join(WORK_MATERIALS)}; got {json_text(name)}")
    key = _key(name)
    key = _ALIASES.get(key, key)
    if key not in WORK_MATERIALS:
        raise ValueError(f"material: {name!r} is not a material machining knows the cutting force of; use one of "
                         f"{', '.join(WORK_MATERIALS)}, or an object with E_MPa, nu, yield_MPa, density_t_per_mm3, "
                         "kc11_MPa and mc")
    return WORK_MATERIALS[key]


def work_material_from_spec(spec: Any) -> CuttingMaterial:
    """The study's ``material``: a table name, or an object that extends a table entry (``{"name": "6061",
    "kc11_MPa": 750}``) or gives every number (E_MPa, nu, yield_MPa, density_t_per_mm3, kc11_MPa, mc; kr optional)."""
    if isinstance(spec, str):
        return lookup_work_material(spec)
    if not isinstance(spec, dict):
        raise ValueError(f"material: a table name, one of {', '.join(WORK_MATERIALS)}, or an object with E_MPa, nu, "
                         "yield_MPa, density_t_per_mm3, kc11_MPa and mc")
    unknown = set(spec) - set(_OBJECT_KEYS)
    if unknown:
        raise ValueError(f"material: unknown keys {sorted(unknown)}; a machining material takes {', '.join(_OBJECT_KEYS)}")
    base = None
    if isinstance(spec.get("name"), str):
        key = _ALIASES.get(_key(spec["name"]), _key(spec["name"]))
        base = WORK_MATERIALS.get(key)
    if base is None:
        missing = [key for key in _OBJECT_KEYS[1:7] if key not in spec]
        if missing:
            raise ValueError(f"material.{missing[0]}: a material of its own needs E_MPa, nu, yield_MPa, "
                             "density_t_per_mm3, kc11_MPa and mc (kr optional)")

    def value(key: str, fallback: float, positive: bool = True) -> float:
        return number(spec[key], where=f"material.{key}", positive=positive) if key in spec else fallback

    E = value("E_MPa", base.E if base else 0.0)
    nu = value("nu", base.nu if base else 0.0, positive=False)
    if not 0 <= nu < 0.5:
        raise ValueError(f"material.nu: Poisson's ratio must be in [0, 0.5), got {nu:g}")
    yield_MPa = value("yield_MPa", base.yield_strength if base else 0.0)
    density = value("density_t_per_mm3", base.density if base else 0.0)
    kc11 = value("kc11_MPa", base.kc11 if base else 0.0)
    mc = value("mc", base.mc if base else 0.0, positive=False)
    if not 0 <= mc < 1:
        raise ValueError(f"material.mc: Kienzle's exponent is between 0 and 1 (about 0.2 to 0.3), got {mc:g}")
    kr = value("kr", base.kr if base else KR_DEFAULT, positive=False)
    if kr < 0:
        raise ValueError(f"material.kr: the radial force over the cutting force, 0 or more (about 0.3), got {kr:g}")
    name = base.name if base is not None else str(spec.get("name") or "Custom").strip() or "Custom"
    if base is not None:
        values = {f.name: getattr(base, f.name) for f in dataclasses.fields(Material)}
        values.update(name=name, E=E, nu=nu, yield_strength=yield_MPa, density=density)
        own_cut = "kc11_MPa" in spec or "mc" in spec
        return CuttingMaterial(**values, key=base.key, kc11=kc11, mc=mc, kr=kr,
                               group=("the study's own" if own_cut else base.group),
                               estimated=base.estimated and not own_cut)
    return CuttingMaterial(name, E, nu, yield_MPa, density, key="", kc11=kc11, mc=mc, kr=kr, group="the study's own")


# -- the cut -----------------------------------------------------------------------------------------

def turning_forces(material: CuttingMaterial, depth_mm: float, feed_mm: float) -> dict:
    """A turning cut's forces, N: the cutting (tangential) force F_c = k_c1.1 b h^(1 - m_c) on a chip ``depth_mm`` wide
    and ``feed_mm`` (per revolution) thick, and the passive force K_r F_c that pushes the part off the tool."""
    kc = material.kc(feed_mm)
    cutting = kc * depth_mm * feed_mm
    return {"kc_MPa": kc, "chip_mm": feed_mm, "tangential_N": cutting, "normal_N": material.kr * cutting,
            "resultant_N": math.hypot(cutting, material.kr * cutting)}


def engagement(diameter_mm: float, width_mm: float, milling: str) -> tuple[float, float]:
    """(φ_st, φ_ex), radians from the cut face's normal: up milling enters at 0 (the finished face, no chip) and leaves
    at arccos(1 - 2 a_e / D); down milling enters at π - that and leaves at π; a slot is engaged from 0 to π."""
    swept = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * width_mm / diameter_mm)))
    return (0.0, swept) if milling == "up" else (math.pi - swept, math.pi)


def mean_chip_mm(feed_mm: float, diameter_mm: float, width_mm: float) -> float:
    """The mean chip thickness over the engagement, mm: f_z (1 - cos φ_e) / φ_e = f_z (2 a_e / D) / arccos(1 - 2 a_e / D)."""
    swept = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * width_mm / diameter_mm)))
    return feed_mm * (1.0 - math.cos(swept)) / swept


def directional_yy(start: float, end: float, kr: float) -> float:
    """Altintas and Budak's averaged directional factor along the normal, α_yy = ½ [-cos 2φ - 2 K_r φ - K_r sin 2φ]
    from φ_st to φ_ex (-K_r π for a slot)."""
    def at(phi: float) -> float:
        return -math.cos(2 * phi) - 2 * kr * phi - kr * math.sin(2 * phi)

    return 0.5 * (at(end) - at(start))


def milling_forces(material: CuttingMaterial, *, diameter_mm: float, flutes: int, depth_mm: float, width_mm: float,
                   feed_mm: float, milling: str, samples: int = 720) -> dict:
    """A milling cut's forces on the part over one tooth period, straight flutes, Kienzle per tooth (the chip f_z sin φ,
    the tangential force k_c1.1 a_p h^(1 - m_c), the radial K_r times it), summed over the teeth in the cut.

    ``normal_N`` is the force along the cut face's inward normal at its extreme over the period (signed: up milling can
    pull the face toward the cutter), ``feed_N`` the force along the feed then, ``resultant_N`` the largest in-plane
    force over the period, ``tangential_N`` the largest one tooth's cutting force (at its thickest chip); ``kc_MPa`` is
    the specific cutting force at the mean chip thickness, the stability's K_t."""
    import numpy as np

    start, end = engagement(diameter_mm, width_mm, milling)
    pitch = _TWO_PI / flutes
    theta = np.linspace(0.0, pitch, samples, endpoint=False)
    normal = np.zeros(samples)
    feed = np.zeros(samples)
    for tooth in range(flutes):
        phi = np.mod(theta + tooth * pitch, _TWO_PI)
        engaged = (phi >= start) & (phi <= end)
        h = np.where(engaged, feed_mm * np.sin(phi), 0.0).clip(min=0.0)
        tangential = material.kc11 * depth_mm * h ** (1.0 - material.mc)
        radial = material.kr * tangential
        # The force on the part (the tool's, reversed), along the feed and into the cut face.
        feed += tangential * np.cos(phi) + radial * np.sin(phi)
        into = radial * np.cos(phi) - tangential * np.sin(phi)
        normal += into if milling == "up" else -into
    extreme = int(np.abs(normal).argmax())
    h_max = feed_mm * max(math.sin(min(max(math.pi / 2, start), end)), math.sin(start), math.sin(end))
    h_mean = mean_chip_mm(feed_mm, diameter_mm, width_mm)
    return {
        "kc_MPa": material.kc(h_mean), "chip_mm": h_mean, "chip_max_mm": h_max,
        "tangential_N": material.kc11 * depth_mm * h_max ** (1.0 - material.mc),
        "normal_N": float(normal[extreme]), "feed_N": float(feed[extreme]),
        "resultant_N": float(np.hypot(normal, feed).max()), "mean_normal_N": float(normal.mean()),
        "engagement_rad": (start, end),
    }


# -- chatter -----------------------------------------------------------------------------------------

@dataclass
class Lobes:
    """The stability lobes of a cut: the limiting depth at each chatter frequency, and its envelope over spindle speed."""

    #: (F,) chatter frequencies, rad/s, and the limiting depth there, mm (inf where the cut cannot chatter).
    omega: Any
    depth_mm: Any
    #: (F,) the phase between the waves on the surface, rad, in (0, 2π).
    epsilon: Any
    #: (S,) spindle speeds, rpm, and the depth the cut stays stable to at each (inf where no lobe reaches).
    rpm: Any
    envelope_mm: Any
    #: The lowest limiting depth at any speed, mm, and the chatter frequency it is at, rad/s.
    absolute_mm: float
    absolute_omega: float
    lobes: int


def stability(omega, frf, coefficient: float, teeth: int, rpm, *, cap_mm: float | None = None,
              max_lobes: int = 50_000) -> Lobes:
    """The lobes of a cut whose force along the normal grows by ``coefficient`` (N/mm² of chip, K) per mm of chip
    thickness, on a part whose transfer function along the normal is ``frf`` (mm/N) at ``omega`` (rad/s, ascending).

    a_lim(ω) = -1 / (2 K Re G(ω)) where positive; ε = π + 2 atan(Im G / Re G); each lobe k puts it at
    n = 60 ω / (z (ε + 2πk)) rpm. ``rpm`` is the grid the envelope (the least a_lim over every lobe) is read on: each
    lobe is drawn segment by segment between neighbouring frequencies, so none falls between two speeds. Only the
    stretches of a lobe under ``cap_mm`` are drawn (a depth no one cuts needs no lobe): the envelope is inf where no
    lobe comes under it, so every lobe down to the slowest speed is drawn however many that takes."""
    import numpy as np

    omega = np.asarray(omega, dtype=float)
    G = np.asarray(frf, dtype=complex)
    rpm = np.asarray(rpm, dtype=float)
    real, imag = G.real, G.imag
    with np.errstate(divide="ignore", invalid="ignore"):
        depth = -1.0 / (2.0 * coefficient * real)
        epsilon = np.pi + 2.0 * np.arctan(imag / real)
    valid = np.isfinite(depth) & (depth > 0) & np.isfinite(epsilon)
    depth = np.where(valid, depth, np.inf)
    envelope = np.full(len(rpm), np.inf)
    drawn = valid if cap_mm is None else valid & (depth <= cap_mm)
    pairs = np.flatnonzero(valid[:-1] & valid[1:] & (drawn[:-1] | drawn[1:]))
    lobes = 0
    if len(pairs) and len(rpm):
        low = float(rpm.min())
        for k in range(max_lobes):
            speeds = 60.0 * omega / (teeth * (epsilon + _TWO_PI * k))
            n0, n1 = speeds[pairs], speeds[pairs + 1]
            a0, a1 = depth[pairs], depth[pairs + 1]
            lo, hi = np.minimum(n0, n1), np.maximum(n0, n1)
            first = np.searchsorted(rpm, lo, side="left")
            last = np.searchsorted(rpm, hi, side="right")
            counts = np.maximum(last - first, 0)
            lobes = k + 1
            if counts.sum():
                segment = np.repeat(np.arange(len(pairs)), counts)
                offsets = np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts, counts)
                grid = first[segment] + offsets
                span = n1[segment] - n0[segment]
                with np.errstate(divide="ignore", invalid="ignore"):
                    t = np.where(span != 0, (rpm[grid] - n0[segment]) / span, 0.0)
                np.minimum.at(envelope, grid, a0[segment] + t * (a1[segment] - a0[segment]))
            if float(hi.max()) < low:  # every later lobe is slower still
                break
    finite = np.isfinite(depth)
    lowest = int(np.argmin(depth)) if finite.any() else 0
    return Lobes(omega=omega, depth_mm=depth, epsilon=epsilon, rpm=rpm, envelope_mm=envelope,
                 absolute_mm=float(depth[lowest]) if finite.any() else math.inf,
                 absolute_omega=float(omega[lowest]) if finite.any() else 0.0, lobes=lobes)
