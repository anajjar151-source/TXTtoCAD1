"""Heat treatment (lite): a steel part quench hardened, from the furnace to under 500 °C.

The study names the ``steel`` (:data:`cadgen._internal.manufacturing.processes.hardening.GRADES`) and the ``quenchant``
(:data:`~cadgen._internal.manufacturing.processes.hardening.QUENCHANTS`: a constant heat transfer coefficient h on every face, and its
bath temperature). ``austenitize_C`` overrides the grade's hardening temperature, ``h_W_m2K`` the quenchant's
coefficient, and ``target_hrc`` is the hardness the part must reach.

The march (:mod:`cadgen._internal.manufacturing.processes.quench`) runs on linear tets. Each node's cooling rate at 700 °C reads the
grade's Jominy curve through the end-quench test's own rates: the ``hardness`` field (the default view; HRC, as
quenched), with the ``cooling_rate`` and the equivalent ``jominy_distance`` beside it and the ``temperature`` per frame.
At the moment the spread between the hottest and the coolest point is largest, the temperatures' thermal strain gives
the free part's elastic stress (``quench_stress``, von Mises, and ``tension``, the largest principal stress) and its
shape change (the ``displacement``, drawn as the distortion). Its findings are the heat treater's: the hardness at the
surface and the core and the depth to the target, soft spots, the quench's stress against the grade's hot strength
(and the sharp edges and thick-to-thin sections that concentrate it), the distortion, and the hand check, a round's
(or a block's) centre cooling by the series solution Grossmann's H and ideal critical diameter rest on. There are no
view checks: its findings are its verdict. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import (
    AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext, frame_attributes, max_frames, xyz,
)
from cadgen._internal.manufacturing.processes.base import Process, finding_of

__all__ = ["HeatTreatmentInputs", "HeatTreatmentProcess", "LIMITS"]

#: This process's findings, held to its closed set (``base.FINDING_TYPES``).
finding = finding_of("heat_treatment")

LIMITS = (
    "Thermal only: the steel is austenite through the quench with constant properties, and it does not transform: "
    "no transformation heat, and no transformation strain in the stress or the distortion.",
    "One constant heat transfer coefficient on every face, the quenchant's or the study's: no vapour blanket, boiling "
    "stage or agitation pattern, and no face shielded from the bath.",
    "Hardness is read from the cooling rate at 700 °C through the grade's Jominy curve, as quenched (before "
    "tempering); a carburising grade's is its core's alone.",
    "The stress is elastic, at the moment of the largest temperature spread: past the hot strength the part yields, "
    "and the permanent distortion, the residual stress and the cracking that follow are not computed.",
)
#: The hand check and the simulation are this many times apart at most for a round or a block (the series solution is
#: exact for them); for any other shape, an equivalent round, FAR_EQUIVALENT.
FAR_EXACT, FAR_EQUIVALENT = 1.25, 2.0
#: An edge whose faces turn by more than this many degrees is sharp (a fillet's faces meet tangent).
SHARP_DEG = 30.0
#: A thick section this many times the thinnest is a thick-to-thin transition (a rule of thumb).
SECTION_RATIO = 3.0
#: The sections the thinnest is read from: this low percentile of the surface's, not one stray ray.
THIN_PERCENTILE = 5.0
#: A fillet suggested at a sharp edge: a tenth of the section there, at least this, mm (a rule of thumb).
FILLET_MIN_MM = 1.0
#: A shape is a block or a round when its volume is within this share of the box's or the cylinder's.
SHAPE_TOLERANCE = 0.03
#: The core is the slowest-cooling point at least this share as deep as the deepest.
CORE_DEPTH = 0.9
#: The Rockwell C scale it reads hardness on.
HRC_RANGE = (20.0, 70.0)
STUDY_KEYS = frozenset({"steel", "quenchant", "austenitize_C", "h_W_m2K", "target_hrc"})


@dataclass(frozen=True)
class HeatTreatmentInputs(Inputs):
    grade: Any = None
    quenchant: Any = None
    austenitize_C: float = 0.0
    #: The study's own h, W/(m² K); ``None`` for the quenchant's.
    h: float | None = None
    target_hrc: float | None = None

    @property
    def coefficient(self) -> float:
        return self.h if self.h is not None else self.quenchant.h

    def quench_words(self) -> str:
        words = f"{self.quenchant.words} at {self.quenchant.bath_C:g} °C"
        if self.h is not None:
            return f"{words}, h = {self.h:g} W/(m² K) (the study's)"
        return f"{words}, h = {self.quenchant.h:g} W/(m² K)"


def austenite_material():
    """The austenite the part is through the quench, as the operators read a material."""
    from cadgen._internal.manufacturing.processes.hardening import AUSTENITE
    from cadgen._internal.fea.materials import Material

    return Material("Austenite (quenched steel)", AUSTENITE.E, AUSTENITE.nu, None, AUSTENITE.density * 1e-12,
                    conductivity=AUSTENITE.conductivity, expansion=AUSTENITE.expansion,
                    specific_heat=AUSTENITE.specific_heat)


def time_words(seconds: float) -> str:
    from cadgen._internal.fea.analyses.thermal_transient import time_label

    return time_label(seconds)


class HeatTreatmentProcess(Process):
    name: ClassVar[str] = "heat_treatment"
    word: ClassVar[str] = "Heat treatment"
    extras_word: ClassVar[str] = "quench hardness"
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = STUDY_KEYS
    #: Linear tets: their lumped capacity keeps the march monotone, so each node passes 700 °C once.
    mesh_orders: ClassVar[tuple[int, ...]] = (1,)
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("hardness", "_HARDNESS", "hardness as quenched", "HRC"),
        FieldSpec("cooling_rate", "_COOLING_RATE", "cooling rate at 700 °C", "°C/s"),
        FieldSpec("jominy_distance", "_JOMINY_DISTANCE", "equivalent Jominy distance", "mm"),
        FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True, per_frame=True),
        FieldSpec("quench_stress", "_QUENCH_STRESS", "quench stress (von Mises)", "MPa"),
        FieldSpec("tension", "_TENSION", "largest principal stress", "MPa", signed=True),
        FieldSpec("displacement", "_DISPLACEMENT", "distortion", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = ()
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "frame", "threshold", "deformation")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum",
                  "options": ["hardness", "cooling_rate", "jominy_distance", "temperature", "quench_stress", "tension"]},
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "defeature")
    noun: ClassVar[str] = "this quench"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> HeatTreatmentInputs:
        from cadgen._internal.manufacturing.processes.hardening import A1_C, GRADES, QUENCHANTS, lookup_grade, lookup_quenchant

        if "material" in document:
            raise ValueError(f"study.material: a heat treatment names its steel with 'steel', one of {', '.join(GRADES)}")
        for key in ("parts", "connections"):
            if key in document:
                raise ValueError(f"study.{key}: a heat treatment quenches one part; solve one occurrence with "
                                 "--occurrence")
        if "steel" not in document:
            raise ValueError(f"study.steel: the steel grade, one of {', '.join(GRADES)}")
        grade = lookup_grade(document["steel"])
        if "quenchant" not in document:
            raise ValueError(f"study.quenchant: what it is quenched in, one of {', '.join(QUENCHANTS)}")
        quenchant = lookup_quenchant(document["quenchant"])
        austenitize = grade.austenitize_C
        if "austenitize_C" in document:
            austenitize = kinds.number(document["austenitize_C"], where="austenitize_C")
            if austenitize <= A1_C:
                raise ValueError(f"austenitize_C: {austenitize:g} °C is not above the eutectoid {A1_C:g} °C: the "
                                 "steel is not austenite there, and nothing hardens")
            if austenitize > 1250.0:
                raise ValueError(f"austenitize_C: {austenitize:g} °C is past 1250 °C, where steel burns; "
                                 f"{grade.name} is hardened from {grade.austenitize_C:g} °C")
        h = None
        if "h_W_m2K" in document:
            h = kinds.number(document["h_W_m2K"], where="h_W_m2K", positive=True)
        target = None
        if "target_hrc" in document:
            target = kinds.number(document["target_hrc"], where="target_hrc")
            low, high = HRC_RANGE
            if not low <= target <= high:
                raise ValueError(f"target_hrc: {target:g} is off the Rockwell C scale this reads ({low:g} to {high:g})")
        return HeatTreatmentInputs((), (), False, grade=grade, quenchant=quenchant, austenitize_C=austenitize, h=h,
                                   target_hrc=target)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: HeatTreatmentInputs):
        """A temperature problem solved a few hundred times (the steps double and halve), then one elastic solve."""
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.thermal import ladder_estimate

        heat = ladder_estimate(ctx, steps=400, frames=2 * max_frames(ctx))
        mechanical = fit.solid_estimate(ctx)
        return fit.Estimate(dofs=mechanical.dofs, memory_bytes=max(heat.memory_bytes, mechanical.memory_bytes),
                            seconds=heat.seconds + mechanical.seconds)

    def apply(self, rung, ctx: SolveContext, inputs: HeatTreatmentInputs):
        from cadgen._internal.fea import fit

        return fit.apply_generic(rung, self, ctx, inputs)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: HeatTreatmentInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import timestep
        from cadgen._internal.manufacturing.processes import hardening, quench, solidification
        from cadgen._internal.fea.analyses.thermal import plan_solver, space_result
        from cadgen._internal.fea.operators import DIRECT_SOLVE_BELOW

        if ctx.assembly is not None:
            raise ValueError("heat_treatment: the document holds several parts; a heat treatment quenches one, so name "
                             "it with --occurrence")
        space = ctx.space
        if space.order != 1:
            raise ValueError("heat_treatment: solved on linear tets (mesh.order 1)")
        grade, bath, start, h = inputs.grade, inputs.quenchant.bath_C, inputs.austenitize_C, inputs.coefficient
        steel = austenite_material()
        started = time.perf_counter()
        nodes = space.dof_locations
        volumes = solidification.node_volumes(space)
        depth = surface_depth(space)
        shape = plain_shape(nodes, float(volumes.sum()), float(depth.max()))
        hand = hardening.centre_cooling(shape["shape"], shape["dims_mm"], h, start_C=start, bath_C=bath)
        estimate = hand["t_500_s"] or hand["t_700_s"] or 1.0
        timings = {"assemble_s": time.perf_counter() - started}
        started = time.perf_counter()
        iterative = plan_solver(ctx) is not None or len(nodes) >= DIRECT_SOLVE_BELOW
        run = quench.march(space, steel, h_W_m2K=h, bath_C=bath, start_C=start, node_volumes=volumes,
                           estimate_s=estimate, frames=max_frames(ctx), iterative=iterative, log=ctx.log,
                           limit_s=timestep.time_limit(ctx))
        timings["solve_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"followed the quench for {run.end_s:.4g} s in {run.steps} steps in {timings['solve_s']:.1f}s")
        started = time.perf_counter()
        warnings: list[str] = []
        stress = quench.thermal_stress(space, steel, run.spread_state, volumes, warnings)
        timings["stress_s"] = time.perf_counter() - started
        started = time.perf_counter()
        slowest = float(np.nanmin(run.rate_700)) if np.isfinite(run.rate_700).any() else 0.0
        rate = np.where(np.isfinite(run.rate_700), run.rate_700, slowest)
        distance = np.array([hardening.jominy_distance(r) if r > 0 else math.inf for r in rate])
        hardness = np.array([grade.hardness(d) for d in distance])
        cut = solidification.sections(space, np.zeros(len(nodes)))
        rows_of = solidification.boundary_facet_rows(space)
        timings["post_s"] = time.perf_counter() - started
        series = Series(kind="time", unit="s", default=run.spread_frame, frames=[
            SeriesFrame(value=round(t, 9), label=time_words(t), attributes=frame_attributes({"temperature": "_TEMPERATURE"}, i))
            for i, (t, _) in enumerate(run.frames)
        ])
        analysis_warnings = []
        if run.stopped_at is not None:
            analysis_warnings.append(timestep.stopped_sentence(time_words(run.stopped_at), "under 500 °C",
                                                               timestep.time_limit(ctx)))
        if run.cut_short:
            analysis_warnings.append(run.cut_short[0].upper() + run.cut_short[1:])
        temperatures = [state for _, state in run.frames]
        result = space_result(
            space,
            {"hardness": hardness, "cooling_rate": rate, "jominy_distance": np.minimum(distance, grade.jominy[-1][0]),
             "temperature": temperatures[0], "quench_stress": stress.von_mises, "tension": stress.tension,
             "displacement": stress.displacement},
            series=series, frame_fields={"temperature": temperatures},
            curves={"hottest_C": {"x": [round(t, 9) for t in run.curve_t], "x_unit": "s",
                                  "y": [round(v, 6) for v in run.curve_hot], "y_unit": "°C"},
                    "coolest_C": {"x": [round(t, 9) for t in run.curve_t], "x_unit": "s",
                                  "y": [round(v, 6) for v in run.curve_cold], "y_unit": "°C"}},
            solver=f"{run.solver}; the stress {stress.solver}", timings=timings, warnings=analysis_warnings + warnings,
            scalars={"run": run, "stress": stress, "hand": hand, "shape": shape, "depth": depth, "sections": cut,
                     "section_rows": rows_of, "node_volumes": volumes, "jominy_raw": distance,
                     "grossmann_H": hardening.grossmann_H(h), "conductivity": hardening.AUSTENITE.conductivity,
                     "mesh_size_mm": float(ctx.volume.max_h), "analysis_warnings": analysis_warnings},
        )
        result.deformation = stress.displacement
        return result

    # -- findings ------------------------------------------------------------------------------------

    def ready_words(self, summary: dict) -> str:
        """The verdict's headline when nothing is to fix: "Ready to quench · core 52 HRC"."""
        return f"Ready to quench · core {summary['core_hrc']:.3g} HRC"

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: HeatTreatmentInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.timestep import stopped_finding

        s = result.scalars
        run = s["run"]
        found = []
        if run.stopped_at is not None:
            found.append(stopped_finding(s["analysis_warnings"][0]))
        if run.cut_short:
            fix = ({"action": "check_inputs", "where": [], "params": {},
                    "summary": "Check the quenchant, h_W_m2K and the austenitising temperature against the shop's"}
                   if run.cut_short.startswith("still above") else
                   {"action": "coarsen_mesh", "where": [], "params": {},
                    "summary": "Give the study a coarser mesh.size_mm and run it again"})
            found.append(finding("warning", "not_cooled", f"Not cooled through at the end: {run.cut_short}",
                                 "a point that never reached 700 °C reads the slowest rate that did, an upper bound "
                                 "on its hardness", fix=fix))
        surface, core = self._surface_and_core(ctx, result)
        found.append(self._hardness(result, inputs, surface, core))
        found += self._target(ctx, result, inputs, surface, core)
        found += self._stress(ctx, result, inputs)
        found += self._sections(ctx, result)
        found.append(self._hand_check(result, inputs, core))
        beyond = result.scalars["jominy_raw"] > inputs.grade.jominy[-1][0]
        if beyond.any():
            share = float(s["node_volumes"][beyond].sum() / s["node_volumes"].sum())
            found.append(finding("info", "beyond_jominy",
                                 f"{share:.0%} of the part cools slower than the grade's Jominy curve goes "
                                 f"({inputs.grade.jominy[-1][0]:g} mm): its hardness there is the curve's last, "
                                 f"{inputs.grade.jominy[-1][1]:g} HRC",
                                 "slower than the end of the curve the steel is softer still, or no softer for an "
                                 "air-hardening grade"))
        if inputs.grade.estimated:
            found.append(finding("info", "estimated_curve",
                                 f"{inputs.grade.name}'s Jominy curve is an estimate from its hardening class "
                                 f"({inputs.grade.hardens_in}-hardening): Just's formula does not reach its "
                                 "composition; compare a mill's curve for the heat when the hardness matters",
                                 "the manufacturing-sim skill's heat-treatment reference lists it"))
        if inputs.grade.core_only:
            found.append(finding("info", "core_only",
                                 f"{inputs.grade.name} is a carburising grade: this is the core's hardness; the "
                                 "carburised case, harder and shallower, is not modelled",
                                 "the case's hardness and depth follow the carburising, which this does not simulate"))
        return found

    def _surface_and_core(self, ctx: SolveContext, result: AnalysisResult):
        return surface_and_core(result)

    def _hardness(self, result: AnalysisResult, inputs: HeatTreatmentInputs, surface, core: int) -> dict:
        fields, nodes = result.fields, result.dof_locations
        hrc, rate = fields["hardness"], fields["cooling_rate"]
        top, bottom = float(hrc[surface].max()), float(hrc[surface].min())
        span = f"{bottom:.3g} HRC" if f"{bottom:.3g}" == f"{top:.3g}" else f"{bottom:.3g} to {top:.3g} HRC"
        return finding(
            "info", "hardness",
            f"{inputs.grade.name} quenched from {inputs.austenitize_C:g} °C in {inputs.quench_words()}: the surface "
            f"{span}, the core {float(hrc[core]):.3g} HRC at {xyz(nodes[core])} mm (it cools "
            f"at {float(rate[core]):.3g} °C/s at 700 °C, like {float(fields['jominy_distance'][core]):.3g} mm along a "
            "Jominy bar)",
            "as quenched, before tempering: each point's cooling rate at 700 °C read on the grade's Jominy curve",
            [{"text": "the core", "ref": None, "at": xyz(nodes[core])}])

    def _target(self, ctx: SolveContext, result: AnalysisResult, inputs: HeatTreatmentInputs, surface,
                core: int) -> list[dict]:
        import numpy as np

        from cadgen._internal.manufacturing.processes.hardening import GRADES, QUENCHANT_ORDER

        target = inputs.target_hrc
        if target is None:
            return []
        hrc, nodes, depth = result.fields["hardness"], result.dof_locations, result.scalars["depth"]
        soft = hrc < target
        measured_surface = {"quantity": "softest surface hardness", "value": round(float(hrc[surface].min()), 2),
                            "limit": target, "units": "HRC", "pass_when": "above"}
        if not (soft & surface).any():
            if not soft.any():
                words = f"hardens through: every point reaches {target:g} HRC, the core {float(hrc[core]):.3g}"
            else:
                reach = float(depth[soft].min())
                words = (f"is hard to {reach:.3g} mm deep, then softer: the core reads {float(hrc[core]):.3g} HRC at "
                         f"{xyz(nodes[core])} mm")
            return [finding("info", "target_hardness",
                            f"The surface reaches the target {target:g} HRC everywhere (its softest "
                            f"{measured_surface['value']:g}); it {words}",
                            "the depth is the shallowest point under the target, measured from the nearest surface",
                            [{"text": "the core", "ref": None, "at": xyz(nodes[core])}], measured=measured_surface)]
        worst = int(np.flatnonzero(soft & surface)[np.argmin(hrc[soft & surface])])
        distance = float(result.scalars["jominy_raw"][worst])
        better = [grade.key for grade in GRADES.values()
                  if not grade.core_only and grade.hardness(distance) >= target]
        current = QUENCHANT_ORDER.index(inputs.quenchant.key)
        faster = QUENCHANT_ORDER[current + 1] if current + 1 < len(QUENCHANT_ORDER) else None
        where = [*face_refs_at(ctx, result, worst), xyz(nodes[worst])]
        if better:
            fix = {"action": "change_material",
                   "summary": f"Use a steel that holds {target:g} HRC this far along its Jominy curve: "
                              f"{', '.join(better)}; or quench it faster",
                   "where": where, "params": {"steel": better[0]}}
        elif faster is not None:
            fix = {"action": "change_quenchant", "summary": f"Quench it faster, in {faster}, or thin the section there",
                   "where": where, "params": {"quenchant": faster}}
        else:
            fix = {"action": "thin", "summary": "Thin the section there so it cools faster; no listed steel or "
                                                "quenchant reaches the target in it", "where": where, "params": {}}
        share = float((soft & surface).sum() / surface.sum())
        return [finding("error", "soft_spot",
                        f"Soft at the surface: {float(hrc[worst]):.3g} HRC at {xyz(nodes[worst])} mm, under the target "
                        f"{target:g} HRC ({share:.0%} of the surface falls short); it cools at "
                        f"{float(result.fields['cooling_rate'][worst]):.3g} °C/s at 700 °C there",
                        "the surface must reach the target hardness; a point there cools too slowly for this steel",
                        [{"text": "the softest surface point", "ref": None, "at": xyz(nodes[worst])}],
                        measured=measured_surface, fix=fix)]

    def _stress(self, ctx: SolveContext, result: AnalysisResult, inputs: HeatTreatmentInputs) -> list[dict]:
        import numpy as np

        from cadgen._internal.manufacturing.processes.hardening import QUENCHANT_ORDER, hot_strength

        s = result.scalars
        run, nodes = s["run"], result.dof_locations
        tension, spread = result.fields["tension"], run.spread_state
        peak = int(np.argmax(tension))
        strength = np.array([hot_strength(inputs.grade.annealed_yield_MPa, float(t)) for t in spread])
        limit, value = float(strength[peak]), float(tension[peak])
        current = QUENCHANT_ORDER.index(inputs.quenchant.key)
        slower = QUENCHANT_ORDER[current - 1] if current > 0 else None

        def gentler(point) -> dict | None:
            return None if slower is None else {
                "action": "change_quenchant",
                "summary": f"Quench it more gently, in {slower}, if its hardness still reaches what the part needs",
                "where": [xyz(point)], "params": {"quenchant": slower}}

        when = f"at {time_words(run.spread_s)}, when the part spans {run.spread_C:.0f} °C"
        measured = {"quantity": "peak quench tension (elastic) against the strength there", "value": round(value, 2),
                    "limit": round(limit, 2), "units": "MPa", "pass_when": "below"}
        item = [{"text": "the peak tension", "ref": None, "at": xyz(nodes[peak])}]
        yields = value > limit
        if not yields:
            found = [finding("info", "quench_stress",
                             f"The quench's tension peaks at {value:.0f} MPa at {xyz(nodes[peak])} mm {when}, under the "
                             f"{inputs.grade.name}'s strength there ({limit:.0f} MPa at {float(spread[peak]):.0f} °C): "
                             "it does not yield", "the largest principal stress of the temperatures' thermal strain, "
                             "elastic, against the annealed yield scaled to the temperature (an estimate)", item,
                             measured=measured)]
        else:
            found = [finding("warning", "quench_yield",
                             f"The quench pulls {value:.0f} MPa at {xyz(nodes[peak])} mm {when}, over the "
                             f"{inputs.grade.name}'s strength there ({limit:.0f} MPa at {float(spread[peak]):.0f} °C): "
                             "the part yields in the quench, so it keeps residual stress and some of its distortion",
                             "elastic thermal stress against the annealed yield scaled to the temperature (an estimate); "
                             "most liquid quenches yield a part's surface, and the transformation's own strain, not "
                             "modelled, comes on top", item, measured=measured, fix=gentler(nodes[peak]))]
        found.append(self._crack_risk(ctx, result, inputs, strength))
        moved = np.linalg.norm(result.fields["displacement"], axis=1)
        far = int(np.argmax(moved))
        words = (f"Distorts up to {float(moved[far]):.3g} mm at {xyz(nodes[far])} mm while it cools unevenly ({when}), "
                 "against the part shrunk evenly")
        item = [{"text": "the largest distortion", "ref": None, "at": xyz(nodes[far])}]
        distortion = {"quantity": "largest distortion (elastic)", "value": round(float(moved[far]), 4), "units": "mm"}
        if yields:
            found.append(finding("warning", "distortion", words + ": it yields as it does, so part of this stays",
                                 "elastic thermal strain only; the permanent share needs the plasticity and the "
                                 "transformation, not modelled: read this as where and which way it moves", item,
                                 measured=distortion, fix=gentler(nodes[far])))
        else:
            found.append(finding("info", "distortion", words + ": elastic, it springs back as the temperature evens out",
                                 "elastic thermal strain only; no transformation strain", item, measured=distortion))
        return found

    def _crack_risk(self, ctx: SolveContext, result: AnalysisResult, inputs: HeatTreatmentInputs, strength) -> dict:
        """A quench crack starts at a sharp edge pulled past the steel's strength as it turns to martensite: under Ms,
        where the steel has gone hard and brittle (hot austenite above it yields instead)."""
        from cadgen._internal.manufacturing.processes.hardening import martensite_start

        tension, nodes, spread = result.fields["tension"], result.dof_locations, result.scalars["run"].spread_state
        ms = martensite_start(inputs.grade.composition)
        edges = sharp_edge_nodes(ctx, result)
        detail = (f"a sharp edge (faces meeting at more than {SHARP_DEG:g}°) concentrates the quench's tension; a crack "
                  f"starts there once the steel turns to martensite, under Ms ({ms:.0f} °C for {inputs.grade.name}, "
                  "Andrews' formula); the transformation's own stress, not modelled, adds to it")
        if not edges:
            return finding("info", "crack_risk", "No crack risk at an edge: the part has no sharp edge", detail)
        cold = [node for node in edges if float(spread[node]) < ms]
        over = [node for node in cold if tension[node] > strength[node]]
        if not cold:
            hottest = max(edges, key=lambda node: float(tension[node]))
            return finding("info", "crack_risk",
                           f"No crack risk at a sharp edge: none has cooled under Ms ({ms:.0f} °C) when the quench "
                           f"pulls hardest; the most loaded is at {float(spread[hottest]):.0f} °C, hot austenite that "
                           "yields rather than cracks", detail,
                           [{"text": "the most loaded sharp edge", "ref": None, "at": xyz(nodes[hottest])}])
        if not over:
            worst = max(cold, key=lambda node: float(tension[node] - strength[node]))
            return finding("info", "crack_risk",
                           f"No crack risk at a sharp edge: none is pulled past its strength as it turns to martensite; "
                           f"the most, {float(tension[worst]):.0f} MPa against {float(strength[worst]):.0f} MPa, at "
                           f"{xyz(nodes[worst])} mm", detail,
                           [{"text": "the most loaded sharp edge", "ref": None, "at": xyz(nodes[worst])}],
                           measured={"quantity": "tension at a sharp edge against its strength",
                                     "value": round(float(tension[worst]), 2),
                                     "limit": round(float(strength[worst]), 2), "units": "MPa", "pass_when": "below"})
        worst = max(over, key=lambda node: float(tension[node] - strength[node]))
        faces = edges[worst]
        radius = round(max(FILLET_MIN_MM, 0.1 * 2.0 * float(result.scalars["depth"].max())), 1)
        return finding("warning", "crack_risk",
                       f"Crack risk at a sharp edge: {float(tension[worst]):.0f} MPa of tension at {xyz(nodes[worst])} mm "
                       f"where {' and '.join(faces)} meet, past the strength there ({float(strength[worst]):.0f} MPa) "
                       f"as it turns to martensite ({float(spread[worst]):.0f} °C, under Ms {ms:.0f} °C); "
                       f"{len(over)} sharp-edge point{'s' if len(over) != 1 else ''} in all", detail,
                       [{"text": "the sharp edge", "ref": ref, "at": xyz(nodes[worst])} for ref in faces],
                       measured={"quantity": "tension at a sharp edge against its strength",
                                 "value": round(float(tension[worst]), 2), "limit": round(float(strength[worst]), 2),
                                 "units": "MPa", "pass_when": "below"},
                       fix={"action": "add_fillet",
                            "summary": f"Round the edge where {' and '.join(faces)} meet, {radius:g} mm or more, or "
                                       "quench more gently",
                            "where": [*faces, xyz(nodes[worst])],
                            "params": {"radius_mm": radius}})

    def _sections(self, ctx: SolveContext, result: AnalysisResult) -> list[dict]:
        import numpy as np

        s = result.scalars
        cut, rows_of, depth, nodes = s["sections"], s["section_rows"], s["depth"], result.dof_locations
        measured = cut.measured & (cut.thickness > 0)
        if not measured.any():
            return []
        thin = float(np.percentile(cut.thickness[measured], THIN_PERCENTILE))
        thinnest = int(np.flatnonzero(measured)[np.argmin(np.abs(cut.thickness[measured] - thin))])
        core = int(np.argmax(depth))
        thick = 2.0 * float(depth[core])
        ratio = thick / max(thin, 1e-9)
        row = int(rows_of[thinnest])
        ordinal = int(ctx.volume.boundary_ordinal[row]) if row >= 0 else None
        face = ctx.volume.faces.get(ordinal) if ordinal is not None else None
        items = [{"text": f"the thickest section, about {thick:.2g} mm", "ref": None, "at": xyz(nodes[core])},
                 {"text": f"a {thin:.2g} mm section", "ref": face.ref if face else None, "at": xyz(cut.middle[thinnest])}]
        measure = {"quantity": "thickest section against the thinnest", "value": round(ratio, 3), "limit": SECTION_RATIO,
                   "units": "×", "pass_when": "below"}
        if ratio <= SECTION_RATIO:
            return [finding("info", "section_change",
                            f"No thick-to-thin transition: the thickest section, about {thick:.2g} mm, is "
                            f"{ratio:.2g} times the thinnest ({thin:.2g} mm)",
                            f"sections more than {SECTION_RATIO:g} times apart cool at very different rates, which "
                            "distorts and cracks a quenched part (a rule of thumb)", items, measured=measure)]
        return [finding("warning", "section_change",
                        f"A thick-to-thin transition: a section about {thick:.2g} mm thick at {xyz(nodes[core])} mm "
                        f"beside one of {thin:.2g} mm ({ratio:.2g} times): the thin one hardens and shrinks long "
                        "before the thick one, which distorts it and can crack it where they meet",
                        f"sections more than {SECTION_RATIO:g} times apart cool at very different rates (a rule of thumb)",
                        items, measured=measure,
                        fix={"action": "thin", "summary": f"Thin the thick section toward {SECTION_RATIO * thin:.2g} mm "
                                                          "(core it out, or split it), or thicken the thin one",
                             "where": [*([face.ref] if face else []), xyz(nodes[core])],
                             "params": {"thickness_mm": round(SECTION_RATIO * thin, 2)}})]

    def _hand_check(self, result: AnalysisResult, inputs: HeatTreatmentInputs, core: int) -> dict:
        s = result.scalars
        hand, shape = s["hand"], s["shape"]
        nodes, rate = result.dof_locations, result.fields["cooling_rate"]
        centre = core if shape["equivalent"] else nearest(nodes, shape["centre_mm"])
        simulated = float(rate[centre])
        expected = hand["rate_700_C_s"]
        exact = not shape["equivalent"]
        tolerance = FAR_EXACT if exact else FAR_EQUIVALENT
        ratio = simulated / expected if expected else math.inf
        summary = (f"By the series solution Grossmann's H rests on, {shape['words']} quenched at h = "
                   f"{inputs.coefficient:g} W/(m² K) (H = {s['grossmann_H']:.2g} per inch) cools at {expected:.3g} °C/s "
                   f"at its centre at 700 °C; the simulation's {'centre' if exact else 'deepest point'} cools at "
                   f"{simulated:.3g} °C/s ({ratio:.2g} times)")
        measured = {"quantity": "simulation against the hand check", "value": round(ratio, 4), "limit": tolerance,
                    "units": "×", "pass_when": "below"}
        if 1.0 / tolerance <= ratio <= tolerance:
            return finding("info", "hand_check", summary,
                           "the exact conduction solution with the same h and austenite's properties"
                           + ("" if exact else ", for a round as thick as the part's thickest section (an estimate)"),
                           measured=measured)
        size = float(result.scalars.get("mesh_size_mm") or 0.0)
        return finding("warning", "hand_check_far", summary + f": more than {tolerance:g} times apart",
                       "check the mesh: a coarse one cools the core too fast or too slow"
                       + ("" if exact else "; an equivalent round is a rough guide for this shape"),
                       measured=measured,
                       fix={"action": "refine_mesh", "summary": "Mesh it finer and solve again",
                            "where": [xyz(nodes[centre])],
                            "params": {"size_mm": round(size / 2.0, 3)} if size else {}})

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        moved = np.linalg.norm(result.fields["displacement"], axis=1)
        return requested or auto_deformation_scale(float(moved.max()), bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: HeatTreatmentInputs, check_results: list[dict]) -> dict:
        import numpy as np

        from cadgen._internal.manufacturing.processes.hardening import critical_diameters, hot_strength, martensite_start

        s = result.scalars
        run, hand, shape = s["run"], s["hand"], s["shape"]
        fields, nodes = result.fields, result.dof_locations
        surface, core = surface_and_core(result)
        rate = fields["cooling_rate"]
        hrc, depth = fields["hardness"], s["depth"]
        softest = int(np.argmin(hrc))
        peak = int(np.argmax(fields["tension"]))
        moved = np.linalg.norm(fields["displacement"], axis=1)
        far = int(np.argmax(moved))
        target = inputs.target_hrc
        reach = None
        if target is not None:
            soft = hrc < target
            reach = round(float(depth[soft].min()), 4) if soft.any() else None
        t85 = run.t_500 - run.t_800
        diameters = critical_diameters(inputs.grade, inputs.coefficient, start_C=inputs.austenitize_C,
                                       bath_C=inputs.quenchant.bath_C)
        released = run.energy_start - run.energy_end
        centre = core if shape["equivalent"] else nearest(nodes, shape["centre_mm"])

        def rounded(value, digits=6):
            return None if value is None or not math.isfinite(value) else round(float(value), digits)

        summary = {
            "steel": inputs.grade.name,
            "quenchant": inputs.quenchant.key,
            "quench": inputs.quench_words(),
            "austenitize_C": inputs.austenitize_C,
            "bath_C": inputs.quenchant.bath_C,
            "h_W_m2K": inputs.coefficient,
            "grossmann_H_per_in": round(s["grossmann_H"], 4),
            "surface_hrc": [round(float(hrc[surface].min()), 2), round(float(hrc[surface].max()), 2)],
            "core_hrc": round(float(hrc[core]), 2),
            "core_at_mm": xyz(nodes[core]),
            "softest_hrc": round(float(hrc[softest]), 2),
            "softest_at_mm": xyz(nodes[softest]),
            "target_hrc": target,
            "depth_to_target_mm": reach,
            "through_hardened": None if target is None else bool((hrc >= target).all()),
            "cooling_rate_core_C_s": round(float(rate[core]), 4),
            "cooling_rate_surface_C_s": [round(float(rate[surface].min()), 4), round(float(rate[surface].max()), 4)],
            "jominy_core_mm": round(float(s["jominy_raw"][core]), 4) if math.isfinite(s["jominy_raw"][core]) else None,
            "t85_core_s": rounded(t85[core]),
            "t85_surface_s": rounded(float(np.nanmin(t85[surface])) if np.isfinite(t85[surface]).any() else None),
            "largest_spread_C": round(run.spread_C, 4),
            "largest_spread_at_s": round(run.spread_s, 9),
            "peak_tension_MPa": round(float(fields["tension"][peak]), 4),
            "peak_tension_at_mm": xyz(nodes[peak]),
            "peak_tension_temperature_C": round(float(run.spread_state[peak]), 4),
            "hot_strength_MPa": round(hot_strength(inputs.grade.annealed_yield_MPa, float(run.spread_state[peak])), 4),
            "martensite_start_C": round(martensite_start(inputs.grade.composition), 2),
            "peak_quench_stress_MPa": round(float(fields["quench_stress"].max()), 4),
            "distortion_mm": round(float(moved[far]), 6),
            "distortion_at_mm": xyz(nodes[far]),
            "hand_check": {
                "shape": shape["shape"] if not shape["equivalent"] else "equivalent round",
                "dims_mm": [rounded(d, 4) for d in shape["dims_mm"]],
                "biot": round(inputs.coefficient * shape["half_mm"] / 1000.0 / s["conductivity"], 6),
                "centre_rate_700_C_s": rounded(hand["rate_700_C_s"]),
                "simulated_rate_700_C_s": round(float(rate[centre]), 6),
                "centre_t85_s": rounded(hand["t85_s"]),
                "simulated_t85_s": rounded(t85[centre]),
                "half_martensite_HRC": diameters["half_martensite_HRC"],
                "ideal_critical_diameter_mm": rounded(diameters["ideal_mm"], 3),
                "critical_diameter_mm": rounded(diameters["this_quench_mm"], 3),
            },
            "heat_to_bath_J": round(run.heat_out / 1000.0, 6),
            "heat_released_J": round(released / 1000.0, 6),
            "energy_balance": round(abs(released - run.heat_out) / max(abs(released), 1e-12), 9),
            "end_s": round(run.end_s, 6),
            "steps": run.steps,
            "smallest_step_s": round(run.smallest_step, 9),
            "largest_step_s": round(run.largest_step, 9),
            "frames": len(run.frames),
            "checks": check_results,
        }
        if run.stopped_at is not None:
            summary["stopped_at_s"] = round(run.stopped_at, 9)
        return summary

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        fields, frames = result.fields, result.frame_fields

        def span(values) -> tuple[float, float]:
            return float(np.min(values)), float(np.max(values))

        return {
            "hardness": span(fields["hardness"]),
            "cooling_rate": span(fields["cooling_rate"]),
            "jominy_distance": span(fields["jominy_distance"]),
            "temperature": (min(float(t.min()) for t in frames["temperature"]),
                            max(float(t.max()) for t in frames["temperature"])),
            "quench_stress": (0.0, float(fields["quench_stress"].max())),
            "tension": span(fields["tension"]),
            "displacement": (0.0, float(np.linalg.norm(fields["displacement"], axis=1).max())),
        }

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: HeatTreatmentInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = {
            # The viewer's "Made of" reads the material's name: the steel is the part's material.
            "material": {"name": inputs.grade.name},
            "steel": inputs.grade.as_dict(),
            "quenchant": inputs.quenchant.key,
            "bath_C": inputs.quenchant.bath_C,
            "austenitize_C": inputs.austenitize_C,
            "h_W_m2K": inputs.coefficient,
        }
        if inputs.target_hrc is not None:
            echo["target_hrc"] = inputs.target_hrc
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        surface = summary["surface_hrc"]
        lines = [
            f"{summary['steel']} from {summary['austenitize_C']:g} °C into {summary['quench']}: surface "
            f"{surface[0]:.3g} to {surface[1]:.3g} HRC, core {summary['core_hrc']:.3g} HRC at {summary['core_at_mm']} mm",
            f"the core cools at {summary['cooling_rate_core_C_s']:.3g} °C/s at 700 °C"
            + (f", t8/5 {time_words(summary['t85_core_s'])}" if summary["t85_core_s"] is not None else ""),
        ]
        if summary["target_hrc"] is not None:
            lines.append(f"target {summary['target_hrc']:g} HRC: " + (
                "through-hardened" if summary["through_hardened"] else
                f"hard to {summary['depth_to_target_mm']:.3g} mm deep" if summary["depth_to_target_mm"] is not None
                else "not reached"))
        hand = summary["hand_check"]
        lines.append(f"peak quench tension {summary['peak_tension_MPa']:.0f} MPa against a hot strength of "
                     f"{summary['hot_strength_MPa']:.0f} MPa; distortion up to {summary['distortion_mm']:.3g} mm")
        if hand["centre_rate_700_C_s"] is not None:
            lines.append(f"hand check ({hand['shape']}): the centre cools at {hand['centre_rate_700_C_s']:.3g} °C/s at "
                         f"700 °C, the simulation {hand['simulated_rate_700_C_s']:.3g}")
        return lines


# -- geometry the findings read ------------------------------------------------------------------------


def surface_and_core(result: AnalysisResult):
    """The surface nodes, and the core: the middle of the thickest section, the slowest to cool of the points within
    :data:`CORE_DEPTH` of the deepest (a long bar's centreline is all as deep; its middle cools last)."""
    import numpy as np

    surface = np.zeros(len(result.dof_locations), dtype=bool)
    surface[np.unique(np.asarray(result.boundary_quadratic)[:, :3])] = True
    depth = result.scalars["depth"]
    deep = np.flatnonzero(depth >= CORE_DEPTH * float(depth.max()))
    return surface, int(deep[np.argmin(result.fields["cooling_rate"][deep])])


def nearest(nodes, point) -> int:
    import numpy as np

    return int(np.argmin(np.linalg.norm(nodes - np.asarray(point), axis=1)))


def surface_depth(space) -> "Any":
    """Each node's distance to the nearest surface (mm), to the surface triangles' corners and middles."""
    import numpy as np
    from scipy.spatial import cKDTree

    nodes = space.dof_locations
    triangles = np.asarray(space.boundary_quadratic)[:, :3]
    samples = np.concatenate([nodes[np.unique(triangles)], nodes[triangles].mean(axis=1)])
    depth, _ = cKDTree(samples).query(nodes)
    depth[np.unique(triangles)] = 0.0
    return depth


def plain_shape(nodes, volume: float, deepest: float) -> dict:
    """The part as the hand check reads it: a block (its volume its box's), a round (two box sides equal and its
    volume the cylinder's), else a long round as thick as its thickest section (an estimate)."""
    import numpy as np

    low, high = nodes.min(axis=0), nodes.max(axis=0)
    sides = high - low
    centre = (low + high) / 2.0
    box = float(np.prod(sides))
    if abs(volume - box) <= SHAPE_TOLERANCE * box:
        return {"shape": "block", "dims_mm": tuple(float(s) for s in sides), "centre_mm": centre, "equivalent": False,
                "half_mm": float(sides.min()) / 2.0,
                "words": f"a {' x '.join(f'{s:.3g}' for s in sides)} mm block"}
    for axis in range(3):
        across = [sides[i] for i in range(3) if i != axis]
        diameter = float(sum(across) / 2.0)
        cylinder = math.pi / 4.0 * diameter * diameter * float(sides[axis])
        if abs(across[0] - across[1]) <= 0.01 * diameter and abs(volume - cylinder) <= SHAPE_TOLERANCE * cylinder:
            return {"shape": "round", "dims_mm": (diameter, float(sides[axis])), "centre_mm": centre, "equivalent": False,
                    "half_mm": diameter / 2.0,
                    "words": f"a {diameter:.3g} mm round {float(sides[axis]):.3g} mm long"}
    diameter = 2.0 * deepest
    return {"shape": "round", "dims_mm": (diameter, math.inf), "centre_mm": centre, "equivalent": True,
            "half_mm": diameter / 2.0,
            "words": f"not a plain round or block, so a long {diameter:.3g} mm round, as thick as its thickest section"}


def sharp_edge_nodes(ctx: SolveContext, result: AnalysisResult) -> dict[int, tuple[str, ...]]:
    """The surface nodes on a sharp edge (two faces meeting at more than :data:`SHARP_DEG`), each with those faces'
    refs."""
    import numpy as np

    triangles = np.asarray(result.boundary_quadratic)[:, :3]
    ordinals = np.asarray(ctx.volume.boundary_ordinal)
    corners = result.dof_locations[triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-300)
    sums: dict[tuple[int, int], Any] = {}
    for column in range(3):
        for node, ordinal, normal in zip(triangles[:, column], ordinals, normals):
            key = (int(node), int(ordinal))
            sums[key] = sums.get(key, 0.0) + normal
    by_node: dict[int, list[tuple[int, Any]]] = {}
    for (node, ordinal), total in sums.items():
        by_node.setdefault(node, []).append((ordinal, total / max(float(np.linalg.norm(total)), 1e-300)))
    limit = math.cos(math.radians(SHARP_DEG))
    found: dict[int, tuple[str, ...]] = {}
    for node, entries in by_node.items():
        if len(entries) < 2:
            continue
        pairs = [(a, b) for i, a in enumerate(entries) for b in entries[i + 1:] if float(a[1] @ b[1]) < limit]
        if pairs:
            refs = sorted({ctx.volume.faces[o].ref for pair in pairs for o, _ in pair if o in ctx.volume.faces})
            if refs:
                found[node] = tuple(refs)
    return found


def face_refs_at(ctx: SolveContext, result: AnalysisResult, node: int) -> list[str]:
    """The faces a surface node lies on."""
    import numpy as np

    triangles = np.asarray(result.boundary_quadratic)[:, :3]
    rows = (triangles == node).any(axis=1)
    ordinals = sorted({int(o) for o in np.asarray(ctx.volume.boundary_ordinal)[rows]})
    return [ctx.volume.faces[o].ref for o in ordinals if o in ctx.volume.faces]
