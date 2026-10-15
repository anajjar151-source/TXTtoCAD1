"""Machining (lite): does the part deflect under the cut, and will the cut chatter.

The study names the cut: the ``operation`` (``milling`` or ``turning``), the ``tool`` (a milling cutter's diameter and
flutes), ``spindle_rpm``, ``feed_per_tooth_mm`` (turning: per revolution), ``depth_mm`` (milling: the axial depth;
turning: the depth of cut, the chip's width), ``width_mm`` (milling: the radial depth), the ``cut_faces`` the cutter is
on, the ``fixtures`` the vise or the chuck holds, and the workpiece ``material``
(:data:`cadgen._internal.manufacturing.processes.cutting.WORK_MATERIALS`, with its Kienzle k_c1.1 and m_c).

1. The cut's force (:mod:`cadgen._internal.manufacturing.processes.cutting`): Kienzle's, summed over the teeth in the cut through one
   tooth period (milling, straight flutes) or the turning tool's one edge; the part feels its component along the
   cut face's inward normal.
2. The modes of the clamped part (the lowest :data:`MODES`) say where on the cut faces it is most flexible along
   their normal: Σ (φᵣ·n)² / ωᵣ². The cutter is put there, its force on a patch of the cut faces about the depth of cut
   across, and a static solve gives the deflection there (against ``tolerance_mm``) and the stress (against yield).
3. The part's transfer function at that patch along the normal, from the modes (with ``damping_ratio``) and the
   static solve's residual compliance, gives the regenerative stability lobes (Altintas and Budak's zero-order
   solution for milling, Tlusty's orthogonal cut for turning): the depth the cut stays stable to at the study's
   speed, at any speed, and the nearest stable speeds the spindle reaches (``max_spindle_rpm``). A cut past its limit
   is fixed by the depth that is stable at its own speed; a stable pocket's speed is the alternative, only within the
   spindle's reach.

Fields: the displacement under the cut, the von Mises stress, and the shape the part rings in at the cut (the
dominant mode's, its largest motion 1 mm). There are no view checks: the findings are the verdict, each with what it
measured and the fix. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import (
    AnalysisResult, FieldSpec, Inputs, SolveContext, by_severity, xyz,
)
from cadgen._internal.fea.study import Fixture, parse_fixtures
from cadgen._internal.manufacturing.processes.base import Process, finding_of

__all__ = ["LIMITS", "MachiningInputs", "MachiningProcess"]

#: This process's findings, held to its closed set (``base.FINDING_TYPES``).
finding = finding_of("machining")

LIMITS = (
    "The cutting force is Kienzle's for a sharp tool, straight flutes (no helix), no run-out or wear, from the "
    "material's machinability group: a real tool and grade can differ by 20 % or more.",
    "Only the part flexes: the tool, the holder and the spindle are rigid, so a stiff part cut by a long, slender tool "
    "chatters on the tool, which this does not see.",
    "The cutter is put where the cut faces are most flexible along their normal, and only the force along that normal "
    "acts: the feed force along a wall is left out (turning: the tangential force, which bends a round part as much "
    "again, is counted in the stress).",
    "Chatter is the zero-order (averaged) solution in one direction, the cut face's normal, linear in the chip: a "
    "light radial cut at high speed is interrupted enough to have extra lobes it misses, and at low speed the tool's "
    "flank rubbing the waves (process damping) makes the real cut more stable than this says.",
    "The damping is the study's (2 % unless it says), not measured: a tap test on the clamped part gives the real "
    "damping and frequency, and the real lobes.",
)
#: The lowest modes of the clamped part found: where it is flexible at the cut, and its transfer function there.
MODES = 8
#: The damping ratio of every mode when the study gives none.
DEFAULT_DAMPING = 0.02
#: The deflection the cut may leave when the study gives no tolerance: ISO 2768-1's fine class up to 6 mm.
DEFAULT_TOLERANCE_MM = 0.05
#: A deflection over this share of the tolerance is close: it leaves little for every other error.
DEFLECTION_CLOSE = 0.5
#: A depth over this share of the chatter limit is close: the damping and the cutting force are this uncertain.
CHATTER_CLOSE = 0.8
#: The fastest the spindle turns when the study gives no max_spindle_rpm: 24,000 rpm, the high-speed spindle of a
#: common small VMC (FANUC ROBODRILL α-DiB's 24,000 min⁻¹ option; the machining reference's source [13]). A chatter fix
#: never asks for a speed past it.
DEFAULT_MAX_SPINDLE_RPM = 24_000.0
#: A wall is thin, and bends like a plate, when its reach from the clamp is this many times its thickness.
THIN_WALL = 3.0
#: The spindle speeds the lobes are drawn over, as multiples of the study's, and how many.
SPEED_SPAN, SPEEDS = (1.0 / 3.0, 3.0), 1500
#: The lobes are drawn up to this many times the deeper of the cut and the lowest limit: deeper is stable enough.
DRAWN_TO = 25.0
OPERATIONS = ("milling", "turning")
_OPERATION_WORDS = {"mill": "milling", "milling": "milling", "turn": "turning", "turning": "turning", "lathe": "turning"}
_MILLING_WORDS = {"down": "down", "climb": "down", "up": "up", "conventional": "up"}
TOOL_KEYS = ("diameter_mm", "flutes")


@dataclass(frozen=True)
class MachiningInputs(Inputs):
    material: Any = None
    operation: str = "milling"
    diameter_mm: float = 0.0
    flutes: int = 1
    spindle_rpm: float = 0.0
    feed_mm: float = 0.0
    depth_mm: float = 0.0
    width_mm: float = 0.0
    milling: str = "down"
    cut_faces: tuple[str, ...] = ()
    fixtures: tuple[Fixture, ...] = ()
    tolerance_mm: float = DEFAULT_TOLERANCE_MM
    tolerance_given: bool = False
    damping: float = DEFAULT_DAMPING
    #: The fastest the spindle turns: a speed a fix gives is never past it.
    max_spindle_rpm: float = DEFAULT_MAX_SPINDLE_RPM
    #: What the solve found of the cut (the face the cutter pushed on, and the force), for the study's echo.
    solved: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def teeth(self) -> int:
        """The cutting edges a spindle turn brings round: the flutes, or a lathe tool's one."""
        return self.flutes if self.operation == "milling" else 1

    def forces(self) -> dict:
        from cadgen._internal.manufacturing.processes import cutting

        if self.operation == "turning":
            return cutting.turning_forces(self.material, self.depth_mm, self.feed_mm)
        return cutting.milling_forces(self.material, diameter_mm=self.diameter_mm, flutes=self.flutes,
                                      depth_mm=self.depth_mm, width_mm=self.width_mm, feed_mm=self.feed_mm,
                                      milling=self.milling)

    def coefficient(self, forces: dict) -> float:
        """K, N/mm²: how much the force along the normal grows per mm² of chip as the part moves along the normal."""
        from cadgen._internal.manufacturing.processes import cutting

        if self.operation == "turning":
            return self.material.kr * forces["kc_MPa"]
        start, end = forces["engagement_rad"]
        return -self.flutes * forces["kc_MPa"] * cutting.directional_yy(start, end, self.material.kr) / (4.0 * math.pi)


def _parse_tool(document: dict, operation: str) -> tuple[float, int]:
    if operation == "turning":
        if "tool" in document:
            raise ValueError("tool: a turning study takes no tool: the part turns and the tool cuts with one edge; "
                             "give depth_mm and feed_per_tooth_mm (per revolution)")
        return 0.0, 1
    tool = document.get("tool")
    if not isinstance(tool, dict):
        raise ValueError('study.tool: the milling cutter, like {"diameter_mm": 10, "flutes": 3}')
    kinds.known(tool, TOOL_KEYS, "tool", "a milling cutter takes diameter_mm and flutes")
    if "diameter_mm" not in tool:
        raise ValueError('tool.diameter_mm: the cutter\'s diameter, like {"diameter_mm": 10, "flutes": 3}')
    diameter = kinds.number(tool["diameter_mm"], where="tool.diameter_mm", positive=True)
    if "flutes" not in tool:
        raise ValueError('tool.flutes: how many cutting edges the cutter has, like {"diameter_mm": 10, "flutes": 3}')
    flutes = kinds.whole(tool["flutes"], where="tool.flutes", words="a whole number of cutting edges from 1 to 16",
                         high=16)
    return diameter, flutes


class MachiningProcess(Process):
    name: ClassVar[str] = "machining"
    word: ClassVar[str] = "Machining"
    extras_word: ClassVar[str] = "machining"
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "operation", "tool", "spindle_rpm", "feed_per_tooth_mm", "depth_mm", "width_mm", "milling", "cut_faces",
        "fixtures", "tolerance_mm", "damping_ratio", "max_spindle_rpm",
    })
    material_needs: ClassVar[frozenset[str]] = frozenset({"density", "yield_strength"})
    # The displacement first: the viewer opens on it, the deflection under the cut. The stress colours the file.
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("displacement", "_DISPLACEMENT", "displacement under the cut", "mm", 3, 1000.0),
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress under the cut", "MPa"),
        FieldSpec("mode_shape", "_MODE_SHAPE", "the shape it rings in at the cut", "mm"),
    )
    checks: ClassVar[tuple] = ()
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["displacement", "von_mises", "mode_shape"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "defeature", "linear_elements")
    noun: ClassVar[str] = "this cut"

    def material_from_spec(self, spec):
        """The study's ``material``, a workpiece material with its cutting force (the material hook)."""
        from cadgen._internal.manufacturing.processes.cutting import work_material_from_spec

        return work_material_from_spec(spec)

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> MachiningInputs:
        from cadgen._internal.fea.analyses.modal import parse_damping
        from cadgen._internal.manufacturing.processes.cutting import MILLING, work_material_from_spec

        for key in ("parts", "connections"):
            if key in document:
                raise ValueError(f"study.{key}: a machining study cuts one part; solve one occurrence with --occurrence")
        if "material" not in document:
            raise ValueError("study.material: the workpiece material, a name like \"6061-t6\" or an object with its "
                             "cutting force")
        material = work_material_from_spec(document["material"])
        raw = document.get("operation")
        operation = _OPERATION_WORDS.get(raw.strip().lower()) if isinstance(raw, str) else None
        if operation is None:
            raise ValueError(f"study.operation: how it is cut, one of {', '.join(OPERATIONS)}; got {kinds.json_text(raw)}")
        diameter, flutes = _parse_tool(document, operation)
        for key in ("spindle_rpm", "feed_per_tooth_mm", "depth_mm"):
            if key not in document:
                words = {"spindle_rpm": "the spindle speed, rpm",
                         "feed_per_tooth_mm": "the feed per tooth, mm (turning: per revolution)",
                         "depth_mm": "the depth of cut, mm (milling: axial)"}[key]
                raise ValueError(f"study.{key}: {words}")
        rpm = kinds.number(document["spindle_rpm"], where="spindle_rpm", positive=True)
        fastest = DEFAULT_MAX_SPINDLE_RPM
        if "max_spindle_rpm" in document:
            fastest = kinds.number(document["max_spindle_rpm"], where="max_spindle_rpm", positive=True)
        if rpm > fastest:
            raise ValueError(f"spindle_rpm: {rpm:g} rpm is past the spindle's {fastest:g} rpm (max_spindle_rpm"
                             + ("" if "max_spindle_rpm" in document else f", {DEFAULT_MAX_SPINDLE_RPM:g} unless given")
                             + "); give the machine's own max_spindle_rpm")
        feed = kinds.number(document["feed_per_tooth_mm"], where="feed_per_tooth_mm", positive=True)
        depth = kinds.number(document["depth_mm"], where="depth_mm", positive=True)
        width, milling = 0.0, "down"
        if operation == "milling":
            if "width_mm" not in document:
                raise ValueError("study.width_mm: the radial depth of cut, mm: how far into the face the cutter reaches "
                                 "(the cutter's diameter for a slot)")
            width = kinds.number(document["width_mm"], where="width_mm", positive=True)
            if width > diameter:
                raise ValueError(f"width_mm: {width:g} mm is wider than the {diameter:g} mm cutter; a slot is "
                                 f"{diameter:g} mm")
            raw_milling = document.get("milling", "down")
            milling = _MILLING_WORDS.get(raw_milling.strip().lower()) if isinstance(raw_milling, str) else None
            if milling not in MILLING:
                raise ValueError(f"milling: down (climb) or up (conventional), got {kinds.json_text(raw_milling)}")
        else:
            for key in ("width_mm", "milling"):
                if key in document:
                    raise ValueError(f"{key}: a turning cut has none: its chip is depth_mm wide and "
                                     "feed_per_tooth_mm (per revolution) thick")
        if "cut_faces" not in document:
            raise ValueError('study.cut_faces: the faces the cutter is on, like ["#o1.f4"]')
        cut = kinds.faces({"faces": document["cut_faces"]}, where="cut_faces")
        fixtures = parse_fixtures(document)
        held = {ref for fixture in fixtures for ref in fixture.faces}
        if both := [ref for ref in cut if ref in held]:
            raise ValueError(f"cut_faces: {both[0]} is also a fixture; the cutter cuts a face the vise does not hold")
        tolerance, given = DEFAULT_TOLERANCE_MM, "tolerance_mm" in document
        if given:
            tolerance = kinds.number(document["tolerance_mm"], where="tolerance_mm", positive=True)
        damping = parse_damping({"damping_ratio": document.get("damping_ratio", DEFAULT_DAMPING)})
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        refs = tuple(dict.fromkeys((*cut, *anchors)))
        return MachiningInputs(refs, anchors, True, material=material, operation=operation, diameter_mm=diameter,
                               flutes=flutes, spindle_rpm=rpm, feed_mm=feed, depth_mm=depth, width_mm=width,
                               milling=milling, cut_faces=cut, fixtures=fixtures, tolerance_mm=tolerance,
                               tolerance_given=given, damping=damping, max_spindle_rpm=fastest)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: MachiningInputs):
        """The modes of the clamped part and one static solve on its matrix."""
        from cadgen._internal.fea.analyses.modal import eigen_estimate

        return eigen_estimate(ctx, MODES, static_solves=1)

    def apply(self, rung, ctx: SolveContext, inputs: MachiningInputs):
        from cadgen._internal.fea.analyses.modal import apply_eigen_rung

        return apply_eigen_rung(self, rung, ctx, inputs)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: MachiningInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import operators, solve
        from cadgen._internal.manufacturing.processes import cutting, solidification
        from cadgen._internal.fea.analyses.modal import held_supports, solver_method
        from cadgen._internal.fea.superposition import find_modes

        if ctx.assembly is not None:
            raise ValueError("machining: the document holds several parts; a machining study cuts one, so name it "
                             "with --occurrence")
        space, volume = ctx.space, ctx.volume
        material = ctx.materials[0]
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        K = operators.stiffness(space, material)
        M = operators.mass(space, material)
        held = held_supports(space, inputs.fixtures, ctx.ordinal_of, require=True)
        timings["assemble_s"] = time.perf_counter() - started

        # The modes of the clamped part: the lowest MODES (a search for more is the study's to ask of `modal`).
        started = time.perf_counter()
        free = space.dofs - len(held.fixed)
        modes = find_modes(K, M, held, math.inf, method=solver_method(ctx, free), locations=space.locations,
                           component=space.component, start=MODES, cap=MODES)
        warnings.extend(w for w in modes.warnings if "were left out" not in w)
        timings["eigen_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"machining: {len(modes)} modes of the clamped part, from {modes.frequencies_Hz[0]:.4g} Hz")

        # Where on the cut faces the part is most flexible along their normal: the cutter goes there.
        ordinals = np.asarray(volume.boundary_ordinal)
        cut_rows = np.flatnonzero(np.isin(ordinals, [ctx.ordinal_of[ref] for ref in inputs.cut_faces]))
        nodes = space.dof_locations
        triangles = np.asarray(space.boundary_quadratic)[:, :3]
        outward, areas, centroids = _facet_geometry(space, nodes, triangles, cut_rows)
        corner = np.unique(triangles[cut_rows])
        normal_sum = np.zeros((space.scalar_count, 3))
        for column in range(3):
            np.add.at(normal_sum, triangles[cut_rows][:, column], outward * areas[:, None])
        node_normal = normal_sum[corner] / np.maximum(np.linalg.norm(normal_sum[corner], axis=1, keepdims=True), 1e-300)
        compliance = np.zeros(len(corner))
        for r in range(len(modes)):
            shape = space.nodal(modes.vectors[:, r])[corner]
            compliance += np.einsum("ij,ij->i", shape, node_normal) ** 2 / modes.omega[r] ** 2
        at = int(compliance.argmax())
        point, out_normal = nodes[corner[at]], node_normal[at]
        inward = -out_normal

        # The cut: its force along the inward normal, on a patch of the cut faces about the depth of cut across.
        forces = inputs.forces()
        F_n = float(forces["normal_N"])
        radius = max(0.5 * inputs.depth_mm, volume.max_h)
        near = np.linalg.norm(centroids - point, axis=1)
        patch = cut_rows[(near <= radius) & (outward @ out_normal > 0.2)]
        if not len(patch):
            patch = cut_rows[[int(near.argmin())]]
        unit = _unit_load(space, patch, inward)
        pressures = np.zeros(len(ordinals))
        pressures[patch] = F_n * unit["pressure"]
        inputs.solved.update({"face": _face_at(ctx, patch), "vector_N": [float(F_n * c) for c in inward]})
        plan = ctx.plan
        solver = None if plan is None or plan.solver in ("direct", "matrix_free") else plan.solver
        outcome = solve.solve_linear_static(
            volume, material, inputs.fixtures, (), ctx.ordinal_of, log=ctx.log, automatic=ctx.automatic,
            facet_pressures=pressures, solver=solver, space=space,
            calculix_first=bool(plan is not None and plan.solver_for == "time"),
        )
        warnings.extend(outcome.warnings)
        timings.update({f"static_{key}": value for key, value in outcome.timings.items()})
        f_hat = unit["vector"]
        deflection = float(f_hat @ outcome.u)                         # mm along the inward normal, at the cut
        static_compliance = abs(deflection / F_n) if F_n else float(f_hat @ _solve_unit(space, K, held, f_hat, warnings))

        # The transfer function at the cut along the normal: the modes, their damping, and the static solve's rest.
        started = time.perf_counter()
        q = modes.vectors.T @ f_hat
        omega_r = modes.omega
        modal_static = float((q ** 2 / omega_r ** 2).sum())
        residual = max(static_compliance - modal_static, 0.0)
        grid = _frequency_grid(omega_r)
        frf = (q[None, :] ** 2 / (omega_r[None, :] ** 2 - grid[:, None] ** 2
                                   + 2j * inputs.damping * omega_r[None, :] * grid[:, None])).sum(axis=1) + residual
        coefficient = inputs.coefficient(forces)
        low, high = SPEED_SPAN
        rpm = np.unique(np.concatenate([np.geomspace(low * inputs.spindle_rpm, high * inputs.spindle_rpm, SPEEDS),
                                        [inputs.spindle_rpm]]))
        lobes, cap = None, math.inf
        if abs(coefficient) > 1e-12:
            with np.errstate(divide="ignore"):
                limits = -1.0 / (2.0 * coefficient * frf.real)
            positive = limits[np.isfinite(limits) & (limits > 0)]
            cap = DRAWN_TO * max(inputs.depth_mm, float(positive.min()) if len(positive) else inputs.depth_mm)
            lobes = cutting.stability(grid, frf, coefficient, inputs.teeth, rpm, cap_mm=cap)
        timings["lobes_s"] = time.perf_counter() - started
        started = time.perf_counter()

        # The part's section at the cut, and its reach from the clamp: a thin wall bends like a plate.
        # (Each section is measured from one of skfem's boundary facets, in mesh.boundary_facets()'s ascending order.)
        section = solidification.sections(space, np.zeros(space.scalar_count))
        boundary_facets = space.mesh.boundary_facets()
        at_patch = np.searchsorted(boundary_facets, space.facets_of_rows(patch))
        at_patch = at_patch[(at_patch < len(boundary_facets)) & section.measured[np.minimum(at_patch, len(boundary_facets) - 1)]]
        thickness = float(np.median(section.thickness[at_patch])) if len(at_patch) else None
        fixed_rows = np.isin(ordinals, [ctx.ordinal_of[ref] for fixture in inputs.fixtures for ref in fixture.faces])
        reach = float(np.linalg.norm(nodes[np.unique(triangles[fixed_rows])] - point, axis=1).min())

        # The stress the cut puts in the part, away from the patch it pushes on (the chip's own, not the part's).
        away = np.linalg.norm(nodes - point, axis=1) > radius + 2.0 * volume.max_h
        judged = away if away.any() else np.ones(len(nodes), dtype=bool)
        peak_node = int(np.flatnonzero(judged)[np.argmax(outcome.von_mises[judged])])
        # Turning: the tangential force, K_r⁻¹ times the normal one, bends a round part as much again: the stress of both.
        stress_scale = forces["resultant_N"] / abs(F_n) if inputs.operation == "turning" and F_n else 1.0

        # The mode that gives most at the cut: modes at one frequency (a round bar bends alike every way) taken as
        # one, rung along the cut (Σ qᵣ φᵣ over them), so its stiffness along the normal is ω² / Σ qᵣ².
        cluster = _clusters(omega_r)
        share = np.bincount(cluster, weights=q ** 2 / omega_r ** 2)
        members = np.flatnonzero(cluster == int(share.argmax()))
        dominant = int(members[np.argmax(q[members] ** 2)])
        dominant_k = float(omega_r[dominant] ** 2 / (q[members] ** 2).sum()) if (q[members] ** 2).sum() else math.inf
        shape = np.linalg.norm(space.nodal(modes.vectors[:, members] @ q[members]), axis=1)
        shape = shape / max(float(shape.max()), 1e-300)
        timings["post_s"] = time.perf_counter() - started
        curves = {}
        if lobes is not None:
            # The depth the cut stays stable to at each speed, drawn to DRAWN_TO times the deeper of the cut and the
            # lowest limit (a lobe's top, or a speed no lobe reaches, reads as that).
            curves["stability_lobes"] = {"x": [round(float(n), 3) for n in lobes.rpm], "x_unit": "rpm",
                                         "y": [round(float(min(a, cap)), 6) for a in lobes.envelope_mm], "y_unit": "mm"}
        return AnalysisResult(
            dof_locations=outcome.dof_locations, vertices=outcome.vertices, tets=outcome.tets,
            boundary_quadratic=outcome.boundary_quadratic, element_dofs=outcome.element_dofs,
            fields={"displacement": outcome.displacement, "von_mises": outcome.von_mises, "mode_shape": shape},
            deformation=outcome.displacement, curves=curves,
            reactions=list(outcome.reactions), applied=tuple(outcome.applied), dofs=outcome.dofs, solver=outcome.solver,
            timings=timings, warnings=warnings,
            scalars={
                "forces": forces, "coefficient": coefficient, "point": point, "inward": inward, "radius": radius,
                "patch_rows": patch, "deflection": deflection, "static_compliance": static_compliance,
                "residual": residual, "modes": modes, "participation": q, "dominant": dominant, "lobes": lobes,
                "dominant_k": dominant_k,
                "drawn_to_mm": cap,
                "thickness": thickness, "reach": reach, "peak_node": peak_node,
                "peak_MPa": float(outcome.von_mises[peak_node]), "stress_scale": stress_scale,
                "max_displacement": float(np.linalg.norm(outcome.displacement, axis=1).max()),
                "analysis_warnings": list(warnings),
            },
        )

    # -- findings ------------------------------------------------------------------------------------

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: MachiningInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        margin = float(getattr(ctx.study, "margin", 2.0) or 2.0)
        found = [*self._deflection(ctx, result, inputs), *self._stress(ctx, result, inputs, margin),
                 *self._chatter(ctx, result, inputs), self._hand_check(result, inputs)]
        if inputs.material.estimated:
            found.append(finding("info", "cutting_force_estimated",
                                 f"{inputs.material.name} has no published Kienzle values: its cutting force "
                                 f"(k_c1.1 {inputs.material.kc11:g} N/mm², m_c {inputs.material.mc:g}) is an estimate",
                                 "about 2.6 times its tensile strength, the middle of the metals' ratio in the table; "
                                 "give kc11_MPa and mc in the material when you have them"))
        if not inputs.tolerance_given:
            found.append(finding("info", "default_tolerance",
                                 f"No tolerance_mm: the deflection is judged against ±{DEFAULT_TOLERANCE_MM:g} mm, "
                                 "ISO 2768-1's fine class for features up to 6 mm",
                                 "give the drawing's tolerance on the cut faces as tolerance_mm"))
        return by_severity(found)

    def ready_words(self, summary: dict) -> str:
        """The verdict's headline when nothing is to fix: "Ready to cut · 0.0185 mm under the cut · stable to 0.54 mm at
        18000 rpm"."""
        words = f"Ready to cut · {abs(summary['deflection_at_cut_mm']):.3g} mm under the cut"
        chatter = summary["chatter"]
        if chatter.get("limit_mm") is not None:
            words += f" · stable to {chatter['limit_mm']:.3g} mm at {chatter['spindle_rpm']:g} rpm"
        return words

    def _deflection(self, ctx: SolveContext, result: AnalysisResult, inputs: MachiningInputs) -> list[dict]:
        s = result.scalars
        moved, tolerance = abs(s["deflection"]), inputs.tolerance_mm
        point = xyz(s["point"])
        face = _face_at(ctx, s["patch_rows"])
        where = [face, point] if face else [point]
        item = [{"text": "the cutter here moves the face most", "ref": face, "at": point}]
        measured = {"quantity": "deflection under the cut", "value": round(moved, 6), "limit": tolerance, "units": "mm",
                    "pass_when": "below"}
        force = abs(s["forces"]["normal_N"])
        head = (f"Under the cut ({force:.3g} N into the face) the part moves {moved:.3g} mm at {point} mm, where the "
                "cut faces give most")
        found = []
        if moved <= DEFLECTION_CLOSE * tolerance:
            return [finding("info", "deflection_within_tolerance",
                            f"{head}: within the ±{tolerance:g} mm tolerance", "the deflection along the face's normal "
                            "where the cutter pushes; it is cut away as the cutter passes, so it is the error it leaves",
                            item, measured=measured)]
        depth = round_down(inputs.depth_mm * DEFLECTION_CLOSE * tolerance / moved)
        fix = {"action": "reduce_depth", "where": where, "params": {"depth_mm": depth},
               "summary": f"Take the cut in lighter passes, about {depth:g} mm deep (depth_mm), so it moves under half "
                          "the tolerance",
               "alternatives": [{"action": "support", "where": where, "params": {},
                                 "summary": f"Support the face behind the cut at {point} mm (a backing block, a "
                                            "clamp nearer the cut, or wax or filler behind a thin wall)"}]}
        if moved > tolerance:
            found.append(finding("error", "deflection_over_tolerance",
                                 f"{head}: more than the ±{tolerance:g} mm tolerance, so the face is cut out of "
                                 "tolerance", "the deflection along the face's normal where the cutter pushes; the "
                                 "force grows with the depth of cut, so a lighter pass moves it less",
                                 item, measured=measured, fix=fix))
        else:
            found.append(finding("warning", "deflection_close_to_tolerance",
                                 f"{head}: over half the ±{tolerance:g} mm tolerance, leaving little for the rest",
                                 "the deflection along the face's normal where the cutter pushes", item,
                                 measured=measured, fix=fix))
        thickness, reach = s["thickness"], s["reach"]
        if thickness is None or reach < THIN_WALL * thickness:
            return found
        stiffer = moved / (DEFLECTION_CLOSE * tolerance)
        severity = "error" if moved > tolerance else "warning"
        why = "the stiffness asked for keeps the deflection under half the tolerance"
        if inputs.operation == "turning":
            # A round bar's bending stiffness grows as the fourth power of its diameter.
            wider = round_up(thickness * stiffer ** 0.25)
            found.append(finding(
                severity, "slender_part_too_flexible",
                f"The part at the cut is {thickness:.2g} mm across and reaches {reach:.3g} mm from the chuck: too "
                f"slender for this cut. It needs to be {stiffer:.2g} times stiffer: support its end (a tailstock centre "
                f"or a steady rest), hold it shorter, or make it about {wider:g} mm across",
                f"a round bar bends as the fourth power of its diameter; {why}", item, measured=measured,
                fix={"action": "support", "where": where, "params": {"stiffness_factor": round(stiffer, 3)},
                     "summary": f"Support the free end with a tailstock centre or a steady rest, {stiffer:.2g} times "
                                "stiffer at the cut",
                     "alternatives": [{"action": "thicken", "where": where,
                                       "params": {"diameter_mm": wider, "from_mm": round(thickness, 2)},
                                       "summary": f"Make it about {wider:g} mm across, or hold it shorter in the chuck"}]}))
            return found
        thicker = round_up(thickness * stiffer ** (1.0 / 3.0))
        found.append(finding(
            severity, "thin_wall_too_flexible",
            f"The wall at the cut is {thickness:.2g} mm thick and reaches {reach:.3g} mm from the clamp: too flexible "
            f"for this cut. It needs to be {stiffer:.2g} times stiffer, about {thicker:g} mm thick, or cut it before "
            "the wall is thinned (rough both sides first and finish it in light passes from the free edge down), or "
            "support it behind the cut", f"a plate bends as the cube of its thickness; {why}", item, measured=measured,
            fix={"action": "thicken", "where": where,
                 "params": {"thickness_mm": thicker, "from_mm": round(thickness, 2), "stiffness_factor": round(stiffer, 3)},
                 "summary": f"Thicken the wall to about {thicker:g} mm, {stiffer:.2g} times stiffer at the cut",
                 "alternatives": [
                     {"action": "rough_before_finishing", "where": where, "params": {},
                      "summary": "Rough both sides of the wall first, then finish it in light passes from the free edge "
                                 "down, while the stock below still stiffens it"},
                     {"action": "support", "where": where, "params": {},
                      "summary": "Support the wall behind the cut (a backing block, wax or low-melt filler)"}]}))
        return found

    def _stress(self, ctx: SolveContext, result: AnalysisResult, inputs: MachiningInputs, margin: float) -> list[dict]:
        s = result.scalars
        stress = s["peak_MPa"] * s["stress_scale"]
        yield_MPa = inputs.material.yield_strength
        factor = yield_MPa / stress if stress > 0 else math.inf
        node = s["peak_node"]
        point = xyz(result.dof_locations[node])
        item = [{"text": "the stress the cut puts in it peaks here", "ref": None, "at": point}]
        words = " (the tangential force's too)" if inputs.operation == "turning" else ""
        head = f"The cut puts {stress:.3g} MPa{words} in the part at {point} mm, against its {yield_MPa:g} MPa yield"
        measured = {"quantity": "stress from the cut (yield over the margin)", "value": round(stress, 4),
                    "limit": round(yield_MPa / margin, 4), "units": "MPa", "pass_when": "below"}
        if factor >= margin:
            return [finding("info", "clamp_stress_ok", f"{head}: a safety factor of {floor3(factor):g}",
                            "the peak away from where the cutter pushes, judged against yield over the study's margin",
                            item, measured=measured)]
        depth = round_down(inputs.depth_mm * factor / margin)
        fix = {"action": "reduce_depth", "where": [point], "params": {"depth_mm": depth},
               "summary": f"Cut about {depth:g} mm deep (depth_mm), so the stress keeps the {margin:g} margin under yield",
               "alternatives": [{"action": "support", "where": [point], "params": {},
                                 "summary": f"Clamp it closer to the cut, or support it near {point} mm"}]}
        if factor < 1:
            return [finding("error", "yields_under_cut", f"{head}: it yields, and the part is bent for good",
                            "the peak away from where the cutter pushes; the force grows with the depth of cut. A sharp "
                            "inside corner's peak grows as the mesh is refined: read the stress a little away from it",
                            item, measured=measured, fix=fix)]
        return [finding("warning", "clamp_stress_close", f"{head}: a safety factor of {floor3(factor):g}, under the "
                        f"{margin:g} the study keeps", "the peak away from where the cutter pushes", item,
                        measured=measured, fix=fix)]

    def _chatter(self, ctx: SolveContext, result: AnalysisResult, inputs: MachiningInputs) -> list[dict]:
        import numpy as np

        s = result.scalars
        lobes = s["lobes"]
        rpm, depth = inputs.spindle_rpm, inputs.depth_mm
        what = "axial depth" if inputs.operation == "milling" else "depth of cut"
        if lobes is None:
            return [finding("info", "chatter_stable", "The cut's force does not change along the face's normal as the "
                            "part moves along it: no regenerative chatter in that direction",
                            "the averaged directional factor of this engagement is zero")]
        limit = float(lobes.envelope_mm[np.searchsorted(lobes.rpm, rpm)])
        speed = f"{rpm:g} rpm"
        quantity = f"{what} against the chatter limit at {speed}"
        if not math.isfinite(limit):
            drawn = s["drawn_to_mm"]
            return [finding("info", "chatter_stable", f"At {speed} no stability lobe comes under {drawn:.3g} mm {what}: "
                            f"it cuts {depth:g} mm, no chatter", "the lobes are drawn to "
                            f"{DRAWN_TO:g} times the deeper of the cut and the lowest limit",
                            measured={"quantity": quantity, "value": depth, "limit": round(drawn, 6), "units": "mm",
                                      "pass_when": "below"})]
        measured = {"quantity": quantity, "value": depth, "limit": round(limit, 6), "units": "mm", "pass_when": "below"}
        point = xyz(s["point"])
        item = [{"text": "chatter starts here", "ref": inputs.solved.get("face"), "at": point}]
        head = f"At {speed} the cut stays stable to {limit:.3g} mm {what}"
        if depth <= CHATTER_CLOSE * limit:
            return [finding("info", "chatter_stable", f"{head}; it cuts {depth:g} mm: no chatter",
                            "the regenerative stability lobe at this spindle speed", item, measured=measured)]
        fix = _chatter_fix(lobes, inputs, limit, point)
        if depth > limit:
            return [finding("error", "chatter", f"{head}; it cuts {depth:g} mm, so it chatters: a rough, wavy face and a "
                            "hammered tool", "the regenerative stability lobe at this spindle speed: past it, the "
                            "waves the last tooth left grow with every pass", item, measured=measured, fix=fix)]
        return [finding("warning", "chatter_close", f"{head}; it cuts {depth:g} mm, within "
                        f"{(1 - CHATTER_CLOSE) * 100:.0f} % of it", "the damping and the cutting force are uncertain to "
                        "about that much", item, measured=measured, fix=fix)]

    def _hand_check(self, result: AnalysisResult, inputs: MachiningInputs) -> dict:
        s = result.scalars
        modes, dominant = s["modes"], s["dominant"]
        f = float(modes.frequencies_Hz[dominant])
        k = s["dominant_k"]
        zeta = inputs.damping
        coefficient = s["coefficient"]
        lobes = s["lobes"]
        tlusty = 2.0 * k * zeta * (1.0 + zeta) / abs(coefficient) if coefficient else math.inf
        lowest = lobes.absolute_mm if lobes is not None else math.inf
        ratio = lowest / tlusty if tlusty and math.isfinite(tlusty) and math.isfinite(lowest) else None
        return finding("info", "hand_check",
                       f"The part rings at the cut at {f:.4g} Hz (mode {dominant + 1}, {k:.3g} N/mm along the normal, "
                       f"{zeta * 100:g} % damping): Tlusty's one-mode limit, 2 k ζ (1 + ζ) / K = {tlusty:.3g} mm at any "
                       f"speed; the lobes' lowest is {lowest:.3g} mm" + (f" ({ratio:.2g} times)" if ratio else ""),
                       f"K = {abs(coefficient):.4g} N/mm², the cut's force along the normal per mm² of chip; the other "
                       "modes and the residual compliance make up the difference")

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        from cadgen._internal.fea.outputs import auto_deformation_scale

        return requested or auto_deformation_scale(result.scalars["max_displacement"], bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: MachiningInputs, check_results: list[dict]) -> dict:
        import numpy as np

        s = result.scalars
        forces, modes, q, lobes = s["forces"], s["modes"], s["participation"], s["lobes"]
        stress = s["peak_MPa"] * s["stress_scale"]
        yield_MPa = inputs.material.yield_strength

        def finite(value) -> float | None:
            return round(float(value), 6) if value is not None and math.isfinite(value) else None

        chatter: dict[str, Any] = {"spindle_rpm": inputs.spindle_rpm, "max_spindle_rpm": inputs.max_spindle_rpm,
                                   "depth_mm": inputs.depth_mm,
                                   "tooth_frequency_Hz": round(inputs.spindle_rpm * inputs.teeth / 60.0, 4),
                                   "damping_ratio": inputs.damping, "cutting_coefficient_MPa": round(s["coefficient"], 4)}
        if lobes is not None:
            limit = float(lobes.envelope_mm[np.searchsorted(lobes.rpm, inputs.spindle_rpm)])
            below, above = _stable_neighbours(lobes, inputs.spindle_rpm, inputs.depth_mm, inputs.max_spindle_rpm)
            chatter.update({
                "limit_mm": finite(limit), "stable": bool(inputs.depth_mm <= limit),
                "absolute_limit_mm": finite(lobes.absolute_mm),
                "absolute_limit_at_Hz": round(lobes.absolute_omega / (2 * math.pi), 4),
                "nearest_stable_rpm": {"below": finite(below), "above": finite(above)},
                "pockets": [{"rpm": round(n, 1), "limit_mm": round(a, 6)} for n, a in _pockets(lobes, inputs.spindle_rpm)
                            if n <= inputs.max_spindle_rpm],
                "lobes": lobes.lobes, "drawn_to_mm": finite(s["drawn_to_mm"]),
            })
        summary = {
            "operation": inputs.operation,
            "material": inputs.material.name,
            "cut": {key: value for key, value in (
                ("tool_diameter_mm", inputs.diameter_mm or None), ("flutes", inputs.flutes if inputs.operation == "milling" else None),
                ("spindle_rpm", inputs.spindle_rpm), ("feed_per_tooth_mm", inputs.feed_mm), ("depth_mm", inputs.depth_mm),
                ("width_mm", inputs.width_mm or None), ("milling", inputs.milling if inputs.operation == "milling" else None),
            ) if value is not None},
            "kienzle": {"kc11_MPa": inputs.material.kc11, "mc": inputs.material.mc, "kr": inputs.material.kr,
                        "chip_mm": round(forces["chip_mm"], 6), "kc_MPa": round(forces["kc_MPa"], 4),
                        "estimated": inputs.material.estimated},
            "force_tangential_N": round(forces["tangential_N"], 4),
            "force_normal_N": round(forces["normal_N"], 4),
            "force_resultant_N": round(forces["resultant_N"], 4),
            "cut_at_mm": xyz(s["point"]),
            "cut_normal": [round(float(c), 6) for c in s["inward"]],
            "patch_radius_mm": round(s["radius"], 4),
            "deflection_at_cut_mm": round(s["deflection"], 9),
            "tolerance_mm": inputs.tolerance_mm,
            "tolerance_given": inputs.tolerance_given,
            "max_displacement_mm": round(s["max_displacement"], 9),
            "static_compliance_mm_per_N": s["static_compliance"],
            "section_at_cut_mm": None if s["thickness"] is None else round(s["thickness"], 4),
            "reach_from_clamp_mm": round(s["reach"], 4),
            "max_von_mises_MPa": round(stress, 4),
            "max_von_mises_at_mm": xyz(result.dof_locations[s["peak_node"]]),
            "yield_MPa": yield_MPa,
            "safety_factor": floor3(yield_MPa / stress) if stress > 0 else None,
            "modes": [{"mode": r + 1, "frequency_Hz": round(float(f), 4),
                       "modal_stiffness_N_per_mm": finite(modes.omega[r] ** 2 / q[r] ** 2) if q[r] else None}
                      for r, f in enumerate(modes.frequencies_Hz)],
            "dominant_mode": s["dominant"] + 1,
            # Its stiffness along the normal at the cut, every mode at its frequency together (a round bar's pair).
            "dominant_modal_stiffness_N_per_mm": finite(s["dominant_k"]),
            "residual_compliance_mm_per_N": s["residual"],
            "chatter": chatter,
            "deformation_scale": s["deformation_scale"],
            "checks": check_results,
        }
        return summary

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"displacement": (0.0, summary["max_displacement_mm"]),
                "von_mises": (0.0, float(result.fields["von_mises"].max())), "mode_shape": (0.0, 1.0)}

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: MachiningInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        forces = inputs.forces()
        echo: dict[str, Any] = {
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "cut_faces": bare(inputs.cut_faces),
            "operation": inputs.operation,
            "material_cutting": {"kc11_MPa": inputs.material.kc11, "mc": inputs.material.mc, "kr": inputs.material.kr,
                                 "group": inputs.material.group, "estimated": inputs.material.estimated},
            "spindle_rpm": inputs.spindle_rpm, "feed_per_tooth_mm": inputs.feed_mm, "depth_mm": inputs.depth_mm,
            "tolerance_mm": inputs.tolerance_mm, "damping_ratio": inputs.damping,
            "max_spindle_rpm": inputs.max_spindle_rpm,
            "cut_force_N": round(abs(forces["normal_N"]), 4),
        }
        if inputs.solved.get("face"):
            # The cut as the force it put on the face the cutter was on: the viewer's Pushed row and its arrow.
            echo["loads"] = [{"type": "force", "faces": [inputs.solved["face"]],
                              "vector_N": [round(c, 4) for c in inputs.solved["vector_N"]]}]
        if inputs.operation == "milling":
            echo.update({"tool": {"diameter_mm": inputs.diameter_mm, "flutes": inputs.flutes},
                         "width_mm": inputs.width_mm, "milling": inputs.milling})
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        chatter = summary["chatter"]
        lines = [
            f"under the cut: {abs(summary['deflection_at_cut_mm']):.3g} mm at {summary['cut_at_mm']} mm "
            f"(tolerance ±{summary['tolerance_mm']:g} mm); peak stress {summary['max_von_mises_MPa']:.3g} MPa "
            f"(yield {summary['yield_MPa']:g} MPa)",
            f"cutting force {abs(summary['force_normal_N']):.3g} N into the face (Kienzle k_c "
            f"{summary['kienzle']['kc_MPa']:.4g} N/mm² at a {summary['kienzle']['chip_mm']:.3g} mm chip)",
        ]
        modes = summary["modes"]
        if modes:
            dominant = modes[summary["dominant_mode"] - 1]
            lines.append(f"rings at the cut at {dominant['frequency_Hz']:.4g} Hz (mode {dominant['mode']}, "
                         f"{summary['dominant_modal_stiffness_N_per_mm'] or math.inf:.3g} N/mm along the normal)")
        if chatter.get("limit_mm") is not None:
            nearest = chatter["nearest_stable_rpm"]
            lines.append(f"stable to {chatter['limit_mm']:.3g} mm at {chatter['spindle_rpm']:g} rpm (cutting "
                         f"{chatter['depth_mm']:g} mm), to {chatter['absolute_limit_mm']:.3g} mm at any speed"
                         + (f"; stable for this depth at {nearest['below']:.0f} or {nearest['above']:.0f} rpm"
                            if not chatter["stable"] and nearest["below"] and nearest["above"] else ""))
        return lines


# -- helpers -----------------------------------------------------------------------------------------

def round_down(value: float) -> float:
    """Two significant figures, rounded down: a depth the fix gives that is never more than it should be."""
    if not value > 0:
        return 0.0
    exponent = math.floor(math.log10(value)) - 1
    return round(math.floor(value / 10 ** exponent * (1 + 1e-12)) * 10 ** exponent, max(0, -exponent))


def round_up(value: float) -> float:
    """To the tenth of a millimetre above."""
    return math.ceil(value * 10.0 - 1e-9) / 10.0


def floor3(value: float) -> float:
    return math.floor(value * 1000) / 1000


def _face_at(ctx: SolveContext, rows) -> str | None:
    """The face the patch's first triangle lies on."""
    ordinal = int(ctx.volume.boundary_ordinal[int(rows[0])]) if len(rows) else None
    face = ctx.volume.faces.get(ordinal) if ordinal is not None else None
    return face.ref if face is not None else None


def _facet_geometry(space, nodes, triangles, rows):
    """(outward unit normals, areas, centroids) of boundary triangles ``rows``: each normal turned away from the tet
    behind it."""
    import numpy as np

    corners = nodes[triangles[rows]]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    normal = cross / np.maximum(2.0 * areas, 1e-300)[:, None]
    centroids = corners.mean(axis=1)
    facets = space.facets_of_rows(rows)
    elements = space.mesh.f2t[0, facets]
    middle = nodes[np.asarray(space.mesh.t)[:, elements].T].mean(axis=1)
    flip = np.einsum("ij,ij->i", middle - centroids, normal) > 0
    normal[flip] *= -1.0
    return normal, areas, centroids


def _unit_load(space, rows, inward) -> dict:
    """A uniform pressure on boundary triangles ``rows`` that pushes 1 N along ``inward`` in all: its load vector
    (N on every vector DOF) and the pressure, MPa per N."""
    import numpy as np
    from skfem import LinearForm, asm

    facet_basis = space.basis.boundary(space.facets_of_rows(rows))

    @LinearForm
    def surface(v, w):
        return -(w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

    vector = asm(surface, facet_basis)
    total = np.array([vector[space.component == c].sum() for c in range(3)])
    along = float(total @ np.asarray(inward))
    if not along > 0:
        raise ValueError("machining: the cut faces near the cutter face every way at once; name the faces the cutter "
                         "is on, not the whole part")
    return {"vector": vector / along, "pressure": 1.0 / along}


def _solve_unit(space, K, held, load, warnings):
    """The displacement under ``load`` (a vector on every DOF), the supports held: for a cut whose normal force is nil."""
    import numpy as np

    from cadgen._internal.fea.operators import solve_spd

    free = held.free(space.dofs)
    local = np.zeros(space.dofs)
    local[free], _ = solve_spd(held.local(K), held.local_vector(load), free, space.locations, space.component, warnings)
    return held.global_vector(local)


def _clusters(omega_r, within: float = 2e-3):
    """Each mode's cluster: modes whose frequencies are within ``within`` of the cluster's lowest share one."""
    import numpy as np

    labels = np.zeros(len(omega_r), dtype=np.int64)
    start = 0
    for index in range(1, len(omega_r)):
        if omega_r[index] - omega_r[start] > within * omega_r[start]:
            start = index
        labels[index] = labels[index - 1] + (start == index)
    return labels


def _frequency_grid(omega_r):
    """Chatter frequencies to search, rad/s: from a third of the lowest mode to three times the highest, dense near
    every mode (just above each is where it chatters)."""
    import numpy as np

    low, high = float(omega_r.min()) / 3.0, float(omega_r.max()) * 3.0
    pieces = [np.geomspace(low, high, 4000)]
    for omega in omega_r:
        pieces.append(np.linspace(0.95 * omega, 1.3 * omega, 1500))
    return np.unique(np.concatenate(pieces))


def _pockets(lobes, rpm: float, count: int = 3) -> list[tuple[float, float]]:
    """The stable pockets nearest ``rpm``: the envelope's local peaks between lobes, (speed, depth)."""
    import numpy as np

    env = lobes.envelope_mm
    finite = np.isfinite(env)
    inner = np.flatnonzero(finite[1:-1] & finite[:-2] & finite[2:]) + 1
    peaks = inner[(env[inner] >= env[inner - 1]) & (env[inner] >= env[inner + 1])]
    order = peaks[np.argsort(np.abs(np.log(lobes.rpm[peaks] / rpm)))][:count]
    return [(float(lobes.rpm[i]), float(env[i])) for i in sorted(order, key=lambda i: lobes.rpm[i])]


def _chatter_fix(lobes, inputs: MachiningInputs, limit: float, point) -> dict:
    """The fix of a cut at or near its chatter limit: the depth that keeps it clear of :data:`CHATTER_CLOSE` at the
    spindle's speed, always; a stable pocket's speed for the depth it cuts as an alternative, only where one lies within
    the spindle's ``max_spindle_rpm``."""
    rpm, depth = inputs.spindle_rpm, inputs.depth_mm
    safe = round_down(CHATTER_CLOSE * limit)
    fix = {"action": "reduce_depth", "where": [point], "params": {"depth_mm": safe},
           "summary": f"Cut about {safe:g} mm deep (depth_mm) at {rpm:g} rpm, under the chatter limit"}
    better = _better_speed(lobes, rpm, depth, inputs.max_spindle_rpm)
    if better is not None:
        fix["alternatives"] = [{
            "action": "change_speed", "where": [point], "params": {"spindle_rpm": round(better)},
            "summary": f"Or run the spindle at about {better:.0f} rpm (spindle_rpm), a stable pocket for {depth:g} mm "
                       f"within its {inputs.max_spindle_rpm:g} rpm; the pocket stands on the lobes' damping, so cut a "
                       "test piece there first"}]
    return fix


def _better_speed(lobes, rpm: float, depth: float, fastest: float) -> float | None:
    """The nearest speed up to ``fastest`` whose pocket keeps ``depth`` clear of :data:`CHATTER_CLOSE`: a pocket's peak
    where one does, else the nearest speed that does; ``None`` when no speed drawn under ``fastest`` does."""
    import numpy as np

    env = lobes.envelope_mm
    wanted = depth / CHATTER_CLOSE
    peaks = [(n, a) for n, a in _pockets(lobes, rpm, count=len(env)) if a >= wanted and math.isfinite(a) and n <= fastest]
    if peaks:
        return min(peaks, key=lambda pair: abs(math.log(pair[0] / rpm)))[0]
    clear = np.flatnonzero((env >= wanted) & (lobes.rpm <= fastest))
    if not len(clear):
        return None
    return float(lobes.rpm[clear[np.argmin(np.abs(np.log(lobes.rpm[clear] / rpm)))]])


def _stable_neighbours(lobes, rpm: float, depth: float, fastest: float) -> tuple[float | None, float | None]:
    """The nearest speeds below and above ``rpm`` (inclusive) at which ``depth`` is stable, among those drawn up to the
    spindle's ``fastest``."""
    import numpy as np

    stable = (lobes.envelope_mm >= depth) & (lobes.rpm <= fastest)
    below = np.flatnonzero(stable & (lobes.rpm <= rpm))
    above = np.flatnonzero(stable & (lobes.rpm >= rpm))
    return (float(lobes.rpm[below[-1]]) if len(below) else None, float(lobes.rpm[above[0]]) if len(above) else None)
