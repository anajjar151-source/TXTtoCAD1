"""What every manufacturing process shares: its base class, the closed set of its findings, and the maker that holds it.

A process is an analysis the FEA pipeline solves on its mesh (``cadgen._internal.fea.analyses.base``'s protocol), held
in this package's registry rather than fea's. :class:`Process` gives the defaults a process differs from an analysis by:
it reads its material its own way (an ``alloy``, a ``resin``, a ``steel``, a sheet, a workpiece), never the solver's
material table, through the one material hook every analysis has (``material_from_spec``).

A finding is fea's dict (``check``, ``severity``, ``type``, ``summary``, ``description``, ``items``, and the ``measured``
and ``fix`` a check carries; ``cadgen._internal.checklist`` reads it as a CI check does), its ``check`` the process's
name. :data:`FINDING_TYPES` closes the vocabulary (law 9): each process's types, the severities each is made at and the
fix actions it can carry, first or as an alternative. :func:`finding_of` makes a process's findings and refuses any type,
severity or action not listed there; the run's own (``check`` ``fea``: a march stopped at its time limit, each step the
fit-the-budget ladder took) are checked by :func:`closed` before a result is returned. The skill's checks.md names
every one, and a test keeps the two in step.

Stdlib only at import.
"""

from __future__ import annotations

from typing import Any, ClassVar, NamedTuple

from cadgen._internal.fea.analyses.base import AnalysisBase, finding as fea_finding

__all__ = ["FINDING_TYPES", "Kind", "Process", "RUN", "closed", "finding_of"]

#: The ``check`` of the findings the run makes itself, whatever the process: the FEA pipeline's.
RUN = "fea"


class Kind(NamedTuple):
    """A finding type: the severities it is made at, and the fix actions it can carry (none for a pass or a note)."""

    severities: tuple[str, ...]
    actions: tuple[str, ...] = ()


_INFO, _WARNING, _ERROR = ("info",), ("warning",), ("error",)
_PASS_OR_WARN, _PASS_OR_FAIL, _WARN_OR_FAIL = ("info", "warning"), ("info", "error"), ("warning", "error")

#: Every finding a check can carry, by ``check`` (the process, or ``fea`` for the run's own): its closed set of types.
FINDING_TYPES: dict[str, dict[str, Kind]] = {
    "casting": {
        "misrun": Kind(_ERROR, ("thicken", "raise_mold_temperature", "move_gate")),
        "misrun_risk": Kind(_WARNING, ("thicken", "raise_mold_temperature", "move_gate")),
        "thinnest_section": Kind(_INFO),
        "shrinkage_hot_spot": Kind(_ERROR, ("add_feeder", "enlarge_feeder", "thin", "add_chill")),
        "no_hot_spot": Kind(_INFO),
        "low_niyama": Kind(_WARNING, ("add_feeder", "enlarge_feeder", "add_chill")),
        "niyama_ok": Kind(_INFO),
        "niyama_no_threshold": Kind(_INFO),
        "hand_check": Kind(_INFO),
        "hand_check_far": Kind(_WARNING, ("check_inputs",)),
        "not_solid": Kind(_WARNING, ("set_duration", "coarsen_mesh")),
        "no_feeder": Kind(_INFO),
        "pure_metal": Kind(_INFO),
    },
    "molding": {
        "cooling_time": Kind(_INFO),
        "not_ejectable": Kind(_WARNING, ("check_inputs",)),
        "sink_void": Kind(_ERROR, ("thin",)),
        "sink_risk": Kind(_WARNING, ("thin",)),
        "no_sink": Kind(_INFO),
        "thin_wall": Kind(_WARNING, ("thicken",)),
        "thinnest_wall": Kind(_INFO),
        "thick_wall": Kind(_WARNING, ("thin",)),
        "thickest_wall": Kind(_INFO),
        "warp": Kind(_INFO),
        "warp_over_tolerance": Kind(_ERROR, ("thin",)),
        "warp_within_tolerance": Kind(_INFO),
        "melt_window": Kind(_INFO),
        "melt_outside_window": Kind(_WARNING, ("change_process",)),
        "mold_window": Kind(_INFO),
        "mold_outside_window": Kind(_WARNING, ("change_process",)),
        "mesh_across_wall": Kind(_INFO),
        "coarse_mesh": Kind(_WARNING, ("refine_mesh",)),
        "hand_check": Kind(_INFO),
        "hand_check_far": Kind(_WARNING, ("check_inputs",)),
        "fibre_filled": Kind(_INFO),
    },
    "heat_treatment": {
        "hardness": Kind(_INFO),
        "target_hardness": Kind(_INFO),
        "soft_spot": Kind(_ERROR, ("change_material", "change_quenchant", "thin")),
        "quench_stress": Kind(_INFO),
        "quench_yield": Kind(_WARNING, ("change_quenchant",)),
        "crack_risk": Kind(_PASS_OR_WARN, ("add_fillet",)),
        "distortion": Kind(_PASS_OR_WARN, ("change_quenchant",)),
        "section_change": Kind(_PASS_OR_WARN, ("thin",)),
        "hand_check": Kind(_INFO),
        "hand_check_far": Kind(_WARNING, ("refine_mesh",)),
        "not_cooled": Kind(_WARNING, ("check_inputs", "coarsen_mesh")),
        "beyond_jominy": Kind(_INFO),
        "estimated_curve": Kind(_INFO),
        "core_only": Kind(_INFO),
    },
    "machining": {
        "deflection_within_tolerance": Kind(_INFO),
        "deflection_close_to_tolerance": Kind(_WARNING, ("reduce_depth", "support")),
        "deflection_over_tolerance": Kind(_ERROR, ("reduce_depth", "support")),
        "thin_wall_too_flexible": Kind(_WARN_OR_FAIL, ("thicken", "rough_before_finishing", "support")),
        "slender_part_too_flexible": Kind(_WARN_OR_FAIL, ("support", "thicken")),
        "clamp_stress_ok": Kind(_INFO),
        "clamp_stress_close": Kind(_WARNING, ("reduce_depth", "support")),
        "yields_under_cut": Kind(_ERROR, ("reduce_depth", "support")),
        "chatter_stable": Kind(_INFO),
        "chatter_close": Kind(_WARNING, ("reduce_depth", "change_speed")),
        "chatter": Kind(_ERROR, ("reduce_depth", "change_speed")),
        "hand_check": Kind(_INFO),
        "cutting_force_estimated": Kind(_INFO),
        "default_tolerance": Kind(_INFO),
    },
    "printing": {
        "warp": Kind(_PASS_OR_FAIL, ("raise_chamber_temperature", "change_orientation", "stress_relieve", "add_rib")),
        "distortion": Kind(_PASS_OR_FAIL,
                           ("raise_chamber_temperature", "change_orientation", "stress_relieve", "add_rib")),
        "release_distortion": Kind(_PASS_OR_FAIL,
                                   ("raise_chamber_temperature", "change_orientation", "stress_relieve", "add_rib")),
        "residual_stress": Kind(_PASS_OR_WARN, ("stress_relieve", "raise_chamber_temperature", "change_orientation")),
        "recoater_collision": Kind(_PASS_OR_WARN, ("support",)),
        "bed_adhesion": Kind(_PASS_OR_WARN, ("add_brim",)),
        "starts_in_air": Kind(_INFO),
        "sls_no_build_shrinkage": Kind(_INFO),
        "hand_check": Kind(_INFO),
        "hand_check_far": Kind(_WARNING, ("check_inputs",)),
    },
    "welding": {
        "distortion": Kind(_PASS_OR_FAIL, ("reduce_heat_input", "balance_welds", "preset", "thicken")),
        "angular_distortion": Kind(_INFO),
        "bowing": Kind(_PASS_OR_WARN, ("check_inputs",)),
        "residual_stress": Kind(_PASS_OR_WARN, ("stress_relieve",)),
        "hand_check": Kind(_INFO),
        "hand_check_far": Kind(_WARNING, ("check_inputs",)),
    },
    "sheet_metal": {
        "bend_may_crack": Kind(_ERROR, ("increase_radius", "turn_blank", "softer_temper")),
        "bend_formable": Kind(_INFO),
        "bend_takes_no_set": Kind(_ERROR, ("reduce_radius", "form_in_die")),
        "springback_over_tolerance": Kind(_WARNING, ("overbend",)),
        "springback_within_tolerance": Kind(_INFO),
        "springback_work_hardening": Kind(_WARNING, ("test_bend",)),
        "springback_work_hardening_within_tolerance": Kind(_INFO),
        "angle_error_over_tolerance": Kind(_WARNING, ("overbend",)),
        "angle_error_within_tolerance": Kind(_INFO),
        "relief_missing": Kind(_WARNING, ("add_relief", "extend_bend")),
        "reliefs": Kind(_INFO),
        "thickness_differs": Kind(_WARNING, ("set_thickness", "set_study_thickness")),
        "thickness_matches": Kind(_INFO),
        "bend_closes_loop": Kind(_INFO),
        "sheet_metal_estimate": Kind(_INFO),
    },
    # The run's own, whatever the process: a march stopped at its time limit (casting, molding, heat_treatment), and
    # each rung of the fit-the-budget ladder a process takes (its ``ladder``), or the run's note that it did not fit.
    RUN: {
        "time_limit": Kind(_WARNING, ("raise_time_limit",)),
        "fit_iterative": Kind(_INFO),
        "fit_defeature": Kind(_INFO),
        "fit_linear_elements": Kind(_INFO),
        "fit_budget": Kind(_INFO),
    },
}


def _refuse(check: str, kind: str, severity: str, fix: dict | None) -> None:
    """A ValueError when ``check``'s finding of ``kind`` at ``severity`` with ``fix`` is outside :data:`FINDING_TYPES`:
    a bug in cadgen, never in the part."""
    kinds = FINDING_TYPES.get(check, {})
    if kind not in kinds:
        raise ValueError(f"finding type {kind!r} of {check!r} is not in FINDING_TYPES")
    if severity not in kinds[kind].severities:
        raise ValueError(f"finding {check}/{kind} is made at {', '.join(kinds[kind].severities)}, not {severity!r}")
    for each in (fix, *(fix or {}).get("alternatives", ())):
        if each and each.get("action") not in kinds[kind].actions:
            raise ValueError(f"finding {check}/{kind} carries no fix action {each.get('action')!r}")


def finding_of(process: str):
    """The finding maker of ``process``: fea's :func:`~cadgen._internal.fea.analyses.base.finding`, its ``check`` the
    process, refusing a type, severity or fix action :data:`FINDING_TYPES` does not list for it."""
    if process not in FINDING_TYPES:
        raise ValueError(f"{process!r} has no FINDING_TYPES")

    def finding(severity: str, kind: str, summary: str, description: str, items=(), *,
                measured: dict | None = None, fix: dict | None = None) -> dict:
        _refuse(process, kind, severity, fix)
        return {**fea_finding(severity, kind, summary, description, items, measured=measured, fix=fix),
                "check": process}

    finding.__doc__ = f"One finding of {process}'s checks (:func:`cadgen._internal.fea.analyses.base.finding`)."
    return finding


def closed(process: str, findings) -> None:
    """Every finding of a run of ``process`` is the process's own or the run's (``fea``), of a type, severity and fix
    action :data:`FINDING_TYPES` lists: a ValueError naming the first that is not."""
    for found in findings:
        check = found.get("check")
        if check not in (process, RUN):
            raise ValueError(f"a {process} check made a finding of {check!r}")
        _refuse(check, found.get("type"), found.get("severity"), found.get("fix"))


class Process(AnalysisBase):
    """A manufacturing process: an analysis of fea's protocol, solved by fea's pipeline, held in this package's
    registry. Its material is never the solver's table's: a process names it its own way and reads it in its ``parse``,
    so the material hook gives nothing (machining's workpiece materials override it)."""

    material_required: ClassVar[bool] = False

    def material_from_spec(self, spec: Any):
        return None
