# Sheet metal bending (`sheet_metal`)

Every bend of a bent sheet off the press brake, by hand formulas: how far it springs back and the overbend that
cancels it, whether it cracks on its outside, and the bend allowance for the flat pattern. An **estimate** (Tier 2), not
a forming simulation: say "estimate" every time you quote it, and read [Limits](#limits) before you report.

## When to use it

- "How much will it spring back", "what overbend do I set", "will it crack at this bend", "is R = t too tight in
  6061-T6", "what bend allowance and K-factor", "how far off is the last flange": one bent sheet part, read from its
  STEP.
- Not for a deep draw, a stamping or a roll-formed section (the draw ratio and the draw's force are hand estimates in
  [estimates.md](estimates.md#forging-extrusion-and-deep-drawing)), nor for the bend rules a shop checks (flange
  lengths, holes near bends, relief sizes): those are `$dfm`'s, which this complements. Where the shop has a bend
  table, its K-factor and radius are the production numbers; these are estimates beside them.

## The workflow

1. **Find the flat to hold** (optional). The part springs back about one flat held still: the largest by default.
   To hold another (the one the brake's back gauge locates, or the one bolted down), list the faces and name one of
   that flat's:

   ```bash
   cadgen fea faces part.step
   ```

2. **Write the study** as `part.sheet_metal.json` beside the part:

   ```json
   {"process": "sheet_metal", "material": "5052-h32", "tolerance_deg": 1}
   ```

3. **Check.**

   ```bash
   cadgen manufacturing check part.step --study part.sheet_metal.json --fail-on error
   ```

   This writes `part.sheet_metal.glb` (coloured by each bend's springback, drawn as it comes off the brake) and
   `part.sheet_metal.result.json` (every number per bend, the study, the findings and the verdict) beside the part, and exits
   3 while an error stands. A part with no
   bends, or not of one thickness, is refused in a sentence before it is meshed; so is a study with an unknown sheet,
   naming the field. Its lines end on the checklist, failures first, then the verdict:

   ```text
   FAIL  bend_may_crack               bend 1 outer strain: 33.3%, needs below 25.7%; at #o1.f2 [21.591, 12.5, 1.409] mm; fix: Open bend 1 to an inside radius of at least 2.2 mm (1.44t).
   FAIL  bend_may_crack               bend 2 outer strain: 33.3%, needs below 25.7%; at #o1.f4 [21.591, 12.5, 34.591] mm; fix: Open bend 2 to an inside radius of at least 2.2 mm (1.44t).
   PASS  springback_within_tolerance  bend 1 springback: 0.724°, needs below 3°; at #o1.f2 [21.591, 12.5, 1.409] mm
   ...
   PASS  reliefs                      bend ends with no relief: 0, needs below 1
   Verdict: 2 to fix · bend may crack · 2 failed, 0 warnings, 5 passed
   ```

   (A U of 1.5 mm 6061-T6 with both bends at R = t and a 3° tolerance.)

4. **Check, fix, check again**, as for a casting (the skill's own section): read `verdict.status` (`ready` or `fix`)
   and each error's and warning's `fix` from the sidecar, make it, rebuild and run again until it is `ready`:
   - `increase_radius`, `reduce_radius`: change that bend's inside radius in the model script (`$cad`) to
     `params.inner_radius_mm` (the flanges keep their lengths), and rebuild the STEP. Its alternatives are the user's
     to choose: `turn_blank` (bend across the grain: where the blank is nested, and the study's `grain_direction`),
     `softer_temper` and `form_in_die`.
   - `add_relief`: cut a relief at each of `where`'s points, `params.width_mm` wide and `params.depth_mm` deep into
     the flat; or `extend_bend`, the bend run out to the flat's edge.
   - `overbend`, `test_bend`: a press brake setting, not a change to the model. Report it to the user for the shop;
     the warning stays, as springback does.
   - `set_thickness`: the model's sheet or the study's `thickness_mm`, whichever the user says is right.

   Never change the material, the thickness or the tolerance to clear a finding: they are the user's.

5. **Report**, in this order: each bend's angle, inside radius and R/t; whether it cracks (its outer strain against
   the limit); its springback, the overbend, and the work-hardening value beside it; the far flat's angle off; any
   missing relief; the bend allowances. Then the limits. Show the result GLB with `$cad` (its Show the model step),
   beside the STEP: the Spring back routine plays the part coming off the brake.

## The study

```json
{"process": "sheet_metal", "material": "6061-t6", "thickness_mm": 1.5, "tolerance_deg": 0.5,
 "fixed_face": "#o1.f7", "grain_direction": [1, 0, 0]}
```

- `process` (required): `sheet_metal`.
- `material` (required): a sheet from [The sheets](#the-sheets) or one of its plain names (`5052`, `6061`, `304`,
  `crs`, `hsla`, `c110`, `brass`, ...), or an object with your own numbers: one that names a sheet changes only what
  it gives (`{"name": "5052-h32", "yield_MPa": 205}` for a mill certificate's yield); one that names none gives
  `E_MPa`, `nu`, `yield_MPa`, `uts_MPa`, `n` and `min_r_t`. `min_r_t` is one number or `[[thickness_mm, R/t], ...]`;
  `min_r_t_along_grain` is the same for a bend along the grain, and `elongation_percent` is optional.
- `thickness_mm`: the sheet's thickness. Left out, it is measured (the bends' inside and outside radii are one
  thickness apart); given and more than 5 % off the measured one, a finding says so.
- `tolerance_deg`: the springback a bend may have before it needs an overbend, and how far the far flat may be off;
  1° by default, the usual press brake angle tolerance.
- `fixed_face`: a face of the flat held still; the largest flat when left out.
- `grain_direction`: the sheet's rolling direction, `[x, y, z]`. A bend whose line runs within 45° of it bends along
  the grain (the hard way) and is judged on the sheet's along-the-grain minimum where it has one; every sheet in the
  table has one value for either direction, so give `min_r_t_along_grain` from the mill certificate when the grain
  matters.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`; linear elements, order 1: the mesh only carries the
  fields to the viewer), `output` (`deformation_scale`: 1, true scale, by default) and `view` (controls and presets; no
  `checks`: its findings are its verdict).
- Not taken: `parts` and `connections` (one part: name it with `--occurrence` in a document of several).

## The sheets

Room-temperature handbook values. A value marked * is not verified against its source (see
[What could not be verified](#what-could-not-be-verified)). Minimum R/t is for a 90° bend without cracking; where a row
gives several, they are by thickness and interpolated between.

| `material` | name | E, GPa | yield, MPa | UTS, MPa | n | elongation, % | minimum R/t | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `crs-1008` | Mild steel CRS 1008/1010 (ASTM A1008 CS) | 200 | 205* | 330* | 0.22* | 30 | 0 (bends flat on itself) | [6], [7] |
| `hsla-50` | HSLA grade 50 (ASTM A1011/A1008 HSLAS 50, class 1) | 200 | 345 | 450 | 0.15* | 22 | 0.5 | [8], [1] |
| `stainless-304` | Stainless 304, annealed | 193 | 215* | 505* | 0.45 | 70* | 0.5 | [9], [1] |
| `stainless-316` | Stainless 316, annealed | 193 | 290* | 580* | 0.45* | 50* | 0.5 | [9], [1] |
| `aluminum-5052-h32` | Aluminium 5052-H32 | 70.3 | 193 | 228 | 0.13* | 12 | 0 to 0.8 mm, 1 at 1.6, 1.5 at 3.2 to 9.5, 2 at 12.7 | [4], [1] |
| `aluminum-6061-t6` | Aluminium 6061-T6 | 68.9 | 276 | 310 | 0.05 | 12 | 1 to 0.8 mm, 1.5 at 1.6, 2.5 at 3.2, 3 at 4.8, 3.5 at 6.4, 4.5 at 9.5, 5 at 12.7 | [4], [1] |
| `aluminum-6061-o` | Aluminium 6061-O | 68.9 | 55 | 124 | 0.20* | 25 | 0 to 1.6 mm, 1 at 3.2 to 6.4, 1.5 at 9.5, 2 at 12.7 | [4], [1] |
| `aluminum-3003-h14` | Aluminium 3003-H14 | 68.9 | 145* | 150* | 0.05* | 8* | 0 to 1.6 mm, 1 at 3.2 and 4.8, 1.5 at 6.0 | [5], [4] |
| `copper-c110-h02` | Copper C110, H02 (half hard) | 117* | 255 | 290* | 0.10* | 14* | 0.5* | [10] |
| `brass-c260-h02` | Brass C260, H02 (half hard) | 110* | 358 | 427 | 0.20* | 23 | 1* | [11], [1] |

- The aluminium radii are the Aluminum Association's for 90° cold bends in a press brake with air-bend dies [4], at
  1/64, 1/32, 1/16, 1/8, 3/16, 1/4, 3/8 and 1/2 in; 3003-H14's are BlueScope's to ASTM E290 [5]. Between two
  thicknesses the limit is interpolated; past the thickest it is held.
- Low-carbon cold-rolled steel bends flat on itself in any direction without cracking [6]: its limit is 0, and a bend
  in it never reads as cracking. HSLA grade 50 and the austenitic stainless steels take Kalpakjian's 0.5t for the soft
  condition [1]; a thermomechanically rolled 355 MPa grade is guaranteed tighter (SSAB Domex 355MC: 0.2t to 3 mm,
  0.3t to 6 mm, either direction [8]).
- Brass C260 half hard is taken half way along Kalpakjian's low-leaded brass, 0 soft to 2t hard [1]: an estimate.
  Copper C110 H02's 0.5t is not from a table.
- n is the power-law exponent of σ = K ε^n. Kalpakjian gives 0.45 for annealed 304, 0.05 for 6061-T6 and 0.13 for
  5052-O [1]; the cold-worked tempers' (5052-H32, 3003-H14, the H02 coppers) are lower than their soft tempers' and
  are taken as marked. n moves only the work-hardening value and its check.
- Shops bend tighter than these tables where their tooling allows (Protocase bends 1.5 mm cold-rolled steel and 1.6 mm
  5052-H32 at about R/t 0.55 [14]): the tables are the material's limit without a test, not the tooling's.

## What comes out

- `part.sheet_metal.glb`, coloured by `springback` (°), each bend's own (the flats read 0), and drawn true to scale as it comes
  off the brake: each bend opened by its springback and every flat past it turned with it, out from the held flat. The
  other fields: `strain_ratio` (each bend's outer strain over the limit its minimum R/t allows: past 1 it may crack)
  and `displacement` (mm, the springback's). The Deformation control exaggerates it; Spring back plays it.
- Summary: `estimate`, `estimate_line`, `material`, `thickness_mm` and `thickness_measured_mm`, `tolerance_deg`,
  `held_flat`, `grain_direction`, and per bend (`bends`): its `faces`, `at_mm`, the flats it `joins`,
  `inner_radius_mm`, `r_over_t`, `angle_deg`, `length_mm`, `final_radius_mm`, `final_angle_deg`, `springback_deg`,
  `overbend_deg`, `springback_hardening_deg`, `gardiner_x` (R Y / (E t)), `kept` (K_s), `grain`, `min_r_over_t`,
  `outer_strain`, `strain_limit`, `strain_ratio`, `may_crack`, `k_factor`, `bend_allowance_mm`, `bend_deduction_mm`.
  Per flat (`flats`): its `faces`, `area_mm2` and `angle_error_deg` (how far it turns off its CAD angle). Then
  `max_springback_deg`, `max_strain_ratio`, `cracking_bends`, `far_flat`, `max_angle_error_deg` and
  `missing_reliefs`. The sidecar's `verdict`: `ready` (no error) or `fix`, its headline ("Ready to bend · 2 bends ·
  overbend up to 1.21°", "2 to fix · bend may crack"), and how many errors, warnings and passed checks.
- CLI: "bend 1: 90° at R 3 mm (R/t 2), 25 mm long, joins flats 1 and 2; springs back 1.19° (2.6° with work hardening),
  overbend 1.21°; outer strain 20% of 36% allowed; K 0.40, BA 5.66 mm, BD 3.34 mm".

## Findings

Each check says pass (an `info` with `measured`) or fail, per bend where it is a bend's; a failing one carries
`measured` and `fix` (with `alternatives` where there are any). A note measures nothing. [checks.md](checks.md#sheet_metal)
lists every type and the fix actions it can carry.

| Finding | Severity | What it means | Fix |
| --- | --- | --- | --- |
| `bend_may_crack` | error | The bend's outer fibre stretches past the strain at the sheet's minimum R/t: it may crack on its outside. `measured`: the outer strain (%) against that limit. | `increase_radius`: open it to `inner_radius_mm` (the minimum R/t times t, rounded up to 0.1 mm); else `turn_blank` (along the grain) or `softer_temper`. |
| `bend_formable` | info | It passes: the outer strain and the limit. | |
| `bend_takes_no_set` | error | The radius is so large the sheet never yields through its thickness (R Y / (E t) at 1/2 or more): it springs back flat. | `reduce_radius`, under `inner_radius_mm`; else `form_in_die`. |
| `springback_over_tolerance` | warning | It springs back more than `tolerance_deg`. `measured`: the springback. | `overbend`: `overbend_deg` on the press brake (`bend_to_deg`). |
| `springback_within_tolerance` | info | It passes, with its overbend all the same. | |
| `angle_error_over_tolerance` | warning | The flat farthest off its CAD angle (the bends between it and the held flat each turn it) is past the tolerance. | `overbend` each bend between (`params.bends`). |
| `angle_error_within_tolerance` | info | It passes. | |
| `springback_work_hardening` | warning | A bend passes on Gardiner's springback but not on the work-hardening value. `measured`: the most of those bends' work-hardening springback. | `test_bend`: measure a test piece before setting the overbend. |
| `springback_work_hardening_within_tolerance` | info | Every bend Gardiner passes passes with work hardening too. | |
| `relief_missing` | warning | A bend ends inside a flat with no relief cut: the sheet beside its end tears or bulges. Its ends are the items. | `add_relief`: at least t/2 wide and R + t + 0.5 mm deep [13] (`$dfm` checks the shop's own rule); else `extend_bend`. |
| `reliefs` | info | Every bend ends at an edge or a relief. | |
| `thickness_differs` | warning | The study's `thickness_mm` is more than 5 % off the measured thickness. | `set_thickness` (the model); else `set_study_thickness`. |
| `thickness_matches` | info | The study's `thickness_mm` is the part's. | |
| `bend_closes_loop` | info | A bend closes a loop of flats (a box closed on itself): its springback is held by the rest, not solved. | |
| `sheet_metal_estimate` | info | This is an estimate by hand formulas. | |

## Hand checks

The springback of a single 90° bend, worked by hand. 1.5 mm 5052-H32 (Y = 193 MPa, E = 70.3 GPa) bent to an inside
radius R = 3 mm, R/t = 2:

- Gardiner [2], in Kalpakjian and Schmid's form [1]: x = R Y / (E t) = 3 × 193 / (70 300 × 1.5) = 0.005491;
  R / R_f = 4x³ - 3x + 1 = 0.98353, so R_f = 3.050 mm.
- The bend's mid-thickness keeps its length, so it keeps K_s = (2R/t + 1) / (2R_f/t + 1) = 5 / 5.0670 = 0.98678 of its
  angle: 88.81°. **Springback 1.19°**; to land on 90° bend it to 90 / 0.98678 = 91.21°, an overbend of 1.21°. The
  check reads 1.19° on a STEP of this bend (its test holds it to 0.005°).
- With work hardening (Hosford and Caddell [3]): K = UTS (e / n)^n = 228 × (2.718 / 0.13)^0.13 = 338 MPa, in plane
  strain K' = (2/√3)^1.13 K = 398 MPa and E' = E / (1 - ν²) = 78 900 MPa; at the mid-thickness radius ρ = 3.75 mm the
  curvature unloads Δ(1/ρ) = 6 K' (t / 2ρ)^n / ((n + 2) E' t) = 0.00769 /mm, to ρ_f = 3.861 mm: K_s = 0.9711,
  springback 2.6°. Expect between the two; a test bend decides.
- Cracking: the outer fibre stretches e = 1 / (2R/t + 1) = 20 %; at 1.5 mm 5052-H32's minimum R/t is 0.89 (between the
  Aluminum Association's 0 at 1/32 in and 1 at 1/16 in), a limit of 1 / (2 × 0.89 + 1) = 36 %: it bends without
  cracking. 6061-T6's 1.44 at 1.5 mm allows 26 %; at R = t (33 %) it cracks, and 5052-H32 does not.
- The flat pattern: DIN 6935's k = 0.65 + 0.5 lg 2 = 0.80, a K-factor of 0.40 [12]; the bend allowance
  BA = (π/2)(3 + 0.40 × 1.5) = 5.66 mm, the outside setback (R + t) tan 45° = 4.5 mm, the bend deduction
  2 × 4.5 - 5.66 = 3.34 mm.

## Limits

- An estimate per bend by hand formulas, not a forming simulation: no contact with the tools, no thinning, no
  anisotropy beyond the grain's choice of limit, no residual stress. The flats stay flat and turn rigidly.
- The inside radius is the CAD's. An air bend takes a radius set by the die opening rather than the punch, and a larger
  radius springs back more: with the shop's die, its bend table and a test bend override these numbers.
- Gardiner's relation takes the sheet elastic-perfectly plastic at its yield strength; a sheet that work-hardens
  strongly (annealed stainless, n 0.45) springs back more, as the Hosford and Caddell value beside it says. Its yield is
  a typical one: a mill certificate's (give it in the material object) moves the springback in proportion.
- The minimum R/t is a table's, for either direction unless the sheet has an along-the-grain value.
- The K-factor is DIN 6935's estimate, held within 0.30 to 0.50 (the range bend tables give [13]): the shop's
  measured K-factor is the production number.

## What could not be verified

These numbers are standard handbook or supplier values that could not be checked against their source while this page
was written; replace any of them with a mill certificate's in the material object:

- Mild steel CRS: its yield (205 MPa, the middle of ASTM A1008 CS's typical 140-275 MPa [7]), its tensile strength
  (330 MPa) and n (0.22).
- HSLA grade 50: n (0.15).
- Stainless 304 and 316, annealed: their typical yield, tensile strength and elongation [9]; 316's n is taken as 304's.
- Aluminium: 5052-H32's n (5052-O's 0.13); 6061-O's n (0.20); 3003-H14's typical yield (145 MPa), tensile strength
  (150 MPa), elongation (8 %) and n (0.05). BlueScope's 3003-H14 minimums (115 MPa yield, 140-180 MPa tensile, 5 %
  elongation) are verified [5].
- Copper C110 H02: its modulus, tensile strength, elongation, n and minimum R/t (only its 37 ksi yield is verified [10]).
- Brass C260 H02: its modulus, n and minimum R/t (its tensile strength, yield and elongation are verified [11]).
- DIN 6935's k-factor formula as CAD bend tables apply it, and its range below R/t of about 0.65 [12].
- The 1° default tolerance is a convention, not a cited value.

## Sources

1. Kalpakjian and Schmid, Manufacturing Processes for Engineering Materials (Pearson): Table 2.3, K and n of annealed
   and tempered metals (304 annealed 1275 MPa and 0.45; 6061-T6 410 MPa and 0.05; 5052-O 210 MPa and 0.13); Table 7.2,
   minimum bend radius at room temperature, soft and hard (aluminium alloys 0 and 6t; low-leaded brass 0 and 2t;
   austenitic stainless 0.5t and 6t; low-carbon, low-alloy and HSLA steels 0.5t and 4t); the springback relation in
   R_i / R_f form, K_s = (2R_i/t + 1) / (2R_f/t + 1), and the outer fibre's strain e = 1 / (2R/t + 1).
2. Gardiner, "The springback of metals", Transactions of the ASME 79 (1957) 1-9.
3. Hosford and Caddell, Metal Forming: Mechanics and Metallurgy (Cambridge University Press), the chapter on bending:
   the springback of a power-law sheet bent in plane strain.
4. The Aluminum Association, Aluminum Standards and Data: approximate radii for 90° cold bending of sheet by alloy,
   temper and thickness (excerpted as Table 2 of "Sheet metal bend radii for aluminum and steel sheet and plate"), and
   the alloys' typical mechanical properties (5052-H32: 228 and 193 MPa, 12 %; 6061-T6: 310 and 276 MPa, 12 %;
   6061-O: 124 and 55 MPa, 25 %; E 70.3 and 68.9 GPa).
5. BlueScope Distribution, Aluminium 3003 data sheet: recommended minimum bend radii for 90° cold forming of 3003 sheet
   (reference test method ASTM E290), H14: 0t at 0.8 and 1.6 mm, 1t at 3.2 and 4.8 mm, 1½t at 6.0 mm; 3003-H14
   tensile 140-180 MPa, yield 115 MPa minimum, elongation 5 % minimum.
6. AISI, Fabrication guidelines for cold bending, as cited in the same excerpt: low-carbon steel (ASTM A366, now A1008
   CS) may be bent back on itself in any direction without cracking.
7. ASTM A1008 CS Type B, typical (non-mandatory) properties as a materials reference compiles them: yield 140-275 MPa,
   elongation 30 %.
8. SSAB, ASTM A1011 HSLAS Grade 50: yield 50 ksi (345 MPa), tensile 65 ksi (450 MPa), elongation 22 % minimum; SSAB
   Domex 355MC: minimum inner radius for a 90° bend 0.2t (1.8-3.0 mm) and 0.3t (3.0-6.0 mm), either direction.
9. ASM Handbook, Vol. 1: annealed type 304 and 316 sheet, typical properties; E 193 GPa.
10. McMaster-Carr, C110 copper sheet, H02 temper: yield 37 ksi (255 MPa); Copper Development Association, C11000:
    E 17 000 ksi, H02 tensile 42 ksi.
11. OnlineMetals, 260 brass sheet, H02: tensile 62 ksi (427 MPa), yield 52 ksi (358 MPa), elongation 23 %; Copper
    Development Association, C26000: E 16 000 ksi.
12. DIN 6935, cold bending of flat steel products: the neutral fibre's correction factor k = 0.65 + 0.5 lg(R/t)
    for R/t under 5, k = 1 above (the K-factor is k / 2).
13. SendCutSend, bending guidelines: K-factors typically 0.30 to 0.50; a bend relief at least half the thickness wide
    and the bend radius plus the thickness plus 0.020 in deep.
14. Protocase, Bend radii and minimum bend sizes: the radii its folder and press brakes bend by material and gauge
    (cold-rolled steel 16 ga, 0.060 in, at 0.03 in; 5052-H32 0.064 in at 0.035 in; 304 16 ga at 0.035 in).
