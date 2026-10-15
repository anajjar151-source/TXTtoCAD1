# Machining (`machining`)

A part on a CNC mill or lathe, under one cut: how far the cut pushes it (against the face's
tolerance), the stress it puts in it (against yield), and whether the cut chatters, with the depth it
stays stable to at the spindle speed and the nearest stable speeds. Lite: read [Limits](#limits)
before you report.

## When to use it

- "Will this thin wall deflect under the cutter", "will the wall be cut out of tolerance", "will this
  slender pin bend away from the tool", "will it chatter", "which spindle speeds are chatter-free",
  "how deep can I cut": one milling or turning cut on one part, held by a vise, clamps or a chuck.
- Not for tool wear, the tool's or the spindle's own flexibility, a toolpath (the cutter is put where
  the part gives most, not moved along a path), or the chip's formation: not in this version.

## Workflow

1. **List the faces** (`cadgen fea faces part.step`, as in `$fea`): the faces the cutter is on (the
   wall being finished, the diameter being turned) and the faces the vise jaws, clamps or chuck hold.
   Prefer faces the user selected in the Viewer (`part.step#o1.f12`).
2. **Write the study** as `part.machining.json` beside the part ([The study](#the-study)), from the
   user's cutting data: the cutter, the spindle speed, the feed, the depths, and the drawing's
   tolerance on the cut faces.
3. **Check**: `cadgen manufacturing check part.step --study part.machining.json --fail-on error`
   (with the `fea` extra, as the skill's Setup says). It writes `part.machining.glb` and
   `part.machining.result.json` beside the part, and exits 3 while an error stands.
4. **Read the findings**: each is a check, with what it measured against its limit and the fix that
   makes it pass ([Findings](#findings)); the lines end with them as a checklist (FAIL, WARN, PASS).
   The sidecar's and the result's `verdict` reads them as a CI check does: `ready` with no error
   ("Ready to cut · 0.0185 mm under the cut · stable to 0.54 mm at 18000 rpm"), else `fix`.
5. **Report**, in this order: the verdict; the deflection at the cut against the tolerance, and
   where the cut was put; the stress against yield; the chatter limit at the spindle speed against
   the depth, the limit at any speed, and the nearest stable speeds; the hand check; the limits. Then
   the fixes, each with its numbers. To fix the model, apply a fix's `params` and check again until
   it passes.

## The study

```json
{"process": "machining", "material": "6061-t6", "operation": "milling",
 "tool": {"diameter_mm": 10, "flutes": 3}, "spindle_rpm": 8000, "feed_per_tooth_mm": 0.05,
 "depth_mm": 5, "width_mm": 1, "milling": "down",
 "cut_faces": ["#o1.f10"], "fixtures": [{"faces": ["#o1.f5"]}],
 "tolerance_mm": 0.02, "damping_ratio": 0.02}
```

- `process` (required): `machining`.
- `material` (required): a name from [The materials](#the-materials) or one of its plain names
  (`6061`, `7075`, `1018`, `mild-steel`, `c45`, `4140`, `42crmo4`, `304`, `316`, `titanium`,
  `ti64`, `brass`, `c360`, `delrin`, `acetal`, `pom`), or an object that extends a table entry
  (`{"name": "6061", "kc11_MPa": 750}`) or gives every number: `E_MPa`, `nu`, `yield_MPa`,
  `density_t_per_mm3`, `kc11_MPa` and `mc`, and optionally `kr`.
- `operation` (required): `milling` or `turning`.
- `tool` (milling, required): `diameter_mm` and `flutes`. Turning takes none: the part turns and the
  tool cuts with one edge.
- `spindle_rpm` (required): the spindle speed.
- `feed_per_tooth_mm` (required): the feed per tooth, f_z; for turning, the feed per revolution, f.
- `depth_mm` (required): milling, the axial depth of cut a_p; turning, the depth of cut, the chip's
  width.
- `width_mm` (milling, required): the radial depth of cut a_e, up to the cutter's diameter (a slot).
- `milling` (milling): `down` (climb, the default) or `up` (conventional).
- `cut_faces` (required): the faces the cutter is on. Not a fixture's.
- `fixtures` (required): the faces held, as in a `$fea` static study (`fixed`, or `roller`).
- `tolerance_mm`: the deflection the cut may leave. Left out, ±0.05 mm, ISO 2768-1's fine class for
  features up to 6 mm [11], and the result says so.
- `damping_ratio`: every mode's, 0.02 (2 %) when left out: typical for a clamped part, not measured
  (a tap test measures it).
- `max_spindle_rpm`: the fastest the machine's spindle turns. Left out, 24 000 rpm, the high-speed
  spindle of a common small VMC [13]; give the machine's own, always for a lathe, whose spindle is
  far slower. A chatter fix never asks for a speed past it, and a `spindle_rpm` past it is refused.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`, `refine`), `output`, `margin` (the
  safety factor the stress keeps, 2 by default), `fit` and `view` (controls, presets, sections and
  show; there are no `checks`: its findings are its verdict).
- Not taken: `parts` and `connections` (one part: name it with `--occurrence` in a document of
  several).

## The cut

- **Kienzle's force** [2]. The specific cutting force at a chip h mm thick is
  k_c = k_c1.1 h^(-m_c), and the cutting (tangential) force on a chip b mm wide is
  F_c = k_c b h = k_c1.1 b h^(1 - m_c). The force pushing the tool off the face, radial in milling
  and passive in turning, is K_r F_c, with K_r = 0.3 [4].
- **Milling** (straight flutes) [3]: a tooth's angle φ is measured from the cut face's normal; up
  milling enters at 0 (on the finished face, with no chip) and leaves at arccos(1 - 2 a_e / D); down
  milling enters at π minus that and leaves at π; a slot runs 0 to π. A tooth's chip is f_z sin φ.
  Summed over the teeth in the cut through one tooth period, the force along the face's inward
  normal is taken at its extreme (signed: up milling can pull the face toward the cutter). The
  feed's component, along the face, is left out.
- **Turning** is the orthogonal cut [3]: the chip is depth_mm wide and the feed per revolution
  thick; the passive force K_r F_c pushes along the face's normal. The tangential force F_c, which
  bends a round part as much again, is left out of the deflection and counted in the stress
  (scaled by √(1 + K_r⁻²), exact for a round part).
- **Where the cutter is put.** The lowest 8 modes of the clamped part say where on the cut faces it
  is most flexible along their normal, Σ (φᵣ·n)² / ωᵣ²: the cutter is put there, its force on the cut
  faces within half the depth of cut (at least one element) of that point. The deflection is the
  load-weighted displacement of that patch along the normal.

## The materials

Kienzle's k_c1.1 and m_c are a tool maker's values by machinability group (DIN/ISO 513 and VDI
3323), for a 0° rake [1]; a positive-rake tool cuts with less. E, ν, yield and density are the
solver's. Values marked * are estimates (see [Numbers not verified](#numbers-not-verified)).

| material | name | k_c1.1, N/mm² | m_c | group | E, MPa | yield, MPa | density, kg/m³ | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `aluminum-6061-t6` | Aluminum 6061-T6 | 800 | 0.25 | wrought aluminium, hardenable (22) | 68 900 | 276 | 2 700 | [1], [10] |
| `aluminum-7075-t6` | Aluminum 7075-T6 | 800 | 0.25 | wrought aluminium, hardenable (22) | 71 700 | 503 | 2 810 | [1], [10] |
| `steel-1018` | Steel 1018 | 1350 | 0.21 | non-alloy steel under 0.25 % C (1) | 205 000 | 370 | 7 870 | [1], [8] |
| `steel-1045` | Steel 1045 | 1500 | 0.22 | non-alloy steel, 0.25 % C and over (2) | 200 000 | 310 | 7 870 | [1], [8] |
| `steel-4140` | Steel 4140 (annealed) | 1775 | 0.24 | low-alloy steel, annealed (6) | 205 000 | 415 | 7 850 | [1], [8] |
| `stainless-304` | Stainless steel 304 | 2150 | 0.20 | austenitic stainless (14) | 193 000 | 215 | 8 000 | [1], [10] |
| `stainless-316` | Stainless steel 316 | 2150 | 0.20 | austenitic stainless (14) | 193 000 | 200 | 8 000 | [1], [8] |
| `titanium-6al-4v` | Titanium Ti-6Al-4V | 2110 | 0.22 | titanium alpha-beta alloys (37) | 113 800 | 880 | 4 430 | [1], [10] |
| `brass-c360` | Brass (C36000) | 700 | 0.27 | copper alloys, free cutting, over 1 % Pb (26) | 97 000 | 310 | 8 500 | [1], [10] |
| `delrin` | Delrin (acetal, POM-H) | 200* | 0.25* | a plastic: no published values | 3 103 | 75.8 | 1 410 | [9] |

- The groups' numbers are VDI 3323's, read by each grade's condition and hardness: 1018 cold drawn
  (126 HB) is group 1 (under 0.25 % C, annealed, 125 HB); 1045 hot rolled (163 HB) group 2; 4140
  annealed (197 HB) group 6; 304 and 316 group 14; 6061-T6 and 7075-T6 the hardenable wrought
  aluminium of group 22 (7075-T6, about 150 HB, is harder than the group's 100); C36000 group 26;
  Ti-6Al-4V group 37.
- Delrin's k_c1.1 is 2.6 times its tensile strength, the middle of the metals' ratio of k_c1.1 to
  tensile strength in this table (1.8 for brass to 4.3 for 304); its m_c is the table's usual 0.25.
  Both are estimates, and every Delrin result says so.

## Chatter

- **The transfer function at the cut**, G(ω) along the face's normal, is the modes'
  Σ qᵣ² / (ωᵣ² - ω² + 2iζωᵣω), qᵣ = φᵣᵀ f̂ the mode's share of the cut's unit load f̂, plus the
  static solve's residual compliance (what the modes above leave, in phase). Each mode's stiffness
  at the cut along the normal is ωᵣ² / qᵣ² (N/mm); modes at one frequency (a round bar's pair) are
  taken together.
- **The force along the normal per mm² of chip**, K: turning, K_r k_c at the feed (Altintas's
  orthogonal cut [3]); milling, -N K_t α_yy / (4π), with K_t the specific cutting force at the mean
  chip thickness h_m = f_z (2 a_e / D) / arccos(1 - 2 a_e / D) and α_yy Altintas and Budak's
  averaged directional factor along the normal, ½ [-cos 2φ - 2 K_r φ - K_r sin 2φ] from φ_st to φ_ex
  (-K_r π for a slot) [4], [5].
- **The lobes** [4], [6]: the limiting depth at a chatter frequency ω is a_lim = -1 / (2 K Re G(ω))
  where it is positive; the phase between the waves is ε = π + 2 atan(Im G / Re G); lobe k puts it at
  n = 60 ω / (z (ε + 2πk)) rpm (z the flutes, 1 for turning). The stability boundary is the least
  a_lim over every lobe at each speed, drawn from a third to three times the study's speed, up to 25
  times the deeper of the cut and the lowest limit.
- **Its lowest**, the depth the cut is stable to at any speed, is -1 / (2 K min Re G); for one mode
  of stiffness k and damping ζ, min Re G = -1 / (4 k ζ (1 + ζ)), so it is 2 k ζ (1 + ζ) / K
  (Tlusty's) [6].
- **The pockets**, the speeds where the boundary peaks between lobes, are where the tooth passes at
  about the chatter frequency divided by a whole number: n ≈ 60 f_c / (z (k + 1)).

## What comes out

- `part.machining.glb`, opening on the displacement under the cut (deformed by it), and coloured by the
  von Mises stress: fields `displacement` (mm), `von_mises` (MPa) and `mode_shape` (the dominant
  mode at the cut, rung along the normal, its largest motion 1 mm).
- Curve `stability_lobes`: the depth (mm) the cut stays stable to against the spindle speed (rpm),
  the study's speed among them (the sidecar's `curves`).
- Summary: `operation`, `material`, `cut`,
  `kienzle` (`kc11_MPa`, `mc`, `kr`, `chip_mm`, `kc_MPa`, `estimated`), `force_tangential_N`,
  `force_normal_N`, `force_resultant_N`, `cut_at_mm`, `cut_normal`, `patch_radius_mm`,
  `deflection_at_cut_mm`, `tolerance_mm` and `tolerance_given`, `max_displacement_mm`,
  `static_compliance_mm_per_N`, `section_at_cut_mm`, `reach_from_clamp_mm`, `max_von_mises_MPa`
  and where, `yield_MPa`, `safety_factor`, `modes` (each `frequency_Hz` and
  `modal_stiffness_N_per_mm` at the cut), `dominant_mode` and its
  `dominant_modal_stiffness_N_per_mm`, `residual_compliance_mm_per_N`, and `chatter`
  (`limit_mm` at `spindle_rpm`, `max_spindle_rpm`, `stable`, `absolute_limit_mm` and its frequency,
  `nearest_stable_rpm` below and above and `pockets`, up to `max_spindle_rpm`, `tooth_frequency_Hz`, `damping_ratio`,
  `cutting_coefficient_MPa` (K), `drawn_to_mm`).
- CLI: "under the cut: 0.691 mm at [40, 16, 30] mm (tolerance ±0.02 mm); peak stress 418 MPa (yield
  276 MPa)", "cutting force 242 N into the face (Kienzle k_c 2266 N/mm² at a 0.0155 mm chip)", "rings
  at the cut at 6116 Hz (mode 2, 860 N/mm along the normal)", "stable to 0.0966 mm at 8000 rpm
  (cutting 5 mm), to 0.092 mm at any speed", then the checklist and the verdict.

## Findings

Every check says it passed, as an `info` with what it measured, when it does: the checklist's PASS
lines. A finding that judges a number carries `measured` (`quantity`, `value`, `limit`, `units`,
`pass_when`); every error and warning carries `fix` (`action`, `summary`, `where`: face refs and
points in mm, `params`: the values to set), most with `alternatives` in the same shape;
[checks.md](checks.md#machining) lists every type and the fix actions it can carry.

| Finding | Severity | What it means | Fix (`action`: `params`) |
| --- | --- | --- | --- |
| `deflection_within_tolerance` | info | The face moves under half the tolerance where the cutter pushes. | |
| `deflection_close_to_tolerance` | warning | It moves over half the tolerance: little is left for every other error. | `reduce_depth`: `depth_mm` that keeps it under half (the force grows with the depth) |
| `deflection_over_tolerance` | error | It moves more than the tolerance: the face is cut out of tolerance. | `reduce_depth`: `depth_mm`, as above; or support it |
| `thin_wall_too_flexible` | error or warning | With the deflection over (or near) the tolerance, the wall at the cut reaches 3 times its thickness or more from the clamp: it bends like a plate. | `thicken`: `thickness_mm` (a plate's stiffness grows as the cube of its thickness) and `stiffness_factor`; alternatives `rough_before_finishing` (rough both sides before it is thinned) and `support` |
| `slender_part_too_flexible` | error or warning | The same for a turned part reaching 3 diameters or more from the chuck. | `support` (a tailstock centre or a steady rest): `stiffness_factor`; alternative `thicken`: `diameter_mm` (a round bar's stiffness grows as the fourth power of its diameter) |
| `clamp_stress_ok` | info | The stress the cut puts in the part keeps the study's margin under yield. | |
| `clamp_stress_close` | warning | Its safety factor is under the margin. | `reduce_depth`: `depth_mm` that keeps the margin |
| `yields_under_cut` | error | The cut bends the part past yield: it stays bent. A sharp inside corner's peak grows as the mesh is refined: read it a little away. | `reduce_depth`, as above; or clamp it closer to the cut |
| `chatter_stable` | info | The depth is under 80 % of the limit at the spindle speed (or no lobe comes near it). | |
| `chatter_close` | warning | It is within 20 % of the limit: the damping and the cutting force are about that uncertain. | `reduce_depth`: `depth_mm`, 80 % of the limit at its own speed; alternative `change_speed`: `spindle_rpm`, the nearest pocket that clears it, only where one lies within `max_spindle_rpm` |
| `chatter` | error | The depth is past the limit: the cut chatters, leaving a wavy face and hammering the tool. | as `chatter_close` |
| `hand_check` | info | The dominant mode's frequency, stiffness and damping, Tlusty's one-mode limit, and the lobes' lowest against it. | |
| `cutting_force_estimated` | info | The material has no published Kienzle values (Delrin): its cutting force is an estimate. | |
| `default_tolerance` | info | No `tolerance_mm`: judged against ±0.05 mm. | |

## Hand checks

- **The force.** Turning: F_c = k_c1.1 b f^(1 - m_c); 1018 at b = 2 mm, f = 0.2 mm/rev:
  1350 × 2 × 0.2^0.79 = 757 N, and 0.3 of it pushes the part off the tool. Milling: one tooth's force
  at its thickest chip is k_c1.1 a_p h_max^(1 - m_c), h_max = f_z where the tooth passes 90°, else
  f_z sin φ_e (the estimate's k_c × a_p × f_z [12], with k_c at the chip).
- **The deflection.** A bar turned at its free end, L from the chuck, deflects as a cantilever,
  P L³ / (3 E I), P the passive force; a 12 mm 1018 bar 60 mm out under 66 N: 0.023 mm, and the solve
  reads it within 10 %. A wall cut at its free edge bends as a plate, stiffer as the cube of its
  thickness.
- **The frequency.** That bar's first mode is Euler-Bernoulli's,
  f = (1.875² / 2π) √(E I / (ρ A L⁴)), within 5 %; a tap test on the clamped part measures it.
- **The chatter limit.** Tlusty's one mode [6]: 2 k ζ (1 + ζ) / K with the dominant mode's
  stiffness at the cut; the lobes' lowest reads it when one mode dominates (the bar: within 10 %),
  higher where the residual compliance (in phase) stiffens it.
- **The pockets.** The stable speeds' centres are n = 60 f_n / (z (k + 1)) [12].

## Limits

- The cutting force is Kienzle's for a sharp tool, straight flutes (no helix), no run-out or wear,
  from the material's machinability group: a real tool and grade can differ by 20 % or more.
- Only the part flexes: the tool, the holder and the spindle are rigid, so a stiff part cut by a
  long, slender tool chatters on the tool, which this does not see.
- The cutter is put where the cut faces are most flexible along their normal, and only the force
  along that normal acts: the feed force along a wall is left out (turning: the tangential force,
  which bends a round part as much again, is counted in the stress).
- Chatter is the zero-order (averaged) solution in one direction, the cut face's normal, linear in
  the chip: a light radial cut at high speed is interrupted enough to have extra lobes it misses, and
  at low speed the tool's flank rubbing the waves (process damping) makes the real cut more stable
  than this says.
- The damping is the study's (2 % unless it says), not measured: a tap test on the clamped part gives
  the real damping and frequency, and the real lobes.

## When the model is big

Quadratic elements; the lowest 8 modes and one static solve on the same mesh. Ladder: `iterative`
(LOBPCG with multigrid for the modes, multigrid CG for the static), `defeature` and
`linear_elements`. A part meshed finely enough for a thin wall takes a while to find its modes: a
thicker part can take a coarser `mesh.size_mm`.

## Sources

1. ISCAR, Materials and Grades (catalogue page 1112), material groups according to DIN/ISO 513
   and VDI 3323: k_c1 and m_c by group (1: 1350, 0.21; 2: 1500, 0.22; 6: 1775, 0.24; 14: 2150, 0.20;
   22: 800, 0.25; 26: 700, 0.27; 37: 2110, 0.22), with each group's tensile strength and hardness.
2. Kienzle, "Die Bestimmung von Kräften und Leistungen an spanenden Werkzeugen und
   Werkzeugmaschinen", VDI-Z 94 (1952) 299-305: F_c = k_c1.1 b h^(1 - m_c).
3. Altintas, Manufacturing Automation, 2nd ed. (Cambridge, 2012): the mechanics of milling (the
   chip f_z sin φ, the tangential and radial forces), and the stability of orthogonal cutting.
4. Altintas, Stepan, Merdol and Dombovari, "Chatter stability of milling in frequency and discrete
   time domain", CIRP Journal of Manufacturing Science and Technology 1 (2008) 35-44: the averaged
   directional factors (eq. 17), a_lim = -(2π Λ_R / (N K_t)) (1 + κ²) and the spindle speeds (eq.
   21); Fig. 4 cuts with K_t = 900 and K_r = 270 N/mm² (K_r / K_t = 0.3) at 4-5 % damping.
5. Altintas and Budak, "Analytical prediction of stability lobes in milling", CIRP Annals 44 (1995)
   357-362: the zero-order solution.
6. Tlusty and Polacek, "The stability of machine tools against self-excited vibrations in
   machining", International Research in Production Engineering (ASME, 1963) 465-474: the limit
   -1 / (2 K Re G) and its minimum.
7. Sandvik Coromant, "Specific cutting force" (knowledge pages): k_c1 is for a 0° rake, a positive
   rake lowers k_c, and the mean chip thickness of a milling cut.
8. AZoM (Aalco and AZoM data sheets): AISI 1018 (7.87 g/cm³, 205 GPa, ν 0.29, yield 370 MPa,
   126 HB); AISI 1045 hot rolled (7.87 g/cm³, 200 GPa, ν 0.29, yield 310 MPa, 163 HB); AISI 4140
   (7.85 g/cm³, 190-210 GPa, ν 0.27-0.30, yield 415 MPa, 197 HB); 316 bar to EN 10088-3 (8.00 g/cm³,
   193 GPa, proof stress 200 MPa minimum).
9. Ensinger, DELRIN acetal homopolymer stock shapes data sheet: 1.41 g/cm³, tensile modulus
   450 000 psi (3103 MPa), tensile strength at yield 11 000 psi (75.8 MPa), ASTM D 638.
10. `$fea`'s material table (its materials reference: ASM for 6061-T6, 7075-T6, 304 and Ti-6Al-4V;
    CDA for C36000 half hard).
11. ISO 2768-1:1989, general tolerances for linear dimensions: fine class ±0.05 mm from 0.5 to 6 mm.
12. The estimates' source [4] in [estimates.md](estimates.md#sources): Altintas's cutting forces and
    stability lobes, and Sandvik Coromant's handbook.
13. FANUC, ROBODRILL α-DiB Plus series (compact vertical machining centres): a 10 000 min⁻¹ spindle
    as standard and a 24 000 min⁻¹ high-speed spindle as an option.

## Numbers not verified

- K_r = 0.3 for every material: one aluminium example's ratio [4]; no table found gives it by
  material (it runs from about 0.2 to 0.5 with the tool's rake and edge).
- Delrin's k_c1.1 (200 N/mm²) and m_c (0.25): estimates, no published Kienzle values found; its ν
  0.35 is a typical acetal's, not the data sheet's.
- 316's ν (0.29, 304's; the data sheet gives none) and its yield (200 MPa, the bar standard's
  minimum, below a typical annealed bar's).
- 4140's E (205 GPa) and ν (0.29), taken from the data sheet's ranges.
- The 2 % damping: a typical value for a clamped part, not a measurement.
- Each grade's VDI 3323 group is read from its condition and hardness, not from a table naming the
  grade.
