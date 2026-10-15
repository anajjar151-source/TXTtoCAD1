# 3D printing (`printing`)

A part printed band by band, each band shrinking on the part below it: the distortion and residual
stress it is printed with, how far it curls off the plate once cut off, and whether a metal edge
rises into the recoater. Lite: read [Limits](#limits) before you report.

## When to use it

- "Will it warp or curl", "will the corners lift", "how much does it move when I cut it off the
  plate", "is the residual stress a cracking risk", "will the recoater hit it": an FDM, metal powder
  bed (LPBF, DMLS, SLM), SLS or resin print of one part.
- Not for printability itself (walls, overhangs, supports, orientation rules): `$dfam-check`'s.
  Not for the melt pool, the scan path, porosity or microstructure: not in this version.

## The study

```json
{"process": "printing", "technology": "powder_bed_metal", "alloy": "316l",
 "build_direction": [0, 0, 1], "bands": 12, "release_from_plate": true, "tolerance_mm": 0.2}
```

- `process` (required): `printing`.
- `technology` (required): `fdm`, `powder_bed_metal`, `sls` or `resin` ([The technologies](#the-technologies)).
- Its material (required): `alloy` for `powder_bed_metal`, `polymer` for the rest: a name from
  [The materials](#the-materials) or a plain name (`ti64`, `inconel`, `17-4`, `nylon`, `resin`, ...).
- `build_direction`: the direction the part grows in, `[x, y, z]` (default `[0, 0, 1]`). The plate is
  the part's lowest face along it, which must be flat (a part with none is refused: turn it).
- `bands`: how many height bands the build is cut into, 2 to 40 (default 12). Each band is a group
  of layers born at once; more bands follow the build more finely and cost a solve each.
- `release_from_plate`: let go of the plate once built (default `true`): the curl and springback of
  cutting it off. `false` reports it as printed, on the plate.
- `tolerance_mm`: what the warp and distortion are judged against. Left out, ISO 2768-2 class K's
  general flatness for the part's longest side (0.05 mm to 10 mm, 0.1 to 30, 0.2 to 100, 0.4 to
  300, 0.6 to 1000, 0.8 to 3000), and the result says so.
- `layer_thickness_mm`: the printer's layer (the recoater check's limit). Default: the material's.
- `chamber_temperature_C` (FDM): the air the part cools to, below where the polymer sets (default
  25 °C, an open printer). `bed_adhesion_MPa` (FDM): what the bed holds per area, to judge the plate's
  pull against.
- `inherent_strain`: `{"in_plane": -0.003, "build": 0}`, your machine's calibrated values
  (negative: a shrinkage), replacing the table's. Give it whenever the user has a calibration.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`, `order` 2 or 1), `output`, `fit`
  (`iterative`, `defeature`, `linear_elements`) and `view` (no `checks`: its findings are its verdict).
- Not taken: `material` (name it by the technology's key), `parts` and `connections` (one part: name it
  with `--occurrence` in a document of several).

## The technologies

| `technology` | names its material | held by | its inherent strain in the plane | along the build | recoater check |
| --- | --- | --- | --- | --- | --- |
| `fdm` | `polymer` | the bed, its lowest face | α (T_set - T_chamber): the layer cooling from where it sets to the chamber [7] | 0 | no |
| `powder_bed_metal` | `alloy` | the plate, its lowest face | Ti-6Al-4V's measured; the rest σ_y / E, the assumed strain [2], [4] | 0 [1] | yes |
| `sls` | `polymer` | nothing: it floats in its powder (held only against rigid motion) | 0 in the build: the bed is held above crystallisation [9] | 0 | no |
| `resin` | `polymer` | the build platform, its lowest face | a layer's linear cure shrinkage in the vat, about 1 % [10] | 0 | no |

- **Along the build: zero.** The cantilever calibrations of metal powder bed fusion take the inherent
  strain along the build direction as zero: the next layer is laid at the nominal height, which takes
  up the layer's own vertical shrinkage [1]; the high-fidelity calculation finds it negligible [2].
  The same holds for each technology here, whose next layer is also laid at its nominal height.
- **In the plane: one number.** A scan that rotates from layer to layer makes the inherent strain the
  same in every direction in the plane [1]; one stripe direction would not (its transverse strain is
  about a third of its longitudinal [1]). This version takes one number.
- **Metals.** Ti-6Al-4V's -0.0056 is calculated by a calibrated high-fidelity model of 60 µm layers on
  a 200 °C plate and validated against an actuator's distortion [2]. No calibration is published for
  the other alloys to take, so their strain is the commercial assumed strain, the as-printed yield
  strength over the modulus, with a strain scaling factor of 1 [4]: an estimate that a calibration
  print (a twin cantilever cut off its plate) replaces. Ti-6Al-4V's measured value is 0.58 of its own
  σ_y / E, so the estimates may read high by as much.
- **FDM.** A layer stops flowing as it sets, at its glass transition (an amorphous polymer) or its
  crystallisation (nylon), then shrinks with its expansion coefficient as it cools to the chamber
  [7]. An enclosure at a warmer `chamber_temperature_C` shrinks it less.
- **SLS.** The bed is held between the polymer's crystallisation and its melting point, so no layer
  shrinks on another while it is built; the whole cake cools and shrinks afterwards, which the
  printer's scale factors take up [9]. The run therefore distorts nothing, and says so: the warp of
  thick flat areas as the cake cools unevenly is not in this version. A calibrated `inherent_strain`
  makes it a layer model like the others.

## The materials

As-printed values: E, Poisson's ratio and the expansion are the wrought alloy's or the polymer's
handbook values, the yield the printer maker's as-built figure (the lower of its build directions).

| `polymer` / `alloy` | name | technology | E, GPa | Poisson | yield, MPa | expansion, 10⁻⁶/K | sets at, °C | layer, mm | in-plane strain | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `316l` | Stainless steel 316L | `powder_bed_metal` | 193 | 0.29 | 480 | 16.0 | | 0.04 | -0.00249 (σ_y / E) | [5], [6], [4] |
| `ti-6al-4v` | Ti-6Al-4V | `powder_bed_metal` | 113.8 | 0.342 | 1100 | 8.6 | | 0.06 | -0.0056 (measured) | [5], [6], [2] |
| `alsi10mg` | AlSi10Mg | `powder_bed_metal` | 70 | 0.33 | 230 | 20.9 | | 0.03 | -0.00329 (σ_y / E) | [5], [4] |
| `in718` | Inconel 718 | `powder_bed_metal` | 200 | 0.294 | 650 | 13.0 | | 0.04 | -0.00325 (σ_y / E) | [5], [6], [4] |
| `17-4ph` | Stainless steel 17-4PH | `powder_bed_metal` | 197 | 0.272 | 860 | 10.8 | | 0.04 | -0.00437 (σ_y / E) | [5], [6], [4] |
| `pla` | PLA | `fdm` | 3.5 | 0.36 | 60 | 68 | 60 (glass) | 0.2 | α (60 - T_chamber) | [8] |
| `petg` | PETG | `fdm` | 2.1 | 0.38 | 50 | 68 | 80 (glass) | 0.2 | α (80 - T_chamber) | [8] |
| `abs` | ABS | `fdm` | 2.2 | 0.35 | 40 | 90 | 105 (glass) | 0.2 | α (105 - T_chamber) | [8], [7] |
| `asa` | ASA | `fdm` | 2.0 | 0.35 | 45 | 95 | 100 (glass) | 0.2 | α (100 - T_chamber) | [8] |
| `pa` | Nylon (PA12 filament) | `fdm` | 1.7 | 0.40 | 48 | 110 | 150 (crystallisation) | 0.2 | α (150 - T_chamber) | [8] |
| `pc` | Polycarbonate | `fdm` | 2.3 | 0.37 | 60 | 68 | 147 (glass) | 0.2 | α (147 - T_chamber) | [8] |
| `pa12` | Nylon PA12 (SLS) | `sls` | 1.7 | 0.40 | 48 | | | 0.1 | 0 in the build | [9] |
| `standard-resin` | Standard acrylate resin | `resin` | 2.5 | 0.38 | 50 | | | 0.05 | -0.01 | [10] |

- The yields are as printed, before any heat treatment: a stress-relieved or aged part is weaker
  (Ti-6Al-4V about 930 MPa after 800 °C for 2 h [5]) and its residual stress is mostly gone.
- An open printer's ABS shrinks 90 × 10⁻⁶ × (105 - 25) = 0.72 % in the plane, PLA 0.24 %.

## How it is built

The part is cut into `bands` height bands along the build direction, each element in the band its
centroid falls in. Band by band, from the plate up, each is born stress-free on the part already
built, as that part has deformed (its nodes shared with the band below move with it from the
start), carries its inherent strain, and the part built so far, held at the plate, takes its load in
a linear static solve. An element's strain counts from its birth, so its stress is
C:(Σ ε(Δu) since its birth - ε*). A region that starts in mid-air (an overhang with nothing under it)
is held where it starts, as a support would hold it, and the result says so. Once built, the plate
lets go: the part's own stress, self-balanced, springs it back, held only against rigid motion. This
is the layer-by-layer inherent strain method of metal powder bed fusion [1], [3], with its layers
lumped into bands.

## What comes out

- `part.printing.glb`, coloured by the residual stress (von Mises, MPa) and deformed by the distortion
  (mm). Fields per frame: `von_mises`, `displacement` and `printed` (1 where printed so far). One
  frame per band ("Band 3/12 · 7.5 mm"), then "Off the plate"; the Viewer's Build scrubber opens on
  the last and Play builds it, band by band, then lets it go.
- Curve `max_distortion_mm` against the band.
- Summary: `technology`, `material`, `build_direction`, `bands`, `band_mm`, `height_mm`,
  `layer_thickness_mm`, `inherent_strain` (`in_plane`, `build`, `basis`), `yield_MPa`,
  `max_von_mises_MPa`, `von_mises_p99_MPa` and where, `released`, `max_distortion_mm` and where
  (off the plate, its rigid motion taken out), `warp_mm` and `warp_at_mm` (the bottom's flatness off
  the plate), `released_max_von_mises_MPa`, `tolerance_mm` and `tolerance_source`,
  `recoater_rise_mm` and where (metal), `plate_pull_MPa` and where, `starts_in_air`, `hand_check`,
  `frames`, and the `chamber_temperature_C` of an FDM print.
- CLI (a 40 x 30 x 6 mm block of 316L): "Stainless steel 316L by powder_bed_metal, 12 bands of 0.5
  mm, inherent strain -0.00249 in the plane, 0 along the build", "as printed: residual stress 1428
  MPa (99th percentile; yield 480 MPa)", "off the plate: the bottom lifts 0.0441 mm out of flat,
  distortion up to 0.073 mm (tolerance 0.2 mm)", "the most a band's top rises as it is printed:
  0.00807 mm (layer 0.04 mm)".

## Findings

Every check says what it measured against its limit (`measured`), passes included; every error and
warning carries the `fix` that makes it pass ([checks.md](checks.md#printing) lists every type and the
fix actions it can carry).

| Finding | Severity | What it measures | Fix |
| --- | --- | --- | --- |
| `warp` | error past `tolerance_mm`, else info | Off the plate, the bottom's flatness: the range of its points' lift about their best-fit plane, and where it lifts most (a corner, usually). | `change_orientation` (`params.build_direction`: the part's shortest axis up), `raise_chamber_temperature` (FDM, `params.chamber_temperature_C`), `stress_relieve` (metal, on the plate before it is cut off), `add_rib`. |
| `release_distortion` | error past `tolerance_mm`, else info | The largest distance any point moved from the CAD, its rigid motion taken out once off the plate. A free shrinkage counts: give a scaled CAD's tolerance if the printer compensates it. | As `warp`. |
| `distortion` | error past `tolerance_mm`, else info | The same as printed, on the plate, when the study keeps it there (`release_from_plate: false`). | As `warp`. |
| `residual_stress` | warning past yield, else info | The as-printed von Mises' 99th percentile against the yield (the peak, at a corner against the plate, is singular). Past yield the part yields and holds about yield: a cracking risk, and a metal part may tear off its plate or supports. The plate's pull is in its description. | `stress_relieve` (metal), `raise_chamber_temperature` (FDM), else `change_orientation`. |
| `recoater_collision` | warning past the layer, else info (metal) | The most a band's top rises along the build while it is printed, against `layer_thickness_mm`. | `support` the edge that rises, or turn it. |
| `bed_adhesion` | warning past `bed_adhesion_MPa`, else info (FDM) | The bed's pull on the part per area, averaged near where it pulls hardest; a note without `bed_adhesion_MPa`. | `add_brim` (`params.brim_mm`). |
| `starts_in_air` | info | A region with nothing under it, held where it starts. | Supports: `$dfam-check`. |
| `sls_no_build_shrinkage` | info | SLS shrinks nothing in the build; the cooling warp is not in this version. | The printer's design guide. |
| `hand_check` | info | [Hand checks](#hand-checks): the first band's middle against a band fully held, within 2 times. | |
| `hand_check_far` | warning | The two are more than 2 times apart. | `check_inputs`: the build direction and the inherent strain. |

## Hand checks

- **A band held on the plate.** Fully held in its plane, a band that would shrink by ε carries the
  equal-biaxial stress σ = E |ε| / (1 - ν), whose von Mises is σ. The first band's middle reads it:
  a 316L block, 676 MPa by hand against 605 simulated (0.89×); a wall thinner than a band is held
  along its length only and reads down to (1 - ν) of it. Every result carries this check.
- **The method: a thin cantilever plate.** A plate whose inherent strain varies uniformly through its
  thickness, ε*(z) = -g (z - t/2), curls with curvature g (beam theory, and a compatible strain: no
  stress). Clamped at one end its tip rises g L² / 2; free, it bows g L² / 8 end to middle. The
  solver reads both to within 1 % (40 x 4 x 2 mm, g = 0.001/mm: 0.80 mm and 0.20 mm), and the
  cantilever is how metal printers calibrate the inherent strain: print a twin cantilever, cut it
  off its plate, measure the curl [1], [4].
- **FDM, by hand.** Armillotta's model of a flat part, the last layer's force α (T_g - T_c) E w Δh
  released at its lever arm, gives a warp of (3/4) α (T_g - T_c) (l / h)² Δh (1 - Δh / h) at
  mid-span for a part l long and h tall printed in layers Δh thick [7] (an estimate:
  [estimates.md](estimates.md#3d-printing)). It is a beam's bow; the simulation's warp of a squat
  part is mostly at its ends.

## Check, fix, check again

As `SKILL.md` says for casting: run it, read `verdict` and each finding's `fix` from the sidecar,
make the fix, run it again until it is `ready`. The fixes a printing study gives:

- `change_orientation`: the study's `build_direction` to `params.build_direction` (the part's
  shortest axis): a squat part keeps its shrinkage locked in evenly and curls less once cut off.
- `raise_chamber_temperature`: the study's `chamber_temperature_C`, only if the user's printer has
  an enclosure that reaches it; else, with the user's word, a polymer that warps less (PETG, PLA).
- `stress_relieve`: a heat treatment on the plate before it is cut off; the run does not model one,
  so tell the user and judge the as-printed result with `release_from_plate: false`.
- `support`, `add_brim`, `add_rib`: the part or the print setup (`$cad`, the slicer); a rib changes
  the model, so rebuild the STEP.
- `check_inputs`: the study, not the part.

Never change the technology or the material to clear a finding without the user's word.

## Limits

- The layers are lumped into bands, each carrying one inherent strain for the whole part: the scan
  pattern, the heat that builds up in a tall part and the plate's temperature are in that number, not
  computed. A metal's strain other than Ti-6Al-4V's is an estimate until calibrated.
- Linear elastic: past yield the real part yields and holds about yield, so a stress past yield is an
  upper bound and the distortion beside it an estimate.
- The plate is rigid and supports are not modelled; a real plate bends under the part's pull, which
  adds to the curl once the part is cut off. The curl the run finds is mostly at the part's ends,
  where the bands cannot hold each other; a long squat part held evenly reads little.
- A recoater rise is a band's, of many layers, not one layer's: a rise past a layer is a risk to
  confirm, not a crash.
- SLS shrinks nothing in the build; its cooling warp is not simulated.

## When the model is big

A linear solve per band, and one for the release, on quadratic tetrahedra by default. Ladder:
`iterative` (multigrid-preconditioned CG), `defeature`, `linear_elements` (linear tetrahedra bend
too stiffly: the curl reads low). Fewer `bands` cost fewer solves.

## Sources

1. Setien, Chiumenti, van der Veen, San Sebastian, Garciandía and Echeverría, "Empirical methodology
   to determine inherent strains in additive manufacturing", Computers & Mathematics with
   Applications 78 (2019) 2282-2295: the inherent strain along the build taken as zero ("the
   vertical shrinkage of the deposited layer is compensated by the recoating phase"); twin-cantilever
   calibration of Ti-6Al-4V; transverse over longitudinal 0.33 for one stripe direction, and a
   periodic rotating scan isotropic in the plane; layers lumped into thicker ones.
2. Setien, Chiumenti, San Sebastian, Caicedo and Moreira, "Defining and Optimising High-Fidelity
   Models for Accurate Inherent Strain Calculation in Laser Powder Bed Fusion", Metals 15 (2025) 180,
   doi:10.3390/met15020180: Ti-6Al-4V, -0.0056 isotropic in the plane, the build-direction and shear
   components negligible; 60 µm layers on a 200 °C plate.
3. Liang, Chen, Cheng, Hayduke and To, "Modified inherent strain method for efficient prediction of
   residual deformation in direct metal laser sintered components", Computational Mechanics 64 (2019)
   1719-1733: the inherent strain applied layer by layer in static solves.
4. Ansys Additive Print, "Assumed Strain" and "Strain Scaling Factor" (help, 2024 R2): a constant,
   isotropic strain of the strain scaling factor times the yield strength over the modulus, the
   factor 1 by default and calibrated per machine and material; the LPBF Calibration Guide (2025 R2):
   calibration on cantilevers cut from their supports.
5. EOS material data sheets, as manufactured, Rp0.2 vertical / horizontal: StainlessSteel 316L (EOS
   M 290, 40 µm) 480 / 540 MPa; Titanium Ti64 (M 400 FlexLine, 2017) about 1100 MPa, 930 after 2 h at
   800 °C; Aluminium AlSi10Mg 230 / 270 MPa; NickelAlloy IN718 650 / 800 MPa; StainlessSteel 17-4PH
   (M 290, 40 µm) 860 / 890 MPa. AlSi10Mg's modulus 69-71 GPa as built and its expansion 20.9 ×
   10⁻⁶/K (20-100 °C) from Renishaw's and 3D Systems' AlSi10Mg data sheets.
6. ASM Handbook, Vol. 1 and 2, and the makers' data: wrought 316 (193 GPa, 16.0 × 10⁻⁶/K),
   Ti-6Al-4V (113.8 GPa, 0.342, 8.6 × 10⁻⁶/K), Inconel 718 (Special Metals: 200 GPa, 0.294,
   13.0 × 10⁻⁶/K), 17-4PH (AK Steel: 197 GPa, 0.272, 10.8 × 10⁻⁶/K).
7. Armillotta, Bellotti and Cavallaro, "Warpage of FDM parts: experimental tests and analytic
   model", Robotics and Computer-Integrated Manufacturing 50 (2018) 140-152: a new layer shrinks by
   α (T_g - T_c) as it cools to the chamber, the platform's reaction holds it, and the part bends by
   it once removed.
8. The polymers: glass transitions ABS 105-110 °C, PLA 50-80, PETG 70-80, nylon 47-60 (its
   crystallisation, not given there, is taken here), PC 145-150; expansion ABS 72-108 × 10⁻⁶/K, PLA
   about 70-85, PC 65-70, nylon 50-110 by grade (generic ranges from filament reviews and the
   Engineering ToolBox's table); moduli and yields as in `$fea`'s material table.
9. Goodridge, Tuck and Hague, "Laser sintering of polyamides and other polymers", Progress in
   Materials Science 57 (2012) 229-267: the sintering window between crystallisation and melting;
   curl when the bed is too cold.
10. Guess and Chambers, Sandia report on SL 5149 and SL 5170 (1995), and Ullett, Rodrigues and
    Chartoff, "Linear shrinkage of stereolithography resins", Solid Freeform Fabrication Symposium
    (1995): an acrylate strand's linear shrinkage as it cures, about 1 % from one exposure.

Not checked against the source this time: ASA's expansion and glass transition, nylon's 150 °C
crystallisation, the resin's 1 % (read from a search summary of [10]), the wrought values in [6]
and [9]'s content (from memory). ISO 2768-2's class K figures are from memory of the standard.
