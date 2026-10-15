# Injection molding (`molding`)

A plastic part cooling in its injection mould, from the cavity full of melt until every point can be
ejected, and how far it warps once it is out: how long the mould has to stay shut, where thick
sections stay hot and sink, which walls are outside the resin's range, and the warp against a
tolerance. Lite, and the warp is an estimate from a model of cadgen's own: read [Limits](#limits)
before you report.

## When to use it

- "How long does it need to cool", "will this boss sink", "will it warp", "is this 1 mm wall too thin
  for PC", "are my ribs too thick": one moulded part in one of [the resins](#the-resins).
- Not for the fill (the flow front, short shots, weld lines, gate freeze), the pack, fibre orientation
  or the mould's own cooling channels: not in this version. Draft, rib and boss geometry rules are
  `$dfm`'s: send a full review there.

## The study

```json
{"process": "molding", "resin": "abs", "melt_temperature_C": 230, "mold_temperature_C": 60,
 "ejection_temperature_C": 90, "h_W_m2K": 2500, "warp_tolerance_mm": 0.1, "mesh": {"size_mm": 0.5}}
```

- `process` (required): `molding`.
- `resin` (required): a name from [The resins](#the-resins), or one of its plain names (`ABS`,
  `polycarbonate`, `PC/ABS`, `polypropylene`, `nylon 6`, `nylon 66`, `nylon`, `glass-filled nylon`,
  `acetal`, `delrin`, `acrylic`, ...).
- `melt_temperature_C`: the melt as it goes in. Default: the middle of the resin's melt window. Above
  the ejection temperature, and for a semi-crystalline resin above where it starts to crystallise.
- `mold_temperature_C`: the mould's (cavity surface's) temperature. Default: the middle of the
  resin's mould window. Below the ejection temperature.
- `ejection_temperature_C`: the part is stiff enough to eject below it everywhere. Default: the
  resin's.
- `h_W_m2K`: the heat transfer coefficient from the plastic to the mould on every face. Default 2500
  W/(m² K), a steel mould's contact with the plastic while it is packed [8]. An aluminium tool or a
  part that shrinks away from the steel early changes it; a large value (10⁶) holds every face at the
  mould temperature, the handbook formula's assumption.
- `warp_tolerance_mm`: the warp the part may have. Given, the warp is a check (an error over it);
  left out, the warp is reported only.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`, `refine`; elements are linear, order 1,
  the only order a moulding takes), `output`, `fit` (`iterative`, `defeature`) and `view`. A
  moulding has no `checks`: its findings are its verdict.
- Left without `mesh.size_mm`, the part is meshed three elements across its wall (the wall taken as
  2 V / A, a plate's own thickness), never coarser than `$fea`'s default. Give `mesh.size_mm` a quarter
  of the wall when the cooling time must be within about 5 %; see [When the model is big](#when-the-model-is-big).
- Not taken: `material` (the plastic is the `resin`), `parts` and `connections` (one part: name it
  with `--occurrence` in a document of several).

## The resins

Handbook and datasheet values at room temperature, held constant through the run. Melt and mould are
the processing guide's windows (the defaults are their middles); the ejection temperature is
Moldflow's or the CAMPUS datasheet's for a representative grade. A semi-crystalline resin releases
its crystallisation heat evenly over the range it crystallises over on cooling; an amorphous one has
none. Values marked * are estimates, listed under [Numbers not verified](#numbers-not-verified).

| `resin` | name | density, kg/m³ | conductivity, W/(m K) | specific heat, J/(kg K) | melt, °C | mould, °C | ejection, °C | crystallises, °C | crystallisation heat, kJ/kg | mould shrinkage, % | walls, mm | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `abs` | ABS | 1050 | 0.17 | 1400* | 210-241 | 38-71 | 86 | amorphous | 0 | 0.4-0.7 | 1.14-3.56 | [1], [2], [4], [6] |
| `pc` | Polycarbonate (PC) | 1200 | 0.20 | 1200 | 260-310 | 66-121 | 128 | amorphous | 0 | 0.5-0.7 | 1.02-3.81 | [1], [2], [4], [6] |
| `pc-abs` | PC/ABS | 1150 | 0.19* | 1300* | 229-260 | 49-71 | 104 | amorphous | 0 | 0.4-0.6 | 1.14-3.56* | [1], [2] |
| `pp` | Polypropylene (PP) | 904 | 0.16 | 1800 | 204-232 | 16-49 | 111 | 125 to 100* | 93* | 1.7-2.2 | 0.89-3.81 | [1], [2], [4], [6], [7] |
| `hdpe` | HDPE | 955* | 0.48 | 1900 | 193-232 | 21-66 | 80 | 120 to 105* | 190* | 1.5-2.5 | 0.76-5.08 | [1], [2], [4], [6], [7] |
| `pa6` | Nylon 6 (PA6) | 1130 | 0.26 | 1700 | 238-277 | 49-82 | 145 | 195 to 175* | 69* | 1.0-1.4 | 0.76-2.92 | [1], [3], [4], [6], [7] |
| `pa66` | Nylon 66 (PA66) | 1140 | 0.25 | 1670 | 285-302 | 66-96 | 180 | 240 to 220* | 75* | 1.7-2.2 | 0.76-2.92 | [1], [3], [4], [6] |
| `pa66-gf30` | Nylon 66, 30 % glass (PA66-GF30) | 1360 | 0.23 | 1410* | 280-300 | 80-90 | 195 | 240 to 220* | 52* | 0.4-0.9 | 0.76-2.92 | [2], [3], [4], [6] |
| `pom` | Acetal (POM) | 1410 | 0.27 | 1500 | 188-210 | 60-82 | 110 | 155 to 140* | 160* | 1.8-2.2 | 0.76-3.05 | [1], [2], [4], [6], [7] |
| `pbt` | PBT | 1300 | 0.21 | 1300* | 249-271 | 60-100 | 170 | 200 to 180* | 50* | 1.7-2.0 | 0.64-3.18 | [1], [2], [4], [5], [6] |
| `pmma` | Acrylic (PMMA) | 1180 | 0.18 | 1450 | 182-271 | 49-104 | 94 | amorphous | 0 | 0.2-0.6 | 0.64-12.7 | [1], [2], [4], [6] |
| `tpu` | TPU | 1175 | 0.26 | 1800* | 188-210 | 21-71 | 70* | none modelled | 0 | 0.8-2.5 | 2.03-19.05 | [1], [5], [6] |

- Melt, mould, density and shrinkage are the Chase processing guide's for unreinforced grades [1],
  its °F converted and rounded to the degree; PA66-GF30's are BASF Ultramid A3WG6's CAMPUS datasheet
  (shrinkage 0.4 % along the flow, 0.9 % across) [3].
- Ejection temperatures are the Moldflow database's for the grades in Lucyshyn et al. [2] (ABS
  Lustran LGA, PC Lexan ML7681, PC/ABS Cycoloy LG8002, PP Borealis RJ766MO, HDPE Marlex 9004, POM
  Ultraform N2320 003, PBT Pocan B 1505, PMMA Plexiglas 8N, PA66-GF30 Ultramid A3WG6, which its CAMPUS
  sheet also gives [3]); PA6's and PA66's are BASF Ultramid B3S's and A3W's CAMPUS sheets [3]
  (Moldflow's toughened Zytel ST801 PA66 reads 220 °C [2]).
- Conductivity and specific heat are the Professional Plastics table's at 23 °C [4] (the middle of a
  range where it gives one), PBT's and TPU's conductivity Kunststoff-Profi's [5]. A melt's specific
  heat runs well above its room-temperature value and its conductivity a little below, which this
  version does not follow: α = k / (ρ c) here is what the [hand check](#hand-checks) uses too.
- Walls are the design guide's recommended range for the resin family [6] (Nylon for the three
  polyamides, Polyester for PBT, Polyethylene for HDPE, Polyurethane for TPU).
- The crystallisation heat is the 100 %-crystalline heat of fusion [7] times a typical moulded
  crystallinity (PP 45 %, HDPE 65 %, PA6 30 %, PA66 38 % of 196 J/g, PA66-GF30 the same on 70 % of
  the mass, POM 49 %, PBT 35 % of 142 J/g), released evenly from where it starts to crystallise to
  where it ends (a DSC cooling exotherm's typical range). PP is ejected inside its range, so part of
  its heat comes out after ejection. TPU's hard segments crystallise a little, by grade: none is
  modelled.
- A semi-crystalline resin cools to its ejection temperature through its crystallisation plateau,
  where a small difference in temperature is a large one in time; its sink is judged at the time it
  starts to crystallise instead (below).

## How it is solved

- **Cooling.** The cavity starts full and packed at the melt temperature. Each face loses heat to the
  mould at `mold_temperature_C` through `h_W_m2K`; casting's enthalpy march (linear tets, lumped
  capacity, backward Euler, Newton on the nodes' enthalpies) follows it until every point is below the
  ejection temperature, keeping every joule of crystallisation heat however long the step.
- **Walls.** Each surface triangle's wall is its section along the inward normal where that crosses a
  wall (its middle at least a quarter of the section from every surface; a plate's edge face, a rib's
  top and a triangle at a wall's very edge measure none). The nominal wall is their area-weighted
  median; the thinnest is the wall at the low end that holds 0.5 % of the surface; the thickest is the
  widest ball that fits at a section's middle (a boss as tall as it is wide is as thick as it is wide).
- **Sink.** A region (at least 0.1 % of the volume and half the nominal wall cubed) that stays hot
  more than 1.2 times as long as the nominal wall does (its sections' 90th percentile) is a sink risk:
  a rib 0.6 of the wall leaves a root about 9 % thicker than the wall, which stays hot about 1.2 times
  as long. Three times as long (a section about 1.7 times the wall, a boss) is an error: it shrinks
  after its skin has set, so it sinks or voids. Hot means to the ejection temperature, or for a resin
  that crystallises above it, to where it starts to crystallise.
- **Warp, an estimate.** Each point shrinks by the resin's mould shrinkage: the low end of its range
  where it reached the ejection temperature as soon as the thinnest wall did, toward the high end the
  longer it stayed hot, low + (high - low) (1 - t_thin / t). The range's ends are the resin's published
  shrinkage ([The resins](#the-resins), [1]); this scaling between them is cadgen's own model, not a published
  law: it gives the right direction (the region that stays hot longest shrinks most and pulls the
  part toward it) and a plausible size, nothing more. The cavity is cut oversize by the part's mean
  shrinkage, so what differs from the mean is an inherent strain, applied the same in every direction
  in a linear static solve on quadratic tets made from the same linear ones. The part is held 3-2-1 as
  a fixture holds it to measure it: at three corners far apart, the first in x, y and z, the second
  across the line to it, the third along the normal of their plane. That takes out rigid motion and
  nothing else, so the hold puts no stress in (`hold_reaction_share` says so); the modulus cancels,
  and Poisson's ratio is 0.38 for every resin. The warp is the displacement from there.

## What comes out

- `part.molding.glb`, coloured by `ejection_time` (s), when each point reaches the ejection temperature:
  the last to cool is red. The other fields: `temperature` per frame (up to 24, from the melt to
  ejectable; the Time scrubber opens on the last frame with a point still too hot), `cooling_rate`
  (°C/s, the mean from the melt to ejection), `shrinkage` (% linear) and `warp` (mm, a vector; the
  part is drawn deformed by it, larger than life, and the Deformation slider sets how much).
- Curves `too_hot_percent` (the share of the volume still above the ejection temperature) and
  `mean_temperature` (°C), against time.
- Summary: `cooling_time_s` and `last_to_cool_at_mm`, `mean_ejectable_s` (when the part's mean is at
  the ejection temperature), `ejectable`, the temperatures and `h_W_m2K`, `volume_mm3`, `mass_g`,
  `hand_check`, `nominal_wall_mm`, `thinnest_wall_mm`, `thickest_wall_mm`, `wall_range_mm`,
  `nominal_wall_cools_s`, `hot_spots` (each `at_mm`, `ejectable_at_s`, `times_nominal`,
  `volume_mm3`), `max_warp_mm` and `max_warp_at_mm`, `warp_tolerance_mm`, `held_at_mm`,
  `hold_reaction_share`, `shrinkage_percent` and `mean_shrinkage_percent`, `heat_to_mould_J`,
  `energy_balance`, `steps`, `frames`. The sidecar's `verdict` is the checklist's; ready reads
  "Ready to mold · ejects in 12 s".
- CLI (a 40 x 30 x 2 mm ABS lid with an 8 mm boss, 6 mm tall): "ejectable in 43.3 s; the last to cool
  at [19.9, 14.8, 3.63] mm", "ABS at 225.5 °C into a mould at 54.5 °C (h = 2500 W/(m² K)), ejected
  below 86 °C", "plate formula for the thickest wall (7.9 mm): 81.1 s to its mean, 109 s to its
  middle with the mould's h", "walls 2 to 7.9 mm (nominal 2 mm); 1 hot spot; warp 0.0227 mm", then the
  checklist: "FAIL sink_void stays hot, against the nominal wall: 5.38×, needs below 1.2×; ...".

## Findings

Every check says pass (an `info` with what it `measured`) or what to change (a `fix`); [checks.md](checks.md#molding)
lists every type and the fix actions it can carry.

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `sink_void` | error | A region stays hot 3 times as long as the nominal wall or more (its place, how many times, its volume): it sinks or voids. | The fix: `thin` it (core it out) so no section is thicker than the nominal wall; a hollow boss's wall or a rib about 0.6 of it. |
| `sink_risk` | warning | A region stays hot 1.2 to 3 times as long as the nominal wall: a sink mark opposite it is likely; at a rib's root, the rib's share of the wall. | `thin` it toward the nominal wall; a rib's root under 0.6 of the wall. |
| `no_sink` | info (pass) | No region stays hot more than 1.2 times as long as the nominal wall: the latest, how many times. | Quote it. |
| `thin_wall` | warning | The thinnest wall is under the resin's recommended range: it may freeze before it fills (the run cannot see the fill). | `thicken` it to the range's low end, or gate closer to it. |
| `thinnest_wall` | info (pass) | The thinnest wall is within the range. | Quote it. |
| `thick_wall` | warning | The thickest section is over the resin's range: a long cycle, and sink or voids. | `thin` it to the range's high end, keeping the wall even. |
| `thickest_wall` | info (pass) | The thickest section is within the range. | Quote it. |
| `warp_over_tolerance` | error | The warp estimate is over `warp_tolerance_mm` (how much, where, the hold). Say it is an estimate from cadgen's own model. | `thin` the section that cools last toward the nominal wall (it shrinks most and pulls the part toward it), or a resin that shrinks less. |
| `warp_within_tolerance` | info (pass) | The warp estimate is within the tolerance. | Quote it as an estimate. |
| `warp` | info | No tolerance given: the warp estimate, where, the hold and the shrinkage range. | Give `warp_tolerance_mm` to judge it. |
| `hand_check` | info (pass) | The plate formula for the thickest wall against the simulation's last point, within 3 times. | Quote it as the check. |
| `hand_check_far` | warning | The two are more than 3 times apart. | Check the resin, the temperatures and `h_W_m2K`; a boss cools sooner than a plate of its thickness, which is not an error. |
| `cooling_time` | info | When every point is ejectable, and the last to cool. | Quote it; filling, packing and opening add to the cycle. |
| `melt_window` | info (pass) | The melt is within the resin's window, measured against the nearer end. | Quote it. |
| `melt_outside_window` | warning | The melt is outside the window. | `change_process` to the window's middle, or confirm the grade's own datasheet. |
| `mold_window` | info (pass) | The mould is within the resin's window, measured against the nearer end. | Quote it. |
| `mold_outside_window` | warning | The mould is outside the window. | `change_process` to the window's middle, or confirm the grade's own datasheet. |
| `mesh_across_wall` | info (pass) | About three elements or more across the nominal wall. | Quote it. |
| `coarse_mesh` | warning | Fewer: the middle of the wall cools too slowly (a fifth too slowly at two across) and a wall one element thick at once. | `refine_mesh` to a third of the wall (`params.mesh_size_mm`) and check again. |
| `fibre_filled` | info | PA66-GF30 shrinks about half as much along the flow as across it; the warp here takes it as the same every way. | Say so with the warp. |
| `not_ejectable` | warning | Not ejectable everywhere after 50 times the hand estimate: the times there are lower bounds. | Check the temperatures and `h_W_m2K`. |
| `time_limit` | warning | It stopped at its time limit (twice `fit.seconds`, at least 30 s). | A larger `fit.seconds`, or a coarser mesh. |

## Hand checks

- **The plate formula.** A wall of thickness s cooled from both faces held at the mould temperature
  reaches the ejection temperature [9]:

  t = s² / (π² α) ln(C (T_melt - T_mould) / (T_eject - T_mould)), α = k / (ρ c)

  with C = 8/π² for the wall's mean (the handbook's cycle-time formula) and C = 4/π for its middle,
  which is when every point of the wall is ejectable, what the simulation reports. A 2 mm ABS wall
  (α = 0.116 mm²/s, melt 225.5, mould 54.5, ejection 86 °C): 5.19 s to its mean, 6.78 s to its middle.
  The finding quotes both for the thickest wall, then its middle through the mould's `h` (the first
  eigenvalue λ of λ tan λ = h (s/2) / k replaces π/2 [10]: 7.71 s with h = 2500) with any
  crystallisation heat folded into the heat capacity (c + released heat / (T_melt - T_eject)): the
  best hand estimate, which the finding compares with the simulation.
- **What the tests hold.** A 2 mm ABS plate with its faces held at the mould temperature is ejectable
  within 8 % of the middle's formula at four elements across the wall (5 % slow: linear tets with a
  lumped capacity; about 10 % at three across, 23 % at two).
- **A boss or a thick corner** cools sooner than a plate of its thickness (it loses heat on more
  sides): the formula is the upper end there. A semi-crystalline resin cools later than its plain α
  says: [the estimates page](estimates.md#injection-moulding) gives the moulders' rules of thumb (a rib
  0.5-0.6 of the wall, walls within 25 % of each other).

## Limits

- The cavity starts full and packed at the melt temperature: filling and packing are not simulated,
  so a short shot, a weld line or a gate that freezes early is not seen (the thin-wall check is the
  proxy).
- The mould is a heat transfer coefficient to its temperature on every face, not meshed: no cooling
  channels, and a mould core or corner that runs hot is not seen.
- Constant room-temperature properties; crystallisation releases its heat evenly over a fixed range,
  whatever the cooling rate (a fast-cooled skin crystallises lower, and less).
- **The warp is an estimate from cadgen's own model, not a published law.** Each point's shrinkage
  is placed in the resin's published range by how long it stayed hot (1 - t_thin / t), a scaling
  cadgen chose, not one a source gives; it is the same in every direction, with no flow or fibre
  orientation, no pressure history and no mould constraint, applied elastically once the part is
  out. Say "estimate" with every warp number, read its pattern and its order of magnitude, never its
  last digit, and confirm a warp that matters with the moulder's own simulation or a trial shot.

## When the model is big

Linear tetrahedra (their lumped heat capacity keeps the enthalpy march monotone); the warp is solved
on quadratic tets made from them. A thin-walled part meshed three across its wall is many elements:
a 40 x 30 x 2 mm lid takes about a minute. Ladder: `iterative` and `defeature`. The time step adapts by
itself (two to three hundred steps from the melt to ejectable). Like every march, it stops at its
time limit (twice `fit.seconds`, at least 30 s) where it has got to, and says so.

## Sources

1. Chase Plastics, Common Processing Guide (May 2019): specific gravity, mould and melt temperature
   (°F) and shrinkage (in/in) for unreinforced ABS, PC, PC/ABS, PP, PE, PA 6, PA 6/6, POM, PBT, PMMA
   and PUR/TPU.
2. Lucyshyn, Des Enffans d'Avernas and Holzer, "Influence of the mold material on the injection
   molding cycle time and warpage depending on the polymer processed", Polymers 13 (2021) 3196,
   Table 2: melt, mould and ejection temperatures from the Moldflow 2016 database for the grades named
   above.
3. CAMPUS datasheets (Material Data Center): BASF Ultramid B3S (PA6: ejection 145 °C), Ultramid A3W
   (PA66: ejection 180 °C; melt 280-300, mould 60-80 °C; shrinkage 1.5 / 1.8 %) and Ultramid A3WG6
   (PA66-GF30: 1360 kg/m³, melt 280-300 °C, mould 80-90 °C, ejection 195 °C, shrinkage 0.4 % along the
   flow and 0.9 % across).
4. Professional Plastics, "Thermal Properties of Plastic Materials" (2008): thermal conductivity and
   specific heat at 23 °C (ABS 0.17; PA6 0.24-0.28 and 1700; PA66 0.25 and 1670; PA66 30 % glass 0.23;
   PBT 1200-2300 J/(kg K); PC 0.19-0.22 and about 1200; HDPE 0.45-0.52 and 1900; PMMA 0.17-0.19 and
   1400-1500; POM copolymer 0.23-0.30 and 1500; PP 0.10-0.22 and 1700-1900).
5. Kunststoff-Profi, "Thermal conductivity of plastics" (2026): PBT 0.21, TPU 0.26 W/(m K).
6. Protolabs, injection moulding design guidelines, "Improving part design with uniform wall
   thickness": recommended walls (ABS 1.143-3.556, acetal 0.762-3.048, acrylic 0.635-12.7, nylon
   0.762-2.921, polycarbonate 1.016-3.81, polyester 0.635-3.175, polyethylene 0.762-5.08,
   polypropylene 0.889-3.81, polyurethane 2.032-19.05 mm), adapted from manufacturingcenter.com.
7. TA Instruments, thermal analysis application notes, from Wunderlich's ATHAS data: heats of fusion
   of the 100 %-crystalline polymers, PE 293, PP 207, POM 326 and PA6 230 J/g.
8. Babenko, Sweeney, Petkov, Lacan, Bigot and Whiteside, "Evaluation of heat transfer at the
   cavity-polymer interface in microinjection moulding based on experimental and simulation study",
   Applied Thermal Engineering 130 (2018) 865-876: Moldflow's standard mould-melt heat transfer
   coefficient, 2500 W/(m² °C).
9. Menges, Michaeli and Mohren, How to Make Injection Molds, 3rd ed. (Hanser, 2001), the chapter on
   cooling: the cooling time of a plate to its mean (8/π²) and its middle (4/π).
10. Incropera, DeWitt, Bergman and Lavine, Fundamentals of Heat and Mass Transfer, 6th ed. (Wiley,
    2007), §5.5: the plane wall's one-term solution with convection, λ tan λ = Bi,
    C = 4 sin λ / (2λ + sin 2λ).

## Numbers not verified

Not found in a source this version could check; each is an estimate, and a datasheet for the grade
overrides it:

- ABS's specific heat (1400), PC/ABS's conductivity (0.19) and specific heat (1300, between ABS's
  and PC's), PBT's specific heat (1300, chosen inside the 1200-2300 [4] gives), TPU's specific heat
  (1800) and ejection temperature (70 °C), PA66-GF30's specific heat (1410: the mass-weighted
  mixture of PA66's 1670 and E-glass's about 800).
- HDPE's density (955: the upper part of the guide's polyethylene range, 915-965 [1]).
- PC/ABS's walls (no row in [6]: ABS's).
- Every crystallisation range (typical DSC cooling exotherms at about 10 K/min), the typical
  crystallinities behind the crystallisation heats, and the 100 %-crystalline heats of PA66 (196 J/g)
  and PBT (142 J/g).
- Poisson's ratio 0.38 for every resin, and the shrinkage's scaling by how long a point stayed hot
  (this version's model, not a published law).
- The 2500 W/(m² K) default is reported as Moldflow's standard value by [8], not read from Moldflow's
  own documentation.
