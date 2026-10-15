"""3D printing (lite): a part built layer by layer, each height band shrinking on the part below it.

The study names the ``technology`` (``fdm``, ``powder_bed_metal``, ``sls``, ``resin``) and its material (``alloy`` for
metal, ``polymer`` for the rest; :mod:`cadgen._internal.manufacturing.processes.additive`). The build direction is ``build_direction``
(+Z by default) and the plate is the part's lowest face along it. The part is cut into ``bands`` height bands (12 by
default); each is born on the bands below, as they have deformed, and carries the technology's inherent strain (in the
plane across the layers, and along the build), the plate holding the bottom
(:class:`cadgen._internal.manufacturing.processes.inherent_strain.Build`). Once built, the plate lets go (``release_from_plate``, default
true) and the part springs back. An SLS part has no plate: it floats in its powder, held only against rigid motion.

It writes the residual stress (von Mises), the distortion and what is printed so far at every band, and off the plate,
as frames, so the viewer's Play builds it. Its findings are a checklist: the warp off the plate and the distortion
against ``tolerance_mm``, the residual stress against yield (a crack and plate-detach risk), a metal edge rising past
a layer (recoater collision), the plate's pull against the bed's adhesion (FDM), and plate theory as the hand check
(the first band against a band fully held).
Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import (
    AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext, frame_attributes, max_frames, plan_value,
    xyz,
)
from cadgen._internal.manufacturing.processes.base import Process, finding_of

__all__ = ["LIMITS", "PrintingInputs", "PrintingProcess"]

#: This process's findings, held to its closed set (``base.FINDING_TYPES``).
finding = finding_of("printing")

LIMITS = (
    "Layers are lumped into height bands, each carrying one inherent strain for the whole part: the scan pattern, the "
    "heat that builds up and the plate's temperature are in that number, not computed; a metal's is an estimate until "
    "it is calibrated for the machine.",
    "Linear elastic: where the stress passes yield the real part yields and holds about yield, so a stress past yield "
    "is an upper bound and the distortion beside it an estimate.",
    "The plate is rigid and supports are not modelled (a region that starts in mid-air is held where it starts, as a "
    "support would hold it); a real plate bends under the part's pull, which adds to its curl once it is cut off.",
    "A recoater rise is a band's, of many layers, not one layer's: a rise past a layer is a risk to confirm, not a "
    "crash.",
    "SLS shrinks nothing in the build (its bed is held above crystallisation); the warp of the cake's uneven cooling "
    "afterwards is not simulated.",
)
#: Bands the part is cut into when the study does not say, and the most it takes.
BANDS, MOST_BANDS = 12, 40
#: The plate-stress hand check: the first band's middle within this factor of the fully held band's stress.
PLATE_FACTOR = 2.0
#: Strains past this are not a process's (a few percent at most).
MOST_STRAIN = 0.05
STRAIN_KEYS = {"in_plane", "build"}


@dataclass(frozen=True)
class PrintingInputs(Inputs):
    technology: Any = None
    material: Any = None
    #: The build direction, a unit vector.
    direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    bands: int = BANDS
    release: bool = True
    #: The study's tolerance, mm; ``None`` for ISO 2768-2 K's by the part's size.
    tolerance_mm: float | None = None
    layer_mm: float = 0.0
    #: FDM: the chamber's temperature, °C (25, an open printer, when the study does not say).
    chamber_C: float | None = None
    adhesion_MPa: float | None = None
    #: The inherent strain in the plane and along the build; ``given`` when the study set it.
    in_plane: float = 0.0
    along: float = 0.0
    given: bool = False

    def strain_words(self) -> str:
        return "the study's (calibrated)" if self.given else self.material.basis


def _unit(raw, where: str) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"{where}: the build direction as [x, y, z], like [0, 0, 1]")
    vector = [kinds.number(value, where=where) for value in raw]
    length = math.sqrt(sum(c * c for c in vector))
    if not length > 0:
        raise ValueError(f"{where}: [0, 0, 0] points nowhere; give the direction the part grows in, like [0, 0, 1]")
    return tuple(c / length for c in vector)


def _parse_strain(raw) -> tuple[float | None, float | None]:
    if not isinstance(raw, dict):
        raise ValueError('inherent_strain: an object like {"in_plane": -0.003, "build": 0} (negative: a shrinkage)')
    kinds.known(raw, STRAIN_KEYS, "inherent_strain", "it takes in_plane and build (negative: a shrinkage)")
    out = []
    for key in ("in_plane", "build"):
        if key not in raw:
            out.append(None)
            continue
        value = kinds.number(raw[key], where=f"inherent_strain.{key}")
        if abs(value) > MOST_STRAIN:
            raise ValueError(f"inherent_strain.{key}: {value:g} is a strain of {abs(value):.0%}; a process's is a few "
                             "tenths of a percent (-0.003), at most a few percent")
        out.append(value)
    return out[0], out[1]


class PrintingProcess(Process):
    name: ClassVar[str] = "printing"
    word: ClassVar[str] = "3D printing"
    extras_word: ClassVar[str] = "printing"
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "technology", "alloy", "polymer", "build_direction", "bands", "release_from_plate", "tolerance_mm",
        "layer_thickness_mm", "chamber_temperature_C", "bed_adhesion_MPa", "inherent_strain",
    })
    mesh_orders: ClassVar[tuple[int, ...]] = (2, 1)
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "residual stress (von Mises)", "MPa", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "distortion", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("printed", "_PRINTED", "printed so far", "", per_frame=True),
    )
    checks: ClassVar[tuple] = ()
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "frame", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "displacement", "printed"]},
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "defeature", "linear_elements")
    noun: ClassVar[str] = "this print"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> PrintingInputs:
        from cadgen._internal.manufacturing.processes.additive import TECHNOLOGIES, lookup_material, lookup_technology

        if "material" in document:
            raise ValueError("study.material: a printing study names its material by the technology: 'alloy' for "
                             "powder_bed_metal, 'polymer' for fdm, sls and resin")
        for key in ("parts", "connections"):
            if key in document:
                raise ValueError(f"study.{key}: a printing study solves one part; solve one occurrence with --occurrence")
        if "technology" not in document:
            raise ValueError(f"study.technology: how it is printed, one of {', '.join(TECHNOLOGIES)}")
        technology = lookup_technology(document["technology"])
        other = "polymer" if technology.material_key == "alloy" else "alloy"
        if other in document:
            raise ValueError(f"study.{other}: {technology.key} prints a{'n' if technology.material_key == 'alloy' else ''} "
                             f"{technology.material_key}; name it with '{technology.material_key}'")
        if technology.material_key not in document:
            raise ValueError(f"study.{technology.material_key}: what it is printed in, for {technology.key}")
        material = lookup_material(document[technology.material_key], technology)
        direction = _unit(document.get("build_direction", [0, 0, 1]), "build_direction")
        bands = kinds.whole(document.get("bands", BANDS), where="bands",
                            words=f"how many height bands to build it in, 2 to {MOST_BANDS}", low=2, high=MOST_BANDS)
        release = document.get("release_from_plate", True)
        if not isinstance(release, bool):
            raise ValueError(f"release_from_plate: true or false, got {kinds.json_text(release)}")
        tolerance = None
        if "tolerance_mm" in document:
            tolerance = kinds.number(document["tolerance_mm"], where="tolerance_mm", positive=True)
        layer = material.layer_mm
        if "layer_thickness_mm" in document:
            layer = kinds.number(document["layer_thickness_mm"], where="layer_thickness_mm", positive=True)
        chamber = None
        for key in ("chamber_temperature_C", "bed_adhesion_MPa"):
            if key in document and technology.key != "fdm":
                raise ValueError(f"{key}: FDM's alone; {technology.key} does not take it")
        if technology.key == "fdm":
            chamber = 25.0
            if "chamber_temperature_C" in document:
                chamber = kinds.number(document["chamber_temperature_C"], where="chamber_temperature_C")
                if chamber >= material.sets_C:
                    raise ValueError(f"chamber_temperature_C: {chamber:g} °C is not below where {material.name} sets "
                                     f"({material.sets_C:g} °C): it would never set")
        adhesion = None
        if "bed_adhesion_MPa" in document:
            adhesion = kinds.number(document["bed_adhesion_MPa"], where="bed_adhesion_MPa", positive=True)
        in_plane, along, given = material.strain_in_plane(chamber or 0.0), 0.0, False
        if "inherent_strain" in document:
            own_plane, own_along = _parse_strain(document["inherent_strain"])
            given = True
            in_plane = in_plane if own_plane is None else own_plane
            along = along if own_along is None else own_along
        return PrintingInputs((), (), False, technology=technology, material=material, direction=direction, bands=bands,
                              release=release, tolerance_mm=tolerance, layer_mm=layer, chamber_C=chamber,
                              adhesion_MPa=adhesion, in_plane=in_plane, along=along, given=given)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: PrintingInputs):
        """A linear solve per band and one for the release, the stiffness growing band by band."""
        from cadgen._internal.fea import fit

        return fit.solid_estimate(ctx, passes=inputs.bands + 2)

    def apply(self, rung, ctx: SolveContext, inputs: PrintingInputs):
        from cadgen._internal.fea import fit

        return fit.apply_generic(rung, self, ctx, inputs)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: PrintingInputs) -> AnalysisResult:
        import time

        import numpy as np
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import connected_components

        from cadgen._internal.manufacturing.processes import inherent_strain as IS
        from cadgen._internal.fea.analyses.thermal import space_result
        from cadgen._internal.fea.materials import Material

        if ctx.assembly is not None:
            raise ValueError("printing: the document holds several parts; a printing study solves one, so name it with "
                             "--occurrence")
        started = time.perf_counter()
        space, volume = ctx.space, ctx.volume
        stock, technology = inputs.material, inputs.technology
        material = Material(stock.name, stock.E, stock.nu, stock.yield_strength, 1e-9)
        d = np.asarray(inputs.direction)
        points = space.dof_locations
        height = points @ d
        z0, z1 = float(height.min()), float(height.max())
        tall = z1 - z0
        centroids = IS.element_centroids(space)
        band_mm = tall / inputs.bands
        band_of = np.clip(np.floor((centroids @ d - z0) / band_mm).astype(np.int64), 0, inputs.bands - 1)
        tolerance_close = max(1e-6 * volume.bbox_diagonal, 0.02 * volume.max_h)
        triangles = np.asarray(space.boundary_quadratic)
        corners = triangles[:, :3]
        plate_rows = (height[corners] <= z0 + tolerance_close).all(axis=1)
        tri = points[corners[plate_rows]]
        plate_area = float(0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum())
        if technology.plate and not plate_area > 1e-6 * volume.bbox_diagonal ** 2:
            raise ValueError(f"printing: the part has no flat face at its lowest point along build_direction "
                             f"{[round(c, 4) for c in inputs.direction]}, so it cannot sit on the build plate; turn it "
                             "(build_direction) so a flat face is down, or give it a flat base")
        plate_nodes = np.unique(triangles[plate_rows])
        e1, e2 = _in_plane_axes(d)
        strain_one = inputs.in_plane * (np.outer(e1, e1) + np.outer(e2, e2)) + inputs.along * np.outer(d, d)

        method = {"iterative": "iterative", "matrix_free": "iterative"}.get(plan_value(ctx, "solver", "direct"))
        build = IS.Build(space, material, method=method, log=ctx.log)
        held_vertices = np.zeros(space.vertices, dtype=bool)
        if technology.plate:
            build.hold(IS.vector_dofs(space, plate_nodes))
            held_vertices[plate_nodes[plate_nodes < space.vertices]] = True
        tets = np.asarray(space.mesh.t)                      # (4, E) corner vertices
        born = np.zeros(tets.shape[1], dtype=bool)
        supports: list[dict] = []
        frames: list[dict] = []
        rise = {"mm": 0.0, "at": None, "band": None}
        nodal_mask = np.zeros(space.scalar_count, dtype=bool)
        element_dofs = space.scalar.element_dofs
        timings = {"assemble_s": time.perf_counter() - started}
        started = time.perf_counter()

        def components(mask):
            """Each vertex's connected piece of the elements ``mask``, -1 off them."""
            chosen = tets[:, mask]
            count = chosen.shape[1]
            if count == 0:
                return np.full(space.vertices, -1)
            incidence = csr_matrix((np.ones(4 * count), (np.repeat(np.arange(count), 4), chosen.T.ravel())),
                                   shape=(count, space.vertices))
            _, labels = connected_components(incidence.T @ incidence, directed=False)
            out = np.full(space.vertices, -1)
            used = np.unique(chosen)
            out[used] = labels[used]
            return out

        for k in range(inputs.bands):
            elements = np.flatnonzero(band_of == k)
            if len(elements) == 0:
                continue
            after = born.copy()
            after[elements] = True
            pieces = components(after)
            for piece in np.unique(pieces[pieces >= 0]):
                vertices = np.flatnonzero(pieces == piece)
                if held_vertices[vertices].any():
                    continue
                if technology.plate:
                    low = IS.lowest_nodes(space, vertices, d, max(0.25 * band_mm, tolerance_close))
                    build.hold(IS.vector_dofs(space, low))
                    held_vertices[low] = True
                    supports.append({"at": xyz(points[low].mean(axis=0)), "band": k + 1})
                else:
                    held = IS.hold_free(space, vertices)
                    build.hold(held)
                    held_vertices[vertices] = True
            born = after
            du = build.add(elements, np.repeat(strain_one[:, :, None], len(elements), axis=2))
            nodal_mask[np.unique(element_dofs[:, elements])] = True
            step = space.nodal(du)
            top_edge = z0 + (k + 1) * band_mm
            top = np.unique(element_dofs[:, elements])
            top = top[height[top] >= top_edge - 0.5 * band_mm]
            if len(top):
                upward = step[top] @ d
                peak = int(np.argmax(upward))
                if upward[peak] > rise["mm"]:
                    rise = {"mm": float(upward[peak]), "at": xyz(points[top[peak]]), "band": k + 1}
            sigma = build.stress()
            frames.append({"label": f"Band {k + 1}/{inputs.bands} · {(k + 1) * band_mm:.3g} mm", "value": float(k + 1),
                           "displacement": space.nodal(build.u), "von_mises": IS.nodal_von_mises(space, sigma),
                           "printed": nodal_mask.astype(float)})
            if ctx.log:
                ctx.log(f"printed band {k + 1} of {inputs.bands}")
        sigma_built = build.stress()
        built = frames[-1]
        reactions = space.nodal(build.reactions())
        released = None
        if inputs.release and technology.plate:
            pieces = components(born)
            keep = np.concatenate([IS.hold_free(space, np.flatnonzero(pieces == piece))
                                   for piece in np.unique(pieces[pieces >= 0])])
            build.release(keep)
            sigma_released = build.stress()
            released = {"label": "Off the plate", "value": float(inputs.bands + 1), "displacement": space.nodal(build.u),
                        "von_mises": IS.nodal_von_mises(space, sigma_released), "printed": nodal_mask.astype(float)}
            frames.append(released)
        timings["solve_s"] = time.perf_counter() - started
        started = time.perf_counter()

        # What a person measures: the distortion with the part's rigid motion taken out (off the plate), the bottom's
        # flatness off the plate, the stress against yield, the plate's pull.
        final = released if released is not None else built
        shape = final["displacement"] - (IS.rigid_part(points, final["displacement"]) if released is not None else 0.0)
        moved = np.linalg.norm(shape, axis=1)
        warp = None
        if released is not None:
            warp = _flatness(points[plate_nodes], shape[plate_nodes], d)
            warp["at"] = xyz(points[plate_nodes][warp.pop("index")])
        vm = built["von_mises"]
        ninety_nine = float(np.quantile(vm[nodal_mask], 0.99)) if nodal_mask.any() else 0.0
        pull = (_plate_pull(space, triangles[plate_rows], reactions, d, max(band_mm, 2.0 * volume.max_h))
                if technology.plate else None)
        size = float(max(np.ptp(points, axis=0)))
        tolerance = inputs.tolerance_mm if inputs.tolerance_mm is not None else IS.default_tolerance_mm(size)
        hand = _hand_check(space, material, sigma_built, born, band_of, d, inputs)
        timings["post_s"] = time.perf_counter() - started

        attributes = {"von_mises": "_VON_MISES", "displacement": "_DISPLACEMENT", "printed": "_PRINTED"}
        shown = _frames_kept(len(frames), max_frames(ctx))
        frames = [frames[i] for i in shown]
        series = Series(kind="time", unit="", default=len(frames) - 1, frames=[
            SeriesFrame(value=frame["value"], label=frame["label"], attributes=frame_attributes(attributes, i))
            for i, frame in enumerate(frames)
        ])
        frame_fields = {name: [frame[name] for frame in frames] for name in attributes}
        result = space_result(
            space, {name: values[0] for name, values in frame_fields.items()}, deformation=frame_fields["displacement"][0],
            series=series, frame_fields=frame_fields, solver=build.how, timings=timings, warnings=list(build.warnings),
            curves={"max_distortion_mm": {"x": [frame["value"] for frame in frames], "x_unit": "band",
                                          "y": [round(float(np.linalg.norm(frame["displacement"], axis=1).max()), 6)
                                                for frame in frames], "y_unit": "mm"}},
            scalars={"height_mm": tall, "band_mm": band_mm, "rise": rise, "supports": supports, "warp": warp,
                     "shape_max_mm": float(moved.max()), "shape_at": xyz(points[int(moved.argmax())]),
                     "released": released is not None, "vm_built_max": float(vm.max()),
                     "vm_built_at": xyz(points[int(vm.argmax())]), "vm_built_p99": ninety_nine,
                     "vm_final_max": float(final["von_mises"].max()), "pull": pull, "tolerance_mm": tolerance,
                     "tolerance_given": inputs.tolerance_mm is not None, "size_mm": size,
                     "hand": hand, "axis_sizes": [float(x) for x in np.ptp(points, axis=0)], "analysis_warnings": []},
        )
        return result

    # -- findings ------------------------------------------------------------------------------------

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: PrintingInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        s = result.scalars
        found = []
        tolerance, source = s["tolerance_mm"], _tolerance_words(s)
        fix = self._fix(inputs, s)
        warp = s["warp"]
        if warp is not None:
            measured = {"value": round(warp["mm"], 6), "limit": tolerance, "units": "mm", "pass_when": "below",
                        "quantity": "bottom out of flat"}
            item = [{"text": "lifts most here", "ref": None, "at": warp["at"]}]
            if warp["mm"] > tolerance:
                found.append(finding("error", "warp", f"Off the plate it curls: its bottom lifts {warp['mm']:.3g} mm out "
                                     f"of flat at {warp['at']} mm, past the {tolerance:g} mm tolerance ({source})",
                                     "the bottom face's flatness once the plate lets go, its rigid tilt taken out", item,
                                     measured=measured, fix=fix))
            else:
                found.append(finding("info", "warp", f"Off the plate its bottom stays flat to {warp['mm']:.3g} mm, within "
                                     f"the {tolerance:g} mm tolerance ({source})",
                                     "the bottom face's flatness once the plate lets go, its rigid tilt taken out", item,
                                     measured=measured))
        when = "off the plate" if s["released"] else ("as printed, on the plate" if inputs.technology.plate else "as printed")
        measured = {"value": round(s["shape_max_mm"], 6), "limit": tolerance, "units": "mm", "pass_when": "below",
                    "quantity": "distortion"}
        item = [{"text": "distorts most here", "ref": None, "at": s["shape_at"]}]
        kind = "release_distortion" if s["released"] else "distortion"
        detail = ("the largest distance any point moved from the CAD, the part's rigid motion taken out"
                  if s["released"] else "the largest distance any point moved from the CAD while the plate holds it")
        if s["shape_max_mm"] > tolerance:
            found.append(finding("error", kind, f"{when.capitalize()} it distorts {s['shape_max_mm']:.3g} mm at "
                                 f"{s['shape_at']} mm, past the {tolerance:g} mm tolerance ({source})", detail, item,
                                 measured=measured, fix=fix))
        else:
            found.append(finding("info", kind, f"{when.capitalize()} it distorts {s['shape_max_mm']:.3g} mm at most, "
                                 f"within the {tolerance:g} mm tolerance ({source})", detail, item, measured=measured))
        found.append(self._stress(inputs, s))
        if inputs.technology.recoater:
            found.append(self._recoater(inputs, s))
        if inputs.technology.key == "fdm" and s["pull"] is not None:
            found.append(self._pull(inputs, s))
        if s["supports"]:
            count = len(s["supports"])
            found.append(finding("info", "starts_in_air", f"{count} region{'s' if count != 1 else ''} start{'' if count != 1 else 's'} "
                                 f"in mid-air (the first at {s['supports'][0]['at']} mm, band {s['supports'][0]['band']}): "
                                 "held where it starts, as a support would hold it; give it supports to print it",
                                 "supports are not modelled; $dfam-check reviews overhangs and supports",
                                 [{"text": "starts in mid-air", "ref": None, "at": item_["at"]} for item_ in s["supports"]]))
        if inputs.technology.key == "sls":
            found.append(finding("info", "sls_no_build_shrinkage", "SLS: the bed holds the part above crystallisation, so "
                                 "no band shrinks on another and nothing distorts in the build; the warp of thick flat areas "
                                 "as the cake cools afterwards is not in this version",
                                 "check thick flat areas against the printer's design guide ($dfam-check measures them)"))
        found.append(self._hand_check(inputs, s))
        return found

    def _fix(self, inputs: PrintingInputs, s: dict) -> dict:
        """The change most likely to bring the distortion within tolerance, as the agent applies it."""
        material, technology = inputs.material, inputs.technology
        worst = max(s["warp"]["mm"] if s["warp"] else 0.0, s["shape_max_mm"])
        ratio = s["tolerance_mm"] / worst if worst > 0 else 1.0
        where = [s["warp"]["at"]] if s["warp"] else [s["shape_at"]]
        if technology.key == "fdm" and not inputs.given:
            gap = material.sets_C - inputs.chamber_C
            target = material.sets_C - ratio * gap
            if target - inputs.chamber_C >= 5.0:
                target = round(min(target, material.sets_C - 5.0))
                return {"action": "raise_chamber_temperature",
                        "summary": f"Print it enclosed at about {target:g} °C (its shrinkage falls with the gap to the "
                                   f"{material.sets_C:g} °C where {material.name} sets), or in a polymer that warps "
                                   "less; a brim holds the corners down",
                        "where": where, "params": {"chamber_temperature_C": target}}
        best = _shortest_axis(s)
        if best is not None and any(abs(a - b) > 1e-6 for a, b in zip(best, inputs.direction)):
            return {"action": "change_orientation",
                    "summary": "Turn it so its shortest side is along the build direction: a squat part keeps its "
                               "shrinkage locked in evenly and curls less once it is cut off",
                    "where": where, "params": {"build_direction": [round(c, 6) for c in best]}}
        if technology.key == "powder_bed_metal":
            return {"action": "stress_relieve",
                    "summary": "Stress-relieve it on the plate before it is cut off, so the stress the plate holds is "
                               "gone before it can curl it",
                    "where": where, "params": {"before_release": True}}
        return {"action": "add_rib", "summary": "Stiffen it along its length (a rib, or a thicker section) so the "
                                                "shrinkage bends it less", "where": where, "params": {}}

    def _stress(self, inputs: PrintingInputs, s: dict) -> dict:
        material = inputs.material
        value, peak, at = s["vm_built_p99"], s["vm_built_max"], s["vm_built_at"]
        measured = {"value": round(value, 4), "limit": material.yield_strength, "units": "MPa", "pass_when": "below",
                    "quantity": "residual stress (99th percentile)"}
        item = [{"text": "the peak residual stress", "ref": None, "at": at}]
        pull = s["pull"]
        pull_words = (f"; the plate pulls hardest, {pull['MPa']:.3g} MPa, at {pull['at']} mm" if pull else "")
        detail = (f"von Mises as printed: {value:.4g} MPa at the 99th percentile, {peak:.4g} MPa at the peak (a corner "
                  f"against the plate is singular){pull_words}")
        if value > material.yield_strength:
            metal = inputs.technology.key == "powder_bed_metal"
            risk = ("it may crack, or tear off its plate or supports" if metal
                    else "it may crack or peel off the plate")
            return finding("warning", "residual_stress", f"As printed the residual stress reaches {value:.4g} MPa, past "
                           f"{material.name}'s {material.yield_strength:g} MPa yield: in the part it yields and holds "
                           f"about yield, and {risk}", detail, item, measured=measured,
                           fix=self._stress_fix(inputs, s, at, material.yield_strength / value))
        return finding("info", "residual_stress", f"As printed the residual stress stays under {material.name}'s "
                       f"{material.yield_strength:g} MPa yield ({value:.4g} MPa at the 99th percentile)", detail, item,
                       measured=measured)

    def _stress_fix(self, inputs: PrintingInputs, s: dict, at, ratio: float) -> dict:
        """What brings the residual stress under yield: a metal stress-relieved on its plate; an FDM polymer printed
        warmer, its shrinkage (and so its stress) falling with the gap to where it sets; else a turn."""
        material = inputs.material
        if inputs.technology.key == "powder_bed_metal":
            return {"action": "stress_relieve", "summary": "Stress-relieve it on the plate before it is cut off, and "
                    "soften the corner it peaks at (a fillet where it meets the plate)", "where": [at],
                    "params": {"before_release": True}}
        if inputs.technology.key == "fdm" and not inputs.given:
            target = material.sets_C - 0.9 * ratio * (material.sets_C - inputs.chamber_C)
            if target - inputs.chamber_C >= 5.0:
                target = round(min(target, material.sets_C - 5.0))
                return {"action": "raise_chamber_temperature", "summary": f"Print it enclosed at about {target:g} °C, so "
                        f"each layer shrinks less as it cools from the {material.sets_C:g} °C where it sets",
                        "where": [at], "params": {"chamber_temperature_C": target}}
        best = _shortest_axis(s)
        return {"action": "change_orientation", "summary": "Turn it so less of it is held flat on the plate, its shortest "
                "side along the build direction", "where": [at],
                "params": {"build_direction": [round(c, 6) for c in best]} if best else {}}

    def _recoater(self, inputs: PrintingInputs, s: dict) -> dict:
        rise, layer = s["rise"], inputs.layer_mm
        measured = {"value": round(rise["mm"], 6), "limit": layer, "units": "mm", "pass_when": "below",
                    "quantity": "a band's top rising"}
        items = [{"text": "rises most here", "ref": None, "at": rise["at"]}] if rise["at"] else []
        if rise["mm"] > layer:
            return finding("warning", "recoater_collision", f"Band {rise['band']}'s top edge rises {rise['mm']:.3g} mm at "
                           f"{rise['at']} mm as it is printed, past the {layer:g} mm layer: the recoater may hit it",
                           "the rise of each band's top along the build direction while it is printed; a band holds many "
                           "layers, so this is a risk to confirm", items, measured=measured, fix={
                               "action": "support", "summary": "Support the edge that rises (or turn the part so that "
                               "edge is not a long free edge across the recoater's path)", "where": [rise["at"]],
                               "params": {}})
        return finding("info", "recoater_collision", f"No band's top rises past the {layer:g} mm layer as it is printed "
                       f"({rise['mm']:.3g} mm at most): clear of the recoater",
                       "the rise of each band's top along the build direction while it is printed", items,
                       measured=measured)

    def _pull(self, inputs: PrintingInputs, s: dict) -> dict:
        pull, adhesion = s["pull"], inputs.adhesion_MPa
        item = [{"text": "the plate pulls hardest here", "ref": None, "at": pull["at"]}]
        detail = (f"the plate's pull on the part's bottom at the end of the print, per area, averaged within "
                  f"{pull['radius_mm']:.2g} mm of where it pulls hardest (at a sharp corner itself it is singular)")
        if adhesion is None:
            return finding("info", "bed_adhesion", f"The bed must hold its bottom down with up to {pull['MPa']:.3g} MPa at "
                           f"{pull['at']} mm; give bed_adhesion_MPa to judge it against the bed", detail, item)
        measured = {"value": round(pull["MPa"], 6), "limit": adhesion, "units": "MPa", "pass_when": "below",
                    "quantity": "pull on the bed"}
        if pull["MPa"] > adhesion:
            return finding("warning", "bed_adhesion", f"Its corner pulls on the bed with {pull['MPa']:.3g} MPa at "
                           f"{pull['at']} mm, past the bed's {adhesion:g} MPa: it may lift off the bed during the print",
                           detail, item, measured=measured, fix={
                               "action": "add_brim", "summary": "Add a brim or mouse ears at that corner, or a rounded "
                               "corner, and keep the bed clean and at temperature", "where": [pull["at"]],
                               "params": {"brim_mm": 5}})
        return finding("info", "bed_adhesion", f"The bed holds it: the pull peaks at {pull['MPa']:.3g} MPa, under the "
                       f"bed's {adhesion:g} MPa", detail, item, measured=measured)


    def _hand_check(self, inputs: PrintingInputs, s: dict) -> dict:
        """Plate theory beside the simulation, as a check: a band fully held on the plate carries E ε / (1 - ν) in its
        plane; the first band's middle, held by the plate, should read about that."""
        hand = s["hand"]
        if not hand.get("plate_MPa") or hand.get("first_band_MPa") is None:
            return finding("info", "hand_check", "No hand check applies: nothing is held on a plate, or nothing shrinks",
                           "an SLS part floats in its powder; a strain of zero stresses nothing")
        ratio = hand["first_band_MPa"] / hand["plate_MPa"]
        spread = max(ratio, 1.0 / ratio) if ratio > 0 else math.inf
        measured = {"value": round(spread, 4), "limit": PLATE_FACTOR, "units": "×", "pass_when": "below",
                    "quantity": "first band against a band fully held"}
        summary = (f"Hand check: a band fully held on the plate carries E ε / (1 - ν) = {hand['plate_MPa']:.3g} MPa; the "
                   f"first band's middle reads {hand['first_band_MPa']:.3g} MPa ({ratio:.2g}×)")
        detail = ("von Mises of an equal-biaxial stress is the stress itself; a wall thinner than a band is held along "
                  "its length only and reads down to (1 - ν) of it")
        if spread > PLATE_FACTOR:
            return finding("warning", "hand_check_far", summary + ": further apart than the hand check allows; check the "
                           "build direction and the inherent strain", detail, measured=measured, fix={
                               "action": "check_inputs", "summary": "Check that the build direction puts the part's "
                               "flat base on the plate and that the inherent strain is the technology's",
                               "where": [s["shape_at"]], "params": {"build_direction": list(inputs.direction)}})
        return finding("info", "hand_check", summary, detail, measured=measured)

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: PrintingInputs, check_results: list[dict]) -> dict:
        s = result.scalars
        material = inputs.material
        summary = {
            "technology": inputs.technology.key,
            "material": material.name,
            "build_direction": [round(c, 6) for c in inputs.direction],
            "bands": inputs.bands,
            "band_mm": round(s["band_mm"], 6),
            "height_mm": round(s["height_mm"], 6),
            "layer_thickness_mm": inputs.layer_mm,
            "inherent_strain": {"in_plane": round(inputs.in_plane, 9), "build": round(inputs.along, 9),
                                "basis": inputs.strain_words()},
            "yield_MPa": material.yield_strength,
            "max_von_mises_MPa": round(s["vm_built_max"], 4),
            "von_mises_p99_MPa": round(s["vm_built_p99"], 4),
            "max_von_mises_at_mm": s["vm_built_at"],
            "released": s["released"],
            "max_distortion_mm": round(s["shape_max_mm"], 6),
            "max_distortion_at_mm": s["shape_at"],
            "warp_mm": None if s["warp"] is None else round(s["warp"]["mm"], 6),
            "warp_at_mm": None if s["warp"] is None else s["warp"]["at"],
            "released_max_von_mises_MPa": round(s["vm_final_max"], 4) if s["released"] else None,
            "tolerance_mm": s["tolerance_mm"],
            "tolerance_source": "study" if s["tolerance_given"] else f"ISO 2768-2 K for {s['size_mm']:.4g} mm",
            "recoater_rise_mm": round(s["rise"]["mm"], 6) if inputs.technology.recoater else None,
            "recoater_rise_at_mm": s["rise"]["at"] if inputs.technology.recoater else None,
            "plate_pull_MPa": None if s["pull"] is None else round(s["pull"]["MPa"], 4),
            "plate_pull_at_mm": None if s["pull"] is None else s["pull"]["at"],
            "starts_in_air": len(s["supports"]),
            "hand_check": {key: (round(value, 6) if isinstance(value, float) else value) for key, value in s["hand"].items()},
            "frames": len(result.series.frames),
            "checks": check_results,
        }
        if inputs.chamber_C is not None:
            summary["chamber_temperature_C"] = inputs.chamber_C
        return summary

    def ready_words(self, summary: dict) -> str:
        """The verdict's headline when nothing is to fix: "Ready to print · 0.044 mm warp off the plate"."""
        if summary["warp_mm"] is not None:
            return f"Ready to print · {summary['warp_mm']:.2g} mm warp off the plate"
        return f"Ready to print · {summary['max_distortion_mm']:.2g} mm distortion"

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        largest = max(float(np.linalg.norm(frame, axis=1).max()) for frame in result.frame_fields["displacement"])
        return requested or auto_deformation_scale(largest, bbox_diagonal)

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        frames = result.frame_fields
        return {
            "von_mises": (0.0, round(max(float(f.max()) for f in frames["von_mises"]), 4)),
            "displacement": (0.0, round(max(float(np.linalg.norm(f, axis=1).max()) for f in frames["displacement"]), 6)),
            "printed": (0.0, 1.0),
        }

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: PrintingInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = {
            # The viewer's "Made of" reads the material's name.
            "material": {"name": inputs.material.name},
            "technology": inputs.technology.key,
            "print_material": inputs.material.as_dict(),
            "build_direction": list(inputs.direction),
            "bands": inputs.bands,
            "release_from_plate": inputs.release,
            "layer_thickness_mm": inputs.layer_mm,
            "inherent_strain": {"in_plane": inputs.in_plane, "build": inputs.along, "basis": inputs.strain_words()},
        }
        if inputs.tolerance_mm is not None:
            echo["tolerance_mm"] = inputs.tolerance_mm
        if inputs.chamber_C is not None:
            echo["chamber_temperature_C"] = inputs.chamber_C
        if inputs.adhesion_MPa is not None:
            echo["bed_adhesion_MPa"] = inputs.adhesion_MPa
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        strain = summary["inherent_strain"]
        lines = [
            f"{summary['material']} by {summary['technology']}, {summary['bands']} bands of {summary['band_mm']:.3g} mm, "
            f"inherent strain {strain['in_plane']:.3g} in the plane, {strain['build']:.3g} along the build",
            f"as printed: residual stress {summary['von_mises_p99_MPa']:.4g} MPa (99th percentile; yield "
            f"{summary['yield_MPa']:g} MPa)",
        ]
        if summary["released"]:
            lines.append(f"off the plate: the bottom lifts {summary['warp_mm']:.3g} mm out of flat, distortion up to "
                         f"{summary['max_distortion_mm']:.3g} mm (tolerance {summary['tolerance_mm']:g} mm)")
        else:
            lines.append(f"as printed: distortion up to {summary['max_distortion_mm']:.3g} mm (tolerance "
                         f"{summary['tolerance_mm']:g} mm)")
        if summary["recoater_rise_mm"] is not None:
            lines.append(f"the most a band's top rises as it is printed: {summary['recoater_rise_mm']:.3g} mm (layer "
                         f"{summary['layer_thickness_mm']:g} mm)")
        return lines


# -- helpers -------------------------------------------------------------------------------------------


def _in_plane_axes(d):
    """Two unit vectors square to ``d`` and to each other: the global axes' where ``d`` is one of them."""
    import numpy as np

    d = np.asarray(d, dtype=float)
    seed = np.eye(3)[int(np.argmin(np.abs(d)))]
    e1 = seed - (seed @ d) * d
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(d, e1)


def _shortest_axis(s: dict):
    """The global axis the part is shortest along, as a build direction: ``None`` when it cannot be told."""
    sizes = s.get("axis_sizes")
    if not sizes:
        return None
    axis = min(range(3), key=lambda i: sizes[i])
    return tuple(1.0 if i == axis else 0.0 for i in range(3))


def _frames_kept(count: int, most: int) -> list[int]:
    """Which of ``count`` frames to write, at most ``most``: evenly spread, the first and the last always."""
    if count <= most:
        return list(range(count))
    step = (count - 1) / (most - 1)
    return sorted({round(i * step) for i in range(most)})


def _flatness(points, shape, d) -> dict:
    """The bottom's flatness: the range of its points' displacement along ``d`` about their best-fit plane, and the
    point that lifts most (``index``)."""
    import numpy as np

    lift = shape @ d
    a = np.column_stack([points, np.ones(len(points))])
    coefficients, *_ = np.linalg.lstsq(a, lift, rcond=None)
    residual = lift - a @ coefficients
    return {"mm": float(np.ptp(residual)), "index": int(np.argmax(residual))}


def _plate_pull(space, rows, reactions, d, radius: float) -> dict | None:
    """The plate's largest pull on the part per area, averaged over the plate within ``radius`` of where it pulls
    hardest (a corner's pull is singular at the corner itself): each plate triangle's share of its nodes' reactions
    along -d."""
    import numpy as np

    if len(rows) == 0:
        return None
    points = space.dof_locations
    corners = points[rows[:, :3]]
    centres = corners.mean(axis=1)
    areas = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    sharing = np.bincount(rows.ravel(), minlength=space.scalar_count)
    pull = -(reactions @ d)                                            # toward the plate: positive
    force = (pull[rows] / np.maximum(sharing[rows], 1)).sum(axis=1)
    worst = int(np.argmax(force / np.maximum(areas, 1e-12)))
    near = np.linalg.norm(centres - centres[worst], axis=1) <= radius
    average = float(force[near].sum() / max(float(areas[near].sum()), 1e-12))
    return {"MPa": max(average, 0.0), "at": xyz(centres[worst]), "radius_mm": radius}


def _hand_check(space, material, sigma, born, band_of, d, inputs) -> dict:
    """The plate-theory hand check's numbers: a band fully held on the plate carries E ε / (1 - ν) in its plane, and
    the first band's middle (the half of its elements nearest its middle) reads ``first_band_MPa``."""
    import numpy as np

    from cadgen._internal.manufacturing.processes import inherent_strain as IS
    from cadgen._internal.fea import operators

    out: dict[str, Any] = {}
    if not inputs.technology.plate:
        return out
    volumes = IS.element_volumes(space)
    centroids = IS.element_centroids(space)
    vm = (operators.von_mises(sigma) * space.basis.dx).sum(axis=1) / np.maximum(volumes, 1e-300)
    first = np.flatnonzero(born & (band_of == 0))
    out["plate_MPa"] = material.E / (1.0 - material.nu) * abs(inputs.in_plane)
    if len(first):
        plane = centroids[first] - np.outer(centroids[first] @ d, d)
        near = first[np.argsort(np.linalg.norm(plane - plane.mean(axis=0), axis=1))[: max(1, len(first) // 2)]]
        out["first_band_MPa"] = float(np.median(vm[near]))
    return out


def _tolerance_words(s: dict) -> str:
    return "the study's" if s["tolerance_given"] else f"ISO 2768-2 K for its {s['size_mm']:.3g} mm"
