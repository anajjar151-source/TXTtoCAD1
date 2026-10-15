# Welding (`welding`)

The distortion and residual stress welds leave in the part they join: how far each joint closes
(angular distortion), how far a long weld bows the part, whether the part stays in tolerance, and the
stress along the welds. Lite: read [Limits](#limits) before you report.

## When to use it

- "How much will it distort", "will this T stay square", "how far will the flange turn", "will the
  beam bow", "what residual stress is at the weld": fillet and butt welds on a weldment of one metal,
  modelled as one solid (the plates and the weld as one part).
- Not for the weld pool, penetration, cracking, porosity or the heat-affected zone's microstructure,
  or the order of welding and clamping (see [Limits](#limits)): not in this version.

## The study

```json
{"process": "welding", "alloy": "s355",
 "welds": [{"faces": ["#o1.f3", "#o1.f8"], "process": "gmaw", "volts": 26, "amps": 220,
            "travel_speed_mm_s": 5, "passes": 1, "label": "web to flange, left"}],
 "tolerance_mm": 0.5, "fatigue_critical": true}
```

- `process` (required): `welding`.
- `alloy` (required): the base metal, a name from [The base metals](#the-base-metals) or a plain
  name (`mild-steel`, `s235jr`, `stainless`, `6061`, ...).
- `welds` (required): each weld, in any order (they are applied together):
  - `faces`: where it runs. Two faces: the plate it lies on, then the plate that meets it (a fillet
    on a T: the flange's top beside the web, then the web's side); the weld runs along the edge they
    share. Or one face with `line_mm`, `[[x, y, z], [x, y, z]]`, its two ends (a butt weld across a
    plate's face, two coplanar faces of two plates). The faces must be flat; the weld straight.
  - `process` (required): the weld's own, `gmaw` (`mig`, `mag`), `gtaw` (`tig`), `smaw` (`stick`) or `laser`
    ([The processes](#the-processes)).
  - Its heat, one way: `heat_input_kJ_mm`, the net heat input per pass (EN 1011-1's Q, the thermal
    efficiency included); or `volts`, `amps` and `travel_speed_mm_s` (`power_W` and
    `travel_speed_mm_s` for a laser), with the process's `efficiency` unless given (0 to 1).
  - `passes`: how many passes (default 1). `thickness_mm`: the plates' thicknesses, one per face or
    one for both; measured from the part when left out. `label`: a name for the findings.
- `tolerance_mm`: what the distortion is judged against. Left out, ISO 2768-2 class K's general
  flatness for the part's longest side, as in [printing.md](printing.md#the-study).
- `fatigue_critical`: `true` judges the residual stress along the welds (it is near yield) as a
  fatigue risk; `false` (default) reports it.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`, `order` 2 or 1), `output`, `fit`
  (`iterative`, `defeature`, `linear_elements`) and `view` (no `checks`: its findings are its verdict).
- Not taken: `material` (the base metal is the `alloy`), `parts` and `connections` (model the
  weldment as one solid).

## The processes

| `process` | what it is | thermal efficiency k | its heat |
| --- | --- | --- | --- |
| `gmaw` | gas metal arc (MIG/MAG) | 0.8 | `volts`, `amps`, `travel_speed_mm_s` |
| `gtaw` | gas tungsten arc (TIG) | 0.6 | `volts`, `amps`, `travel_speed_mm_s` |
| `smaw` | manual metal arc (stick) | 0.8 | `volts`, `amps`, `travel_speed_mm_s` |
| `laser` | laser beam | 0.7 | `power_W`, `travel_speed_mm_s` |

Q = k U I / v (J/mm, with U in V, I in A and v in mm/s), EN 1011-1's heat input with its thermal
efficiencies [5]; a laser's k P / v, its absorbed share an assumption (give `efficiency`, or the
heat input, where it is known). An arc weld puts in about 0.2 to 4 kJ/mm a pass.

## The base metals

| `alloy` | name | E, GPa | Poisson | yield, MPa | expansion, 10⁻⁶/K | conductivity, W/(m K) | specific heat, J/(kg K) | density, kg/m³ | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `s235` | Structural steel S235 | 210 | 0.3 | 235 | 12 | 53.3 | 440 | 7850 | [6] |
| `a36` | Structural steel A36 | 200 | 0.26 | 250 | 11.7 | 51.9 | 486 | 7850 | [7] |
| `s355` | Structural steel S355 | 210 | 0.3 | 355 | 12 | 53.3 | 440 | 7850 | [6] |
| `304` | Stainless steel 304 | 193 | 0.29 | 215 | 17.3 | 16.2 | 500 | 8000 | [8] |
| `6061-t6` | Aluminium 6061-T6 | 68.9 | 0.33 | 276 | 23.6 | 167 | 896 | 2700 | [8] |

- The yields are the plate's minimum (S235 and S355 up to 16 mm thick).
- The relations below were measured on steel; another metal's weld is scaled by its α / (c ρ) against
  steel's 3.48 × 10⁻³ mm³/J (304: 1.25 times, 6061-T6: 2.8 times): its heat swells it more.
- A 6061-T6 weld softens its heat-affected zone to about half its yield, which this version does not
  model (the parent's yield is used throughout).

## How a weld shrinks the part

Each weld gets its zone's inherent strain, the strain the welding locks into the metal beside it,
sized by its heat input Q and the plates' thickness h through the classical relations, and the part
is solved once, free, for the distortion and stress they leave (the inherent strain method of weld
distortion [11]):

- **Along the weld.** The yielded zone beside the weld pulls with the tendon force F_T = 0.2 kN per
  J/mm of Q in steel [1], [3], in proportion to E α Q / (c ρ) [4]. Its area is F_T / σ_y, the material
  nearest the weld line, whose inherent strain along the weld is -σ_y / E.
- **Across it.** In each plate, a strip a plate thickness wide beside the weld carries a strain
  across the weld that varies through the plate's thickness; its integrals are the transverse
  shrinkage S and the angular distortion θ of Satoh and Terasaki's relations [1], [2] for the plate's
  share of the heat:
  - θ = 1.44 × 10⁻³ Q/h² rad for Q/h² ≤ 6.27 J/mm³, 0.1061 (Q/h²) / ((Q/h² - 6.16)² + 73.6) beyond:
    a plate barely heated through turns most; one heated through shrinks evenly and turns less (θ
    peaks near Q/h² = 10.6 at 0.69° a plate);
  - a fillet's S = 1.16 × 10⁻³ Q/h up to Q/h² = 6.27, [1.44 × 10⁻⁴ ((Q/h²)² - Q/h²) + 0.0025] h up
    to 20, then 2.85 × 10⁻³ Q/h; a butt weld's S = 2.85 × 10⁻³ Q/h (mm);
  - a fillet's heat divides between the plate it lies on, which conducts it both ways, and the plate
    that meets it: 2 h_F / (2 h_F + h_W) to the first [1];
  - each pass adds its own; the relations are for a 200 mm weld (a longer one turns up to 1.4 times
    more [1]: not taken).
- **The joint.** The angular distortion reported is the joint closing on the weld's own side: each
  plate's rotation about the weld, fitted to its face's displacement beyond the strip, summed over
  the plates the weld joins. A T joint welded on one side closes by the flange turning up and the web
  leaning in; welded on both sides, the web stays square and each side closes by its flange alone.

## What comes out

- `part.welding.glb`, coloured by the residual stress (von Mises, MPa) and deformed by the distortion
  (mm, its rigid motion taken out). The other fields: `longitudinal_stress` (MPa, along the nearest
  weld, signed) and `weld_zone` (1 in a weld's zones). No frames: the welds act together.
- Summary: `alloy`, `yield_MPa`, `welds` (each `label`, `process`, `joint` (`fillet` or `butt`),
  `heat_input_kJ_mm` and how it was found, `passes`, `length_mm`, `from_mm`, `to_mm`,
  `tendon_force_kN`, `zone_area_mm2`, `longitudinal_strain`, `plates` (each `face`, `thickness_mm`,
  `heat_share`, `Q_over_h2_J_mm3`, `transverse_shrinkage_mm`, `angle_empirical_deg`, `angle_deg`),
  `angle_deg`, `angle_empirical_deg`, `bow_mm`, `bow_beam_mm`, `longitudinal_stress_MPa`),
  `max_distortion_mm` and where, `max_angle_deg`, `max_von_mises_MPa` and where,
  `max_longitudinal_stress_MPa`, `tolerance_mm` and `tolerance_source`, `fatigue_critical`.
- CLI (a 100 x 200 x 10 mm S235 flange with a 10 mm web 80 mm tall, one 1 kJ/mm fillet): "Structural
  steel S235: distortion up to 0.493 mm at [-50, 10, 10] mm (tolerance 0.4 mm)", "weld 1: fillet, 1
  kJ/mm × 1, turns 0.848° (Satoh and Terasaki 0.824°), bows 0.0624 mm", "residual stress along the
  welds up to 117 MPa (yield 235 MPa)".

## Findings

Every check says what it measured against its limit (`measured`), passes included; every error and
warning carries the `fix` that makes it pass ([checks.md](checks.md#welding) lists every type and the
fix actions it can carry).

| Finding | Severity | What it measures | Fix |
| --- | --- | --- | --- |
| `distortion` | error past `tolerance_mm`, else info | The largest distance any point moved from the CAD, its rigid motion taken out; the weld that turns its joint most. | `reduce_heat_input` (`params.weld`, `params.heat_input_kJ_mm`), with `alternatives`: `balance_welds` (weld the other side too), `preset` (`params.preset_deg`), `thicken` (`params.thickness_mm`, a plate on the rising side of θ only). |
| `angular_distortion` | info | Each weld's joint closing, in degrees, its joint, heat and passes. | |
| `hand_check` | info | The weld whose angle is furthest from Satoh and Terasaki's, against it, within 2 times. | |
| `hand_check_far` | warning | The two are more than 2 times apart. | `check_inputs`: the faces (the plate the weld lies on first), the heat input and the thicknesses. |
| `bowing` | info within 2× of beam theory, else warning | The bow along the weld that bows the part most, against beam theory's. | `check_inputs`. |
| `residual_stress` | warning past 80 % of yield when `fatigue_critical`, else info | The tension along the welds, the 90th percentile of the weld zones (a note when not fatigue-critical). | `stress_relieve` (a post-weld heat treatment, or peening the toes). |

## Hand checks

- **Angular distortion, Satoh and Terasaki.** Each plate's θ for its share of the heat, summed: a
  one-sided 1 kJ/mm fillet on a T of 10 mm plates gives the flange 2/3 of it, Q/h² = 6.67, θ = 0.55°,
  and the web Q/h² = 3.33, θ = 0.28°, together 0.82°; the simulation reads 0.85° (1.03×). Welded on
  both sides, each joint reads 0.58° and 0.56°: the web stays square.
- **Bowing, beam theory.** The welds' tendon forces F_T, each e off the section's centroid, bend the
  part M = Σ F_T e and bow it M L² / (8 E I) over the weld's length L. The T above: 200 kN, 13.9 mm
  off its centroid, 0.052 mm by beam theory against 0.062 mm simulated.
- **Transverse shrinkage of a butt weld, by hand.** S = 2.85 × 10⁻³ Q/h mm in steel [1]; or from the
  weld's size, about 0.2 A_w / t + 0.05 times the root opening [estimates.md](estimates.md#welding).
- **The method.** The inherent strain solve is the one `printing` uses; its own check, a cantilever
  plate's curl against beam theory, is in [printing.md](printing.md#hand-checks).

## Check, fix, check again

As `SKILL.md` says for casting: run it, read `verdict` and each finding's `fix` from the sidecar,
make the fix, run it again until it is `ready`. The fixes a welding study gives:

- `reduce_heat_input`: the weld's `heat_input_kJ_mm` (or its volts, amps and speed): a smaller weld or
  faster travel, only as far as the joint's strength allows (ask the user before you shrink a weld).
- `balance_welds`: add the same weld on the joint's other side, or alternate sides pass by pass.
- `preset`: the plates set against the angle before welding; the run does not model a preset, so tell
  the user the angle.
- `thicken`: the plate's thickness in the model (`$cad`), then rebuild the STEP.
- `stress_relieve`: a post-weld heat treatment or peening: tell the user; the run does not model it.
- `check_inputs`: the study, not the part.

## Limits

- Every weld is applied at once, not in sequence, and the part is free: in this linear model neither
  the welds' order nor clamping while they cool changes the result (real clamps hold some distortion
  back).
- Each weld is the classical relations' inherent strain, sized by its heat input and the plates'
  thickness from measurements on steel and scaled to the metal by α / (c ρ): an estimate of the zone,
  not a thermal history.
- Linear elastic, the base metal's yield throughout: near a weld the stress is about yield where the
  section is wide, as it is in a weld; an aluminium's softened heat-affected zone is not modelled.
- Straight welds on flat faces; a multi-pass weld's angle and transverse shrinkage add pass by pass,
  its tendon force is one pass's.

## When the model is big

One linear solve, on quadratic tetrahedra by default; give the strips across each weld a few elements
through the plate's thickness (`mesh.size_mm` about half the thinnest plate). Ladder: `iterative`
(multigrid-preconditioned CG), `defeature`, `linear_elements` (the angle reads low).

## Sources

1. Nakatani, "Prediction method of welding deformation for large steel structures", Proceedings of
   ICCES'08 (2008) 1678-1683: the heat input Q = η I E / v; the fillet's flange share
   Q_total 2 h_F / (2 h_F + h_W); the fillet's transverse shrinkage and angular distortion in Q/h² for
   a 200 mm weld; the tendon force F_T = 0.2 Q_net kN; a butt weld's S = 2.85 × 10⁻³ Q_net / h.
2. Satoh and Terasaki, "Effect of welding conditions on welding deformations in welded structural
   materials", Journal of the Japan Welding Society 45 (1976) 302-308: the relations [1] gives.
3. White, Leggatt and Dwight, "Weld shrinkage prediction", Welding and Metal Fabrication (1980): the
   tendon force.
4. Okerblom, The Calculations of Deformations of Welded Metal Structures (1958; English translation,
   HMSO): longitudinal shrinkage in proportion to α Q / (c ρ).
5. EN 1011-1 (and ISO/TR 17671-1): heat input Q = k U I / v, thermal efficiency k = 0.8 for MIG/MAG
   and manual metal arc, 0.6 for TIG, 1.0 for submerged arc (as TWI and SSAB give them).
6. EN 1993-1-1 (E 210 GPa, ν 0.3, α 12 × 10⁻⁶/K, ρ 7850 kg/m³), EN 1993-1-2 (λ = 54 - 0.0333 θ:
   53.3 W/(m K) at 20 °C; c = 425 + 0.773 θ - 1.69 × 10⁻³ θ² + 2.22 × 10⁻⁶ θ³: 440 J/(kg K)), EN
   10025-2 (yield 235 and 355 MPa up to 16 mm).
7. ASTM A36 (yield 250 MPa, 36 ksi), AISC (E 200 GPa, α 11.7 × 10⁻⁶/K), ASM for a mild carbon steel
   (ν 0.26, 51.9 W/(m K), 486 J/(kg K)).
8. ASM Handbook, Vol. 1 and 2: annealed 304 and 6061-T6, as in `$fea`'s material table.
9. ISO 2768-2: general flatness tolerances, class K.
10. Blodgett, Design of Welded Structures (1966): balancing welds about the neutral axis, presetting.
11. Ueda, Murakawa and Ma, Welding Deformation and Residual Stress Prevention (Elsevier, 2012): the
    inherent strain and inherent deformation of a weld.

Not checked against the source this time: [2], [3], [4], [10] and [11] are read through [1] or
from memory; the EN 1993 and A36 values in [6] and [7] and ISO 2768-2's figures are from memory of
the standards; the laser's 0.7 is an assumption.
