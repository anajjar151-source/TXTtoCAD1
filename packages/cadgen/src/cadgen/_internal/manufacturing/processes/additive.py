"""The 3D printing technologies and materials a ``printing`` study names, and the inherent strain each leaves.

A printed band shrinks as it cools or cures on the part below it; held by that part and the plate, it cannot, and
what it would have taken up is its inherent strain (:mod:`cadgen._internal.manufacturing.processes.inherent_strain`): an in-plane value
(across the layers, negative for a shrinkage) and one along the build direction. Along the build direction it is taken
as zero, the hypothesis of the cantilever calibrations of metal powder bed fusion: the next layer is laid at the
nominal height, which takes up the layer's own vertical shrinkage. In the plane:

- **metal powder bed fusion**: Ti-6Al-4V's is measured (calibrated on twin cantilevers); for the other alloys there is
  no published calibration to take, and the in-plane strain is the commercial *assumed strain*, the yield strength
  over the modulus (a strain scaling factor of 1): an estimate until the user calibrates it;
- **FDM**: the thermal strain α (T_set - T_chamber) of each layer cooling from where it sets (the glass transition of
  an amorphous polymer, the crystallisation of a semi-crystalline one) to the chamber's temperature;
- **SLS**: zero in the build. The bed holds the part between its crystallisation and its melting point, so the layers
  do not shrink one on another; the whole part shrinks as the cake cools after the build, which the printer's scale
  factors take up, and the warp of uneven cooling is not in this version;
- **resin**: the linear shrinkage of a layer's cure in the vat (its green state).

Units are the ones people write them in: MPa, 1/K, °C, mm. Sources per value: the manufacturing-sim skill's printing
reference. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

from cadgen._internal.fea.analyses.kinds import json_text

__all__ = ["MATERIALS", "PrintMaterial", "TECHNOLOGIES", "Technology", "lookup_material", "lookup_technology"]


@dataclass(frozen=True)
class Technology:
    key: str
    #: How a sentence names it: "metal powder bed fusion".
    words: str
    #: The study key that names its material: "alloy" or "polymer".
    material_key: str
    #: Built on a plate (or a resin printer's platform) it is fixed to; an SLS part floats in its powder.
    plate: bool
    #: A blade or roller spreads each layer over the part: an edge that rises past a layer can hit it.
    recoater: bool


TECHNOLOGIES: dict[str, Technology] = {technology.key: technology for technology in (
    Technology("fdm", "fused filament (FDM)", "polymer", plate=True, recoater=False),
    Technology("powder_bed_metal", "metal powder bed fusion", "alloy", plate=True, recoater=True),
    Technology("sls", "polymer powder bed fusion (SLS)", "polymer", plate=False, recoater=False),
    Technology("resin", "resin (SLA, DLP)", "polymer", plate=True, recoater=False),
)}

_TECHNOLOGY_ALIASES = {
    "fff": "fdm", "filament": "fdm", "lpbf": "powder_bed_metal", "slm": "powder_bed_metal", "dmls": "powder_bed_metal",
    "pbf_lb": "powder_bed_metal", "metal": "powder_bed_metal", "powder_bed": "powder_bed_metal", "mjf": "sls",
    "sla": "resin", "dlp": "resin", "msla": "resin",
}


@dataclass(frozen=True)
class PrintMaterial:
    key: str
    name: str
    #: The technology it prints in.
    technology: str
    #: Young's modulus and the yield strength as printed, MPa; Poisson's ratio.
    E: float
    nu: float
    yield_strength: float
    #: Its expansion coefficient, 1/K (FDM's thermal strain; ``None`` where the strain is not thermal).
    expansion: float | None
    #: The default layer thickness, mm.
    layer_mm: float
    #: The in-plane inherent strain (negative: a shrinkage); for FDM ``None``: α (T_set - T_chamber) per study.
    in_plane: float | None
    #: Where an FDM polymer sets as it cools, °C: its glass transition, or its crystallisation; ``None`` for the rest.
    sets_C: float | None = None
    #: How the in-plane strain was found, in words for the summary.
    basis: str = ""

    def strain_in_plane(self, chamber_C: float) -> float:
        """The in-plane inherent strain: the table's, or FDM's α (T_set - T_chamber)."""
        if self.in_plane is not None:
            return self.in_plane
        return -self.expansion * max(self.sets_C - chamber_C, 0.0)

    def as_dict(self) -> dict:
        return {"name": self.name, "youngs_GPa": round(self.E / 1000.0, 6), "poisson": self.nu,
                "yield_MPa": self.yield_strength, "expansion_per_K": self.expansion, "sets_at_C": self.sets_C}


_ASSUMED = "the yield strength over the modulus (assumed strain, scaling factor 1): calibrate it for your machine"


def _metal(key, name, E_GPa, nu, yield_MPa, alpha, layer_mm, in_plane=None, basis=_ASSUMED) -> PrintMaterial:
    strain = -yield_MPa / (E_GPa * 1000.0) if in_plane is None else in_plane
    return PrintMaterial(key, name, "powder_bed_metal", E_GPa * 1000.0, nu, yield_MPa, alpha, layer_mm, strain, None, basis)


def _filament(key, name, E_MPa, nu, yield_MPa, alpha, sets_C, words) -> PrintMaterial:
    return PrintMaterial(key, name, "fdm", E_MPa, nu, yield_MPa, alpha, 0.2, None, sets_C,
                         f"α (T_set - T_chamber), set at its {words}")


# Sources per value: the manufacturing-sim skill's printing reference ("The materials").
MATERIALS: dict[str, PrintMaterial] = {material.key: material for material in (
    _metal("316l", "Stainless steel 316L", 193, 0.29, 480, 16.0e-6, 0.04),
    _metal("ti-6al-4v", "Ti-6Al-4V", 113.8, 0.342, 1100, 8.6e-6, 0.06, -0.0056,
           "measured on twin cantilevers (60 µm layers, a 200 °C plate)"),
    _metal("alsi10mg", "AlSi10Mg", 70, 0.33, 230, 20.9e-6, 0.03),
    _metal("in718", "Inconel 718", 200, 0.294, 650, 13.0e-6, 0.04),
    _metal("17-4ph", "Stainless steel 17-4PH", 197, 0.272, 860, 10.8e-6, 0.04),
    _filament("pla", "PLA", 3500, 0.36, 60, 68e-6, 60, "glass transition"),
    _filament("petg", "PETG", 2100, 0.38, 50, 68e-6, 80, "glass transition"),
    _filament("abs", "ABS", 2200, 0.35, 40, 90e-6, 105, "glass transition"),
    _filament("asa", "ASA", 2000, 0.35, 45, 95e-6, 100, "glass transition"),
    _filament("pa", "Nylon (PA12 filament)", 1700, 0.40, 48, 110e-6, 150, "crystallisation"),
    _filament("pc", "Polycarbonate", 2300, 0.37, 60, 68e-6, 147, "glass transition"),
    PrintMaterial("pa12", "Nylon PA12 (SLS)", "sls", 1700, 0.40, 48, None, 0.1, 0.0, None,
                  "none in the build: the bed holds it between crystallisation and melting"),
    PrintMaterial("standard-resin", "Standard acrylate resin", "resin", 2500, 0.38, 50, None, 0.05, -0.01, None,
                  "a layer's linear cure shrinkage in the vat, about 1 %"),
)}

_MATERIAL_ALIASES = {
    "316": "316l", "ss316l": "316l", "stainless-316l": "316l", "ti64": "ti-6al-4v", "ti6al4v": "ti-6al-4v",
    "titanium": "ti-6al-4v", "ti-64": "ti-6al-4v", "alsi10": "alsi10mg", "aluminium": "alsi10mg", "aluminum": "alsi10mg",
    "inconel": "in718", "inconel-718": "in718", "718": "in718", "17-4": "17-4ph", "174ph": "17-4ph", "nylon": "pa",
    "pa6": "pa", "pa-12": "pa", "polycarbonate": "pc", "resin": "standard-resin", "standard": "standard-resin",
}


def _key(name: str) -> str:
    return "-".join(name.strip().lower().replace("_", " ").split())


def lookup_technology(name) -> Technology:
    """A printing technology by name; a ValueError naming ``technology`` and listing them otherwise."""
    key = _key(name).replace("-", "_") if isinstance(name, str) else None
    key = _TECHNOLOGY_ALIASES.get(key, key)
    if key not in TECHNOLOGIES:
        raise ValueError(f"technology: {json_text(name)} is not a printing technology cadgen knows; use one of "
                         f"{', '.join(TECHNOLOGIES)}")
    return TECHNOLOGIES[key]


def lookup_material(name, technology: Technology) -> PrintMaterial:
    """The technology's material by its table name or an alias; a ValueError naming the study key otherwise."""
    own = [key for key, material in MATERIALS.items() if material.technology == technology.key]
    where = technology.material_key
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{where}: name the {technology.words} material, one of {', '.join(own)}; got {json_text(name)}")
    key = _key(name)
    key = key if key in MATERIALS else _MATERIAL_ALIASES.get(key, key)
    if technology.key == "sls" and key == "pa":
        key = "pa12"
    if key not in MATERIALS or MATERIALS[key].technology != technology.key:
        raise ValueError(f"{where}: {name!r} is not a {technology.words} material cadgen knows; use one of {', '.join(own)}")
    return MATERIALS[key]
