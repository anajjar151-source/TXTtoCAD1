# Heat treatment (`heat_treatment`)

A steel part quench hardened: from the furnace into the quenchant until it is under 500 °C, how fast
each point cools, how hard that makes it, how hard the quench pulls on it and how far it distorts.
Lite: read [Limits](#limits) before you report.

## When to use it

- "How hard will it be", "will the core harden", "how deep is the hardness", "will it crack in the
  quench", "will it distort", "oil or water": a steel part hardened by quenching from the
  austenitising temperature, one part at a time.
- Not for tempering, carburising (the case), induction or flame hardening, the transformation itself
  (bainite, retained austenite) or the residual stress left after: not in this version.

## The study

```json
{"process": "heat_treatment", "steel": "4140", "quenchant": "fast_oil",
 "target_hrc": 50, "mesh": {"size_mm": 2.5}}
```

- `process` (required): `heat_treatment`.
- `steel` (required): a grade from [The steels](#the-steels), or one of its plain names (`aisi 4140`,
  `42crmo4`, `100cr6`, `c45`, `ss410`, ...).
- `quenchant` (required): one of [The quenchants](#the-quenchants); it sets the heat transfer
  coefficient on every face and the bath's temperature. `water` and `air` mean still water and still
  air; `oil` is refused, as it is two quenchants here.
- `austenitize_C`: the furnace temperature it is quenched from. Default: the grade's. Above the
  eutectoid, 727 °C, and at most 1250 °C.
- `h_W_m2K`: a constant heat transfer coefficient replacing the quenchant's (a measured one, an
  agitated tank); the bath stays the quenchant's.
- `target_hrc`: the hardness the part must reach, HRC (20 to 70). With it, a surface under the target
  is an error, and the result says how deep the target reaches.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`, `refine`; elements are linear, order 1,
  the only order a heat treatment takes), `output`, `fit` (`iterative`, `defeature`) and `view`
  (controls, presets, sections and show; there are no `checks`: its findings are its verdict).
- Not taken: `material` (the steel is `steel`), `parts` and `connections` (one part: name it with
  `--occurrence` in a document of several).

## The steels

The composition is the middle of each grade's AISI/SAE range [1]. The Jominy curve of a low-alloy
grade is Just's formula from that composition [2]; the high-carbon and high-alloy grades lie outside
it and carry an estimated curve, which every result says (`estimated_curve`). The annealed yield is
what the quench's stress is judged against, scaled to the temperature ([Findings](#findings)).

| `steel` | name | composition, wt % | austenitise, °C | hardens in | Jominy curve | annealed yield, MPa | sources |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `1045` | AISI 1045 | C 0.465, Mn 0.75, Si 0.25 | 845 | water | Just: 61 HRC at the end, 35 at 6 mm, 30 at 10 mm, 22 at 20 mm | 310 | [1], [2], [3], [4] |
| `4140` | AISI 4140 | C 0.405, Mn 0.875, Si 0.25, Cr 0.95, Mo 0.20 | 845 | oil | Just: 58 to 6 mm, 54 at 10 mm, 46 at 20 mm, 37 at 50 mm | 417 | [1], [2], [3], [4] |
| `4340` | AISI 4340 | C 0.405, Mn 0.70, Si 0.25, Ni 1.825, Cr 0.80, Mo 0.25 | 845 | oil | Just: 58 to 10 mm, 52 at 20 mm, 44 at 50 mm | 470 | [1], [2], [3], [4] |
| `8620` | AISI 8620 (core) | C 0.205, Mn 0.80, Si 0.25, Ni 0.55, Cr 0.50, Mo 0.20 | 845 | oil | Just: 47 at the end, 34 at 6 mm, 22 at 20 mm | 385 | [1], [2], [3] |
| `52100` | AISI 52100 | C 1.04, Mn 0.35, Si 0.25, Cr 1.45 | 845 | oil | estimated: 65 at the end, 64 at 6 mm, 48 at 12 mm, 39 at 20 mm, 33 at 50 mm | 550 | [1], [3] |
| `o1` | AISI O1 tool steel | C 0.90, Mn 1.20, Si 0.30, Cr 0.50, W 0.50, V 0.15 | 800 | oil | estimated: 65 at the end, 60 at 10 mm, 46 at 18 mm, 35 at 50 mm | 400 | [1], [3] |
| `d2` | AISI D2 tool steel | C 1.55, Mn 0.35, Si 0.35, Cr 12.0, Mo 0.95, V 0.90 | 1010 | air | estimated: 62 throughout (air hardening) | 450 | [1], [3] |
| `h13` | AISI H13 tool steel | C 0.39, Mn 0.35, Si 1.0, Cr 5.13, Mo 1.43, V 1.0 | 1010 | air | estimated: 53 throughout (air hardening) | 400 | [1], [3] |
| `410` | AISI 410 stainless | C 0.12, Mn 0.50, Si 0.50, Cr 12.5 | 980 | air | estimated: 42 throughout (air hardening) | 275 | [1], [3], [4] |

- **Just's formula** [2], E the distance from the quenched end in mm (6 to 80) and K the ASTM grain
  size (7, a fine-grained steel's; phosphorus 0.015 %):
  J(E) = 95 √C - 0.00276 E² √C + 20 Cr + 38 Mo + 14 Mn + 5.5 Ni + 6.1 Si + 39 V + 96 P - 0.81 K
  - 12.28 √E + 0.898 E - 13 HRC, capped at the quenched end's 60 √C + 20. Nearer than 6 mm it runs
  straight from that cap at 1.5 mm; it never rises with distance and never reads under 20 HRC (the C
  scale's floor). Its range is C under 0.6 %, Cr under 2 %, Mn under 2 %, Ni under 4 %, Mo under
  0.5 %: 52100 and O1 (their carbon) and D2, H13 and 410 (their chromium) are past it.
- **The estimated curves** follow the grade's class: D2, H13 and 410 harden in still air, so their
  curve is flat at their as-quenched hardness; 52100 and O1 harden in oil and fall off past a few
  millimetres. Compare a mill's curve for the heat when the number matters.
- **8620** is a carburising grade: the result is its core's hardness; the case, carburised and harder,
  is not modelled (`core_only`).
- **The thermal properties** are one set for every grade: austenite's, which a part quenched faster
  than it transforms stays until it does, from Eurocode 3 for carbon steel [5]: density 7850 kg/m³,
  conductivity 27.3 W/(m K) (its value above 800 °C), specific heat 650 J/(kg K) (above 900 °C, where
  no transformation heat is folded in) and expansion 20 × 10⁻⁶ /K (the slope of its thermal
  elongation above 860 °C). The stress takes steel's room-temperature 200 GPa and 0.3 (`$fea`'s
  steel), so it is an upper bound: steel's modulus falls as it heats.

## The quenchants

One constant heat transfer coefficient on every face, and the bath's temperature, from the ASM
Handbook's table of quench severities [6] where it lists the quenchant. The boiling curve (the vapour
blanket, then boiling, then convection) is not modelled: the coefficient is constant, a stated limit.
Grossmann's severity H = h / 2k is reported per inch with austenite's conductivity; tables that give
still water about 1 per inch took room-temperature steel's, about twice as high.

| `quenchant` | what it is | h, W/(m² K) | bath, °C | H, per inch | source |
| --- | --- | --- | --- | --- | --- |
| `still_air` | still air | 200 | 27 | 0.09 | [6] |
| `forced_air` | air blown at about 5 m/s | 350 | 27 | 0.16 | [6] |
| `slow_oil` | a conventional (straight mineral) oil, still | 1100 | 65 | 0.51 | derived from [7] at [6]'s oil ratio |
| `fast_oil` | a fast (high-hardening) quench oil, still | 2000 | 60 | 0.93 | [6] |
| `polymer_10` | a 10 % polymer solution, still | 3500 | 43 | 1.6 | [6]'s 25 % PVP, conservative [8] |
| `still_water` | still water | 5000 | 32 | 2.3 | [6] |
| `brine` | brine, still | 9000 | 32 | 4.2 | derived from [7] at [6]'s water ratio |
| `agitated_water` | water moving at about 0.5 m/s | 12000 | 32 | 5.6 | [6] |

- **Slow oil and brine** are not in the table [6]: Grossmann's still conventional oil, H 0.25 to 0.30,
  and still brine, H 2 [7], are converted at the table's own h per H for its still fast oil (2000 for
  0.5) and still water (5000 for 1.1).
- **The polymer** row is the table's nearest, a 25 % PVP solution; a 10 % solution quenches faster,
  near still water [8]. Give `h_W_m2K` for yours.
- **Still air's 200** is the table's; an air-cooled part's coefficient falls as it cools (radiation
  is most of it when hot), so a slow air cool reads a little fast.

## What comes out

- `part.heat_treatment.glb`, coloured by `hardness` (HRC, as quenched): soft reads cold. The other fields:
  `cooling_rate` (°C/s, as each point passes 700 °C), `jominy_distance` (mm: the place on a Jominy bar
  that cools as fast), `temperature` per frame (up to 24, from the furnace to under 500 °C; the Time
  scrubber opens on the moment of the largest spread), and, at that moment, `quench_stress` (von
  Mises, MPa), `tension` (the largest principal stress, MPa) and the distortion, drawn by the
  Deformation control (`displacement`, mm).
- Curves `hottest_C` and `coolest_C` against time (the sidecar's `curves`).
- Summary: `surface_hrc` (lowest and highest), `core_hrc` and `core_at_mm` (the core: the point
  deepest under the surface), `softest_hrc`, `target_hrc`, `depth_to_target_mm`, `through_hardened`,
  `cooling_rate_core_C_s`, `cooling_rate_surface_C_s`, `jominy_core_mm`, `t85_core_s` and
  `t85_surface_s` (800 to 500 °C), `largest_spread_C` and when, `peak_tension_MPa`, where and its
  temperature, `hot_strength_MPa` there, `martensite_start_C`, `distortion_mm` and where,
  `hand_check` (the shape, the Biot number, the series' and the simulation's centre rate and t8/5,
  the half-martensite hardness, Grossmann's ideal critical diameter and this quench's), the heat
  (`heat_to_bath_J`, `heat_released_J`, `energy_balance`, at round-off), `steps`, `frames`. The
  sidecar's `verdict` is the checklist's; ready reads "Ready to quench · core 54 HRC".
- CLI: "AISI 4140 from 845 °C into a fast quench oil, still at 60 °C, h = 2000 W/(m² K): surface
  56.8 to 58.2 HRC, core 54 HRC", "the core cools at 30.2 °C/s at 700 °C, t8/5 11 s", "target 50 HRC:
  through-hardened", "peak quench tension 868 MPa against a hot strength of 267 MPa", "hand check
  (round): the centre cools at 30.6 °C/s at 700 °C, the simulation 30.2".

## Findings

A checklist: every check says when it passes, as an `info`. A check that compares a number with a
limit carries `measured` (`value`, `limit`, `units`, `pass_when`); every error and warning that has a
cure carries a `fix` (`action`, `summary`, `where`, `params`) an agent can apply and check again;
[checks.md](checks.md#heat_treatment) lists every type and the fix actions it can carry.

| Finding | Severity | What it means | Fix |
| --- | --- | --- | --- |
| `hardness` | info | The surface's hardness, the core's, and how fast the core cools at 700 °C (and its Jominy distance). | |
| `target_hardness` | info | With `target_hrc`: the whole surface reaches it; how deep it reaches, or that it hardens through. | |
| `soft_spot` | error | With `target_hrc`: a surface point under it (the softest, and the share of the surface). | `change_material` (a grade that holds the target at that point's Jominy distance, `params.steel`), else `change_quenchant` (the next faster, `params.quenchant`), else `thin`. |
| `quench_stress` | info | The quench's peak tension is under the steel's strength at that temperature: it does not yield. | |
| `quench_yield` | warning | The peak tension is over it: the part yields in the quench and keeps residual stress and some distortion. Most liquid quenches do. | `change_quenchant` (the next gentler), if the hardness still reaches what is needed. |
| `crack_risk` | warning, or info when it passes | A sharp edge (faces meeting at more than 30°) pulled past the strength there as it turns to martensite (under Ms). Hot austenite above Ms yields rather than cracks. | `add_fillet` (`params.radius_mm`: a tenth of the thickest section, at least 1 mm, a rule of thumb), or quench more gently. |
| `distortion` | warning when it yields, else info | How far and where it distorts while it cools unevenly, against the part shrunk evenly. | `change_quenchant` (gentler). |
| `section_change` | warning, or info when it passes | The thickest section more than 3 times the thinnest (a rule of thumb): the thin one hardens and shrinks first. | `thin` (`params.thickness_mm`: 3 times the thin one), or thicken the thin one. |
| `hand_check` | info | The series solution against the simulation's centre (within 1.25 times for a round or a block; 2 times for an equivalent round). | |
| `hand_check_far` | warning | Further apart than that. | `refine_mesh` (`params.size_mm`: half). |
| `beyond_jominy` | info | A share of the part cools slower than the grade's curve goes: it reads the curve's last value there. | |
| `estimated_curve` | info | The grade's Jominy curve is an estimate (52100, O1, D2, H13, 410). | |
| `core_only` | info | 8620: the core's hardness alone. | |
| `not_cooled` | warning | It stopped (50 times the hand estimate, or 20 000 steps) before the part was under 500 °C. | `check_inputs` (the quenchant and h, still above 500 °C), or `coarsen_mesh` (out of steps). |
| `time_limit` | warning | It stopped at its time limit (twice `fit.seconds`, at least 30 s). | A larger `fit.seconds`, or a coarser mesh. |

- **The hardness.** Each point's cooling rate at 700 °C is matched to the place on a Jominy bar that
  cools as fast, from the end-quench test's own rates [9] (log-log between its 1/16-inch stations:
  270 °C/s at 1.6 mm, 70 at 6.4, 18 at 12.7, 5.6 at 25.4, 2.0 at 50.8; slower than that, the last two
  stations' slope carries on), and the grade's curve read there. This is the Grossmann and Lamont
  practice [7].
- **The strength at temperature** is the grade's annealed yield times Eurocode 3's reduction of a
  carbon steel's yield with temperature [5] (1 to 400 °C, 0.78 at 500, 0.47 at 600, 0.23 at 700, 0.11
  at 800, 0.06 at 900): an estimate, as the part is austenite, not the annealed steel, through the
  quench.
- **Ms** is Andrews' linear formula [10], 539 - 423 C - 30.4 Mn - 17.7 Ni - 12.1 Cr - 7.5 Mo °C, the
  carbon taken at 0.6 % at most.
- **The moment** the stress is read is when the spread between the hottest and the coolest point is
  largest: the steepest gradient over the part.

## Hand checks

- **Grossmann's round, by the series.** The centre of a long round of radius R quenched at h cools as
  θ = Σ Cₙ exp(-λₙ² a t / R²), λₙ J₁(λₙ) = Bi J₀(λₙ), Bi = h R / k, Cₙ = 2 J₁(λₙ) / (λₙ (J₀² + J₁²));
  a slab of half-thickness L as Σ Cₙ exp(-λₙ² a t / L²), λₙ tan λₙ = Bi, Cₙ = 4 sin λₙ / (2 λₙ + sin
  2 λₙ); a finite round, or a block, is the product of its round's and its slabs' [11]. Grossmann's
  H = h / 2k makes Bi = H D: the conduction his critical diameters rest on [7]. The check holds
  a round's or a block's centre against it (the simulation reads within 3 % on a 2 mm mesh); any
  other shape against a long round as thick as its thickest section, an estimate.
- **The ideal critical diameter.** The half-martensite hardness, 44 √C + 14 HRC (Just [2], carbon at
  0.6 % at most), sits at some distance on the grade's Jominy curve; the largest long round whose
  centre cools that fast at 700 °C is the critical diameter, with h infinite Grossmann's ideal
  critical diameter D_I. 1045 reads about 24 mm (about an inch), 4140 about 120 mm; in still water a
  1045 round hardens to half martensite at its centre up to about 15 mm, in a fast oil up to about
  8 mm. An air-hardening grade never falls to it: none.
- **The core, by the same series.** A 10 mm square 1045 bar, 40 mm long, in still water cools at
  about 180 °C/s at its centre (Jominy about 3 mm, over 50 HRC); a 30 mm square one, 60 mm long, at
  about 36 °C/s (about 9 mm, about 31 HRC).

## Limits

- Thermal only: the steel is austenite through the quench with constant properties, and does not
  transform. No transformation heat (which slows the cooling where it transforms), no transformation
  strain (the expansion as martensite forms, which drives most quench cracking and distortion).
- One constant coefficient on every face: no vapour blanket or boiling stages, no faces shielded
  from the bath (a blind hole, a pocket), no agitation pattern. A real soft spot from a trapped vapour
  blanket is not seen.
- Hardness as quenched, before tempering, read from the cooling rate at 700 °C alone; a grade's
  curve is its composition's middle, and a real heat lies anywhere in its band. 8620's case is not
  modelled.
- The stress is elastic, at one moment: past the strength the part yields, and the permanent
  distortion and the residual stress that follow are not computed; the distortion shown springs back
  as the temperature evens out. The crack check reads that elastic stress against an estimated
  strength at sharp edges below Ms: a guide to where, not a prediction.

## When the model is big

Linear tetrahedra only (their lumped capacity keeps the march monotone, so each point passes 700 °C
once). Ladder: `iterative` (multigrid-preconditioned CG instead of a factor) and `defeature`. The
time step doubles while no point moves more than 6 °C in a step and halves past 25 °C (about a hundred
steps for a water quench); like every march it stops at its time limit (twice `fit.seconds`, at least
30 s) where it has got to, and says so.

## Sources

1. AISI/SAE standard steel compositions (SAE J403 and J404 for 1045, 4140, 4340, 8620 and 52100;
   ASTM A681 for O1, D2 and H13; ASTM A240/A276 for 410): the middle of each range.
2. E. Just, "New formulas for calculating hardenability curves", Metal Progress 96 (1969) 87-88, as
   reproduced in G. E. Totten (ed.), Steel Heat Treatment Handbook, 2nd ed. (CRC, 2006): the Jominy
   regression, the quenched end's 60 √C + 20 and the half-martensite 44 √C + 14.
3. ASM Heat Treater's Guide (ASM International, 1995): the austenitising temperatures and the
   quench each grade is made for.
4. Annealed yield strengths as tabulated at amesweb.info ("Yield strength of steel", after MatWeb):
   4140 annealed at 815 °C 417 MPa, 4340 annealed at 810 °C 470 MPa, 1045 hot-rolled 310 MPa; 410
   annealed is ASTM A276's 275 MPa minimum.
5. EN 1993-1-2 (Eurocode 3, fire design of steel structures), 3.2 and 3.4: carbon steel's density,
   conductivity (27.3 W/(m K) from 800 °C), specific heat (650 J/(kg K) from 900 °C), thermal
   elongation (2 × 10⁻⁵ per K from 860 °C) and the yield reduction factors k_y,θ.
6. ASM Handbook, Vol. 4, Heat Treating (1991), "Quenching of Steel": heat transfer coefficients and
   Grossmann H by quenchant, bath temperature and agitation (water at 32 °C still 5000 and at
   0.51 m/s 12000 W/(m² K); a high-hardening oil at 60 °C still 2000; 25 % PVP at 43 °C still 3500;
   air at 27 °C still 200 and at 5.08 m/s 350), as reproduced in QForm's heat-treatment documentation.
7. M. A. Grossmann, M. Asimow and S. F. Urban, "Hardenability, its relation to quenching, and some
   quantitative data", Hardenability of Alloy Steels (ASM, 1939); M. A. Grossmann, Elements of
   Hardenability (ASM, 1952): H = h / 2k, still oil 0.25 to 0.30, still water 0.9 to 1.0, still brine
   2; J. L. Lamont, "How to estimate hardening depth in bars", Iron Age 152 (1943).
8. B. Tiwary and K. N. Prabhu, "Assessment of quench severity of PAG polymer quenchants",
   Materials Performance and Characterization 3 (2014), doi 10.1520/MPC20140014: dilute PAG
   solutions quench about as severely as water.
9. ASTM A255, Standard Test Methods for Determining Hardenability of Steel (the end-quench test),
   and its cooling rates at 700 °C (1300 °F) at each 1/16-inch station, as tabulated in the ASM
   Metals Handbook and in W. D. Callister, Materials Science and Engineering (Wiley), the Jominy
   chapter.
10. K. W. Andrews, "Empirical formulae for the calculation of some transformation temperatures",
    Journal of the Iron and Steel Institute 203 (1965) 721-727.
11. H. S. Carslaw and J. C. Jaeger, Conduction of Heat in Solids, 2nd ed. (Oxford, 1959): the slab's
    and the cylinder's series with a surface coefficient, and the product solution.

### Not verified against the source

These were set from the handbooks' standard values without the source at hand; treat them as
estimates and replace them when you have the document:

- Just's coefficients ([2]) and the half-martensite 44 √C + 14.
- The end-quench cooling rates at each station ([9]), checked only at their ends (about 270 and 2 °C/s).
- The estimated Jominy curves of 52100, O1, D2, H13 and 410, and their as-quenched hardnesses.
- The annealed yields of 8620 (385), 52100 (550), O1 (400), D2 (450) and H13 (400) MPa, and 1045's
  annealed (the 310 is hot-rolled).
- The austenitising temperatures ([3]) and the compositions' middles ([1]).
- Grossmann's still oil 0.25 to 0.30 and still brine 2 ([7]), which set `slow_oil` and `brine`.
- Andrews' coefficients ([10]).
