# Casting (`casting`)

The metal poured into its mould, from the pour to fully solid: where it freezes last, whether the
feeders reach it, where porosity is likely and whether thin sections freeze before the mould fills.
Lite: read [Limits](#limits) before you report.

## When to use it

- "Will it cast", "where will it shrink or be porous", "is my riser in the right place", "will this
  1 mm frame on a silver pendant fill", "how long until I can knock it out": a sand, investment
  (lost-wax, a jeweller's flask included), permanent-mould or die casting of one part.
- Not for the mould filling itself (the flow front, air entrapment, turbulence), gas porosity,
  hot tears or the grain structure: not in this version.

## The study

```json
{"process": "casting", "alloy": "a356", "mold": "sand",
 "pour_temperature_C": 720, "mold_temperature_C": 25,
 "feeders": [{"faces": ["#o1.f12"]}, {"faces": ["#o1.f3"], "h_W_m2K": 50}],
 "fill_time_s": 4, "mesh": {"size_mm": 2}}
```

- `alloy` (required): a name from [The alloys](#the-alloys), or one of its plain names (`sterling`,
  `925`, `14k`, `18k`, `bronze`, `brass`, `zamak`, `gray-iron`, `cast-steel`, `316`, ...).
- `process` (required): `casting`.
- `mold` (required): `sand`, `investment`, `permanent_mold` or `die`
  ([The moulds](#the-moulds)). It sets the mould's temperature, the pour's superheat and the
  mould's heat transfer coefficient.
- `pour_temperature_C`: the metal's temperature as it goes in; above the liquidus. Default: the
  liquidus plus the mould's superheat.
- `mold_temperature_C`: the mould's temperature at the pour (a flask's or a die's preheat); below
  the solidus. Default: the mould's.
- `h_W_m2K`: a constant heat transfer coefficient from the metal to the mould, replacing the
  mould's own (a coated die, a chill you have a number for).
- `feeders`: the faces metal feeds from while the casting freezes: the gate, the riser, the sprue's
  contact, by the Viewer's selectors. Each entry takes `faces`, and optionally `h_W_m2K` (its own
  coefficient to the mould temperature; left out, the face is insulated, as a riser's metal sits on
  it) or `held_C` (held at that temperature until the rest is solid, or at most 1.44 times
  Chvorinov's time for the casting, as long as a riser of 1.2 times its modulus stays liquid; then
  cooled like the mould). A feeder is taken to stay liquid until the casting is solid.
- `fill_time_s`: how long the mould takes to fill. Left out, it is estimated from the mass (see
  [The moulds](#the-moulds)), and the result says so.
- `duration_s`: how long to follow it. Left out, until every point is solid.
- Shared keys, as in `$fea`'s study file: `mesh` (`size_mm`, `refine`; elements are linear, order 1,
  the only order a casting takes), `output`, `fit` (`iterative`, `defeature`) and `view` (controls,
  presets, sections and show; a casting has no `checks`: its findings are its verdict).
- Not taken: `material` (the metal is the `alloy`), `parts` and `connections` (one part: name it
  with `--occurrence` in a document of several).

## The moulds

| `mold` | the mould | mould temperature, °C | superheat, °C | heat transfer | fill time estimate |
| --- | --- | --- | --- | --- | --- |
| `sand` | sand, at room temperature | 25 | 100 | the sand heats as it takes heat in: h = e / √(π t), e = 1000 W s^½/(m² K) | 2 s per √kg |
| `investment` | a jeweller's flask or a ceramic shell, preheated | 600 | 100 | as sand, e = 600 W s^½/(m² K) | 2 s per √kg |
| `permanent_mold` | a coated steel or iron gravity die | 300 | 100 | constant, 1000 W/(m² K) | 2 s per √kg |
| `die` | a steel die, high-pressure | 200 | 60 | constant, 5000 W/(m² K) | 0.05 s |

- **The insulating moulds.** A sand or investment mould conducts so poorly that it, not the metal,
  sets the freezing time: its face heats up as it takes heat in, like a semi-infinite body, so its
  coefficient falls as e / √(π t) with e = √(k ρ c) its effusivity, the metal-mould contact taken as
  perfect. This is Chvorinov's own model, and why the freezing time grows with the square of the
  section [14]. Silica sand: k ≈ 0.6-0.9 W/(m K), ρ ≈ 1500 kg/m³, c ≈ 1130-1170 J/(kg K),
  e ≈ 1020-1260 [15]; measured in bonded moulding sands, 1140 (green sand) and 1300 (oil-bonded),
  and 790-1040 from handbook data [19]. The preset's 1000 sits in that range. Gypsum-bonded
  investment's 600 is unverified: no measured value for a jeweller's investment was found, and it
  is an estimate from plaster's properties (k 0.16-0.50, ρ 950-1300, c 840-1000: e ≈ 360-810 [20]);
  a ceramic shell conducts better. Give `h_W_m2K` or `mold_temperature_C` where you know better.
- **The investment flask's 600 °C** is a jeweller's (Cooksongold's 600-650 °C for 14k gold [2]); a
  steel shell is preheated hotter and an aluminium one cooler, so for those give
  `mold_temperature_C`. An alloy whose solidus is under the preset's mould temperature (aluminium,
  zinc in a 600 °C flask) is refused until you do.
- **The metal moulds.** A permanent mould's or a die's coefficient is the metal-mould contact's,
  set by the coating and the gap that opens as the casting shrinks: reported values for permanent
  moulds run 500-16,000 W/(m² K) [16]. The presets are Flemings's round numbers, 1000 W/(m² K) for
  a carbon-coated die and 5000 under high pressure (10,000 for a polished die) [21], not
  measurements: in a high-pressure die the peak is higher still, 42,000 fitted to die thermocouples
  for AlSi9Cu3Fe [22]. Give `h_W_m2K` when the foundry has one.
- **Superheat** is the usual 50-150 °C above the liquidus (Cooksongold pours 14k at 930-1020 °C
  against its 870 °C liquidus [2]); the presets take the middle.
- **The fill time estimate** is the form of the gating rules' pouring time, t = K √(mass) [17]:
  for grey iron K = K_f (1.41 + T/14.59), T the section in mm and K_f about 1, so 1.8 to 3.1
  s/√kg for 5 to 25 mm sections; for steel K = 2.43 - 0.395 log₁₀(mass in kg), 2.4 at 1 kg to 1.6
  at 100 kg. The gravity preset takes K = 2 s/√kg from these (no rule for light alloys or
  precious metals was found: unverified for them). A die fills in 1-100 ms, 6-7 ms for thin walls
  and 30-80 ms for thick ones [25]; the preset is a flat 0.05 s. Both are orders of magnitude,
  labelled as estimates in every result. A jeweller's 10 g pendant reads 0.2 s. Give `fill_time_s`
  when the misrun answer matters.

## The alloys

Room-temperature handbook values, held constant through the run. Latent heats marked * are not
published for the alloy and are estimates, the mass-weighted sum of its elements' (CRC [1]);
marked †, an alloy with silicon, they are the NPL estimate [23], the liquidus times the
mole-weighted sum of its elements' entropies of fusion. Mass weighting counts silicon's large heat
of fusion in full and reads high wherever silicon is a few percent: 494 kJ/kg for A356 against a
measured 425 [24], and 538 for the ADC12 die-casting alloy against a measured 411 [26], where the
NPL estimate reads 417 and 415. Values marked ‡ are unverified: no source for the alloy was found.
A critical Niyama value is given where one is published; where none is, the result shows where
Niyama is lowest and says no threshold is known.

| `alloy` | name | density, kg/m³ | conductivity, W/(m K) | specific heat, J/(kg K) | latent heat, kJ/kg | liquidus, °C | solidus, °C | critical Niyama, (°C·s)^½/mm | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sterling-silver-925` | Sterling silver 925 | 10360 | 350 | 246* | 112* | 892 | 810 | none published | [4], [1] |
| `fine-silver` | Fine silver 999 | 10490 | 429 | 235 | 104.6 | 961.8 | 961.8 | none (a pure metal) | [1] |
| `gold-14k-yellow` | 14k yellow gold | 13000 | 66‡ | 222* | 109* | 870 | 830 | none published | [2], [1], [6b] |
| `gold-18k-yellow` | 18k yellow gold | 15300 | 66‡ | 174* | 87* | 900 | 860 | none published | [3], [1], [6b] |
| `tin-bronze` | Tin bronze C90500 | 8720 | 74.8 | 377 | 192* | 999 | 854 | none published | [5], [1] |
| `silicon-bronze` | Silicon bronze C87300 | 8360 | 28.4 | 377 | 236† | 971 | 821 | none published | [5], [23] |
| `yellow-brass` | Yellow brass C85400 | 8440 | 87.9 | 377 | 172* | 941 | 927 | none published | [5], [1] |
| `a356` | A356 aluminium | 2685 | 151 | 963 | 425 | 615 | 555 | 0.3 | [6], [24], [12] |
| `a380` | A380 aluminium | 2710 | 96.2 | 963 | 400† | 593 | 538 | none published | [7], [23], [26] |
| `zamak-3` | Zamak 3 | 6600 | 113 | 419 | 120* | 387 | 381 | none published | [7], [1] |
| `grey-iron` | Grey iron (class 30) | 7150 | 46 | 490 | 230‡ | 1200 | 1150 | none (graphite expansion) | [8], [27] |
| `ductile-iron` | Ductile iron 65-45-12 | 7100 | 36 | 460 | 230‡ | 1160‡ | 1120‡ | none (graphite expansion) | [8] |
| `wcb-steel` | Cast carbon steel WCB | 7850 | 50 | 486 | 247 | 1502 | 1462 | 0.775 | [9], [1], [28], [10] |
| `cf8m-stainless` | CF8M stainless | 8000 | 16.3 | 500 | 290 | 1430 | 1375 | 1.0 | [9], [28], [29], [11] |

- Sterling's conductivity is about 350 W/(m K) by the Wiedemann-Franz law from its electrical
  conductivity. No measured conductivity for 14k or 18k yellow gold was found: both take 66 W/(m K),
  an AuAg20Cu10 alloy's (about 17k) on its maker's datasheet [6b]; the Wiedemann-Franz law from
  the same sheet's 12.5 % IACS gives 45-62. In a small investment casting the flask, not the metal,
  sets the freezing time, so these change it little.
- Fine silver freezes at one temperature; it is solved over a 1 °C range so its enthalpy has a
  slope. Its Niyama value means little: a pure metal shrinks into a pipe or a centreline cavity where
  it freezes last, which the hot spots show.
- The copper alloys are the CDA's, converted from its US units [5]. The CDA gives no specific heat
  for C87300: it takes that of C65500, the wrought 3 % silicon bronze (0.09 Btu/(lb °F)). The
  mass-weighted estimates of the other two agree with the NPL estimate within 6 % (191 and
  183 kJ/kg).
- A356: 425 kJ/kg is the measured latent heat of LM25, its British equivalent, and a DSC of A356
  itself gave 424 [24]. Its solidus and liquidus are given as 555-570 and 610-620 °C by
  different sources [6], [24]. A380 has no published latent heat that was found: 400 is the NPL
  estimate, near the 411 measured for ADC12, a die-casting alloy of the same family [26].
- Grey iron's liquidus is the thermal-analysis regression's for class 30 (C 3.1-3.4, Si 1.9-2.3):
  1180-1220 °C, about 1195 at C 3.3 %, Si 2.1 % (carbon equivalent 4.0); its solidus is the stable
  eutectic, about 1150 °C (1153 in the iron-carbon diagram; silicon raises it, and undercooling
  puts a casting's eutectic arrest a few degrees lower) [27]. Ductile iron's 1160/1120 °C match
  only a materials database: unverified. The irons' 230 kJ/kg is unverified: no measured value was
  found, and estimates run 220-280 (the NPL estimate for C 3.3 %, Si 2.1 %, carbon left out, is
  223; materials databases list 260-280 without a method). Grey and ductile iron expand as graphite
  forms, which offsets part of their shrinkage: Niyama, a steel criterion, is not a reliable
  indicator for them.
- WCB's liquidus is the steel founders' benchmark dataset's, 1502 °C, and MAGMA's C19Mn5's, 1501
  [28]. Its solidus is C19Mn5's, 1462 °C (a 39 °C freezing range); the benchmark WCB dataset is not
  fully solid until 1411 °C (91 °C), its solid fraction rising steeply below the liquidus and
  slowly at the end [28]. Its latent heat is iron's own, 247 kJ/kg [1]: the two datasets use 180
  and 274 [28].
- CF8M's liquidus, 1430 °C, is the steel founders' benchmark dataset's [28] (NIST's 316L reference
  steel melts at 1402-1435 °C [29]); its solidus is wrought 316's, 1375 °C [9] (the benchmark
  datasets give their cast steels freezing ranges of 70-110 °C [28]). Its latent heat is the
  290 kJ/kg measured for that 316L [29].
- The thresholds: WCB's 0.775 is Niyama's own, 1 (°C·min)^½/cm, in these units [10]; CF8M's 1.0 is
  the value Carlson and Beckermann used for nickel alloys and austenitic stainless steels [11]; A356's
  0.3 is the upper end of the 0.2-0.3 one study found for centrifugally cast A356 [12]. Thresholds
  depend on the alloy and the mould and are not established for most alloys [13].

## What comes out

- `part.casting.glb`, coloured by `solidification_time` (s), the time each point is fully solid: the
  last to freeze is red. The other fields: `temperature` and `liquid_fraction` per frame (up to 24,
  from the pour to fully solid; the Viewer's Time scrubber opens on the last frame with liquid),
  `niyama` ((°C·s)^½/mm, at a tenth of the freezing range above the solidus, near the end of
  solidification) and `cooling_rate` (°C/s, there). Nothing deforms.
- Curve `liquid_percent`: the share of the volume still liquid against time (the sidecar's `curves`).
- Summary: `solidification_time_s` and `last_to_freeze_at_mm`, `first_solid_s`, `fully_solid`,
  `alloy`, `mold`, `pour_temperature_C`, `mold_temperature_C`, `mold_words`, `volume_mm3`,
  `mass_g`, `modulus_mm` (V/A of the cooled faces), `hand_check`, `fill_time_s` and
  `fill_time_estimated`, `hot_spots` (each `at_mm`, `freezes_at_s`, `cut_off_at_s`, `volume_mm3`,
  `unfed`), `thinnest_section_mm` and `thinnest_section_solid_s`, `min_niyama`, `niyama_critical`,
  the heat: `heat_to_mould_J`, `heat_from_held_feeders_J`, `heat_released_J` and `energy_balance`
  (their mismatch, a share; the march keeps it at round-off), `steps`, `frames`.
- CLI (a 30 mm cube of A356 in sand): "solid in 2.49 min; the last to freeze at [x, y, z] mm",
  "A356 aluminium poured at 715 °C into a sand mould at 25 °C, h falling as it heats (...)",
  "Chvorinov's rule: 2.52 min for V/A 5 mm", "1 hot spot; thinnest section 30 mm, solid through at
  2.44 min; the mould fills in about 538 ms (estimated)".

## Findings

Each check says what it measured against its limit, passes included, and each error and warning
carries the fix that makes it pass ([checks.md](checks.md#casting) lists every type and the fix
actions it can carry).

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `misrun` | error | A section is solid through before the mould has filled (its thickness, place and time): a misrun or cold shut. | Thicken it to the `params.thickness_mm` that stays liquid 3 times the fill, preheat the mould, or gate closer to it; with an estimated fill time, ask for the real one first. |
| `misrun_risk` | warning | A section freezes within 3 times the fill time: metal stops flowing before it is solid, and the run's instant fill is optimistic. | As for `misrun`. |
| `thinnest_section` | info | Passes: no section freezes that soon. The thinnest, its thickness and when it is solid through, against 3 times the fill time. | Quote it; it is the user's margin. |
| `shrinkage_hot_spot` | error | A region that freezes after everything around it, cut off from every feeder while still liquid (its place, the liquid volume cut off, when): shrinkage porosity collects there. With no feeder named, the region that freezes last. | Feed it: a riser on its nearest face, of 1.2 times its modulus by Chvorinov's rule (`add_feeder`, or `enlarge_feeder` for one that does not reach it); or thin it so it freezes before its feed path, or chill it. |
| `no_hot_spot` | info | Passes: it freezes toward its feeders, no liquid pocket cut off from them (the largest that is, against a hot spot's size). | Quote it. |
| `low_niyama` | warning | Niyama is under the alloy's critical value over a share of the casting (the lowest and where): porosity is likely there. Near a feeder's faces it is left out (the feeder's own). | Read it with the hot spots: the same cures. It marks where, not how much. |
| `niyama_ok` | info | Passes: Niyama stays at the alloy's critical value or above away from the feeders (the lowest and where). | Quote it. |
| `niyama_no_threshold` | info | The alloy has no published critical Niyama: the lowest value and where. | Compare the field with a sound casting of the alloy; read the hot spots. |
| `hand_check` | info | Chvorinov's rule for the whole casting's V/A against the simulation's last point, within 3 times. | Quote it as the check. |
| `hand_check_far` | warning | The two are more than 3 times apart. | Check the alloy, the mould and `h_W_m2K`; a part with one thick section in thin walls freezes later than its average modulus says, which is not an error. |
| `no_feeder` | info | No feeder named: every region that freezes last reads as unfed. | Name the gate or riser faces as `feeders` and check again. |
| `pure_metal` | info | A pure metal (fine silver): solved over 1 °C; Niyama means little for it. | Read the hot spots. |
| `not_solid` | warning | Not solid at the end (past `duration_s`, or 50 times the hand estimate): times to solid there are lower bounds. | A longer `duration_s`, a coarser mesh, or check the inputs. |
| `time_limit` | warning | It stopped at its time limit (twice `fit.seconds`, at least 30 s): nothing after is solved. | A larger `fit.seconds`, or a coarser mesh. |

## Hand checks

- **Chvorinov's rule, an insulating mould.** t = B (V/A)², B = (π/4) (ρ L' / (e ΔT))², with
  L' = L + c (T_pour - T_solidus) (the latent heat and everything above the solidus) and
  ΔT = (T_liquidus + T_solidus)/2 - T_mould [14]. A 15 mm cube of A356 in sand: V/A = 2.5 mm,
  L' = 425 + 0.963 × 160 = 579 kJ/kg, ΔT = 560 °C, B = 6.05 s/mm², t = 37.8 s; the solver reads
  37.3 s, and 149 s for a 30 mm cube (4.0 times: the square of the modulus). Steel conducts less
  well and reads about 20 % over the rule, which assumes the metal conducts without resistance.
- **A metal mould.** The contact and the metal's own conduction in series:
  t = (ρ L' / ΔT) ((V/A)/h + (V/A)² / (2k)). Between n = 1 (the contact controls, small sections)
  and n = 2 (the metal does). A die casting's skin cools well below the solidus, so the solver reads
  1.5 to 2 times this.
- **Feeders.** A riser feeds a section while it is still liquid: its modulus should be at least
  1.2 times the section's it feeds [18], and its own shrinkage volume more than the casting's
  (a few percent of the casting's volume for most alloys).
- **Thin sections.** A plate of thickness s in an insulating mould freezes in about B (s/2)²; a
  rod of diameter d in about B (d/4)².

## Limits

- The cavity starts full at the pour temperature: filling is not simulated (a thin section far
  from the gate freezes sooner than this says), nor is the metal's flow while it shrinks.
- The mould is a heat transfer coefficient to its temperature on every face (a sand or investment
  mould's falls as it heats), not meshed: a mould's re-entrant corners and thin cores, which heat
  through and slow the freezing beside them, are not seen, and a sand core inside a casting reads
  as cold as its outside.
- Constant properties; the liquid fraction falls straight from liquidus to solidus; one specific
  heat for liquid and solid; no undercooling.
- No gas porosity, hot tears, segregation or microstructure. Niyama marks where shrinkage porosity
  is likely, not how much; its threshold is published for few alloys.
- A named feeder is taken to stay liquid until the casting is solid; whether it does is the riser's
  own sizing ([Hand checks](#hand-checks)).

## When the model is big

Linear tetrahedra only (their lumped heat capacity keeps the enthalpy march monotone). Ladder:
`iterative` (multigrid-preconditioned CG instead of a factor) and `defeature`. The time step adapts
by itself (about a hundred steps from pour to solid). Like every march, it stops at its time limit
(twice `fit.seconds`, at least 30 s) where it has got to, and says so.

## Sources

1. CRC Handbook of Chemistry and Physics: the elements' densities, melting points, specific heats
   and heats of fusion (silver 11.28 kJ/mol, copper 13.26, gold 12.55, zinc 7.068, tin 7.15,
   aluminium 10.71, silicon 50.21, iron 13.81, chromium 21.0, nickel 17.48, molybdenum 37.48,
   manganese 12.91, lead 4.77 kJ/mol).
2. Cooksongold, 14ct AY properties sheet: density 13.0 g/cm³, melting range 830-870 °C, casting
   930-1020 °C, flask 600-650 °C.
3. Rio Grande, 18K yellow gold alloy (604700) tech sheet: density 15.3 g/cm³, solidus-liquidus
   860-900 °C, cast at about 1000 °C.
4. JETS, sterling casting grain (92.5 % silver, 7.5 % copper): solidus 810 °C, liquidus 892 °C,
   10.36 g/cm³.
5. Copper Development Association, alloy pages (alloys.copper.org), US units converted here:
   C90500 liquidus 1830 °F (999 °C), solidus 1570 °F (854 °C), specific gravity 8.72, conductivity
   43.2 Btu/(ft h °F) (74.8 W/(m K)), specific heat 0.09 Btu/(lb °F) (377 J/(kg K)); C87300 1780 °F
   (971 °C), 1510 °F (821 °C), 8.36, 16.4 (28.4), no specific heat; C85400 1725 °F (941 °C),
   1700 °F (927 °C), 8.44, 50.8 (87.9), 0.09; C65500 specific heat 0.09.
6. A356.0: density 2.685 g/cm³ and 151-152 W/(m K) (Key to Metals, A356.0, via materialhub.de);
   963 J/(kg K) and a melting range of 557-613 °C (Xometry, A356 datasheet). The 555/615 °C pair is
   one a published simulation of A356 uses; it was not checked against ASM Handbook Vol. 2.
   6b. Heraeus, AuAg20Cu10 (Hera 238) datasheet: 66 W/(m K) at 20 °C, 12.46-12.55 % IACS,
   15.03 g/cm³, 865-895 °C. The Lorenz number 2.1-2.9 × 10⁻⁸ W Ω/K²: Klotz, Tiberto and Held,
   "Additive manufacturing of 18-karat yellow-gold alloys", Santa Fe Symposium (2016).
7. NADCA, Product Specification Standards for Die Castings (2021), section 3: A380 (0.098 lb/in³,
   2.71 g/cm³; 1000-1100 °F, 538-593 °C; 55.6 Btu/(ft h °F), 96.2 W/(m K); 0.230 Btu/(lb °F),
   963 J/(kg K)); Zamak 3 (6.6 g/cm³, 718-728 °F, 381-387 °C, 113 W/(m K), 419 J/(kg K)). Nyrstar's
   Zamak datasheet (2020) gives the same 6.6 kg/dm³ and 381-387 °C.
8. ASM Handbook, Vol. 1: grey iron class 30 and ductile iron 65-45-12 (density, conductivity,
   specific heat; not rechecked here).
9. ASM Handbook, Vol. 1: carbon steel and type 316 (density, conductivity, specific heat; not
   rechecked here), for ASTM A216 WCB and A351 CF8M. 316's melting range 1375-1400 °C: ASM
   Specialty Handbook, Stainless Steels, as suppliers' datasheets reproduce it (Alloys
   International's 316 sheet); other datasheets give 1370-1400 and 1390-1440 °C.
10. Niyama, Uchida, Morikawa and Saito, "A method of shrinkage prediction and its application to
    steel casting practice", AFS International Cast Metals Journal 7 (1982) 52-63: about
    1 (°C·min)^½/cm, which is 0.775 (°C·s)^½/mm.
11. Carlson and Beckermann, "Use of the Niyama criterion to predict shrinkage-related leaks in
    high-nickel steel and nickel-based alloy castings", SFSA Technical and Operating Conference
    (2008): 1.0 (°C·s)^½/mm.
12. Bhoraniya, Dharaiya and Sata, "Application of Niyama criterion to predict shrinkage porosity in
    vertical centrifugal casting of ASTM A356 alloy", Int. J. Process Management and Benchmarking
    12 (2022) 395-406: a threshold of 0.20-0.30.
13. Carlson and Beckermann, "Prediction of shrinkage pore volume fraction using a dimensionless
    Niyama criterion", Metallurgical and Materials Transactions A 40 (2009) 163-175.
14. Chvorinov, Giesserei 27 (1940) 177-186; Flemings, Solidification Processing (McGraw-Hill,
    1974), chapter 1: the semi-infinite mould and B = (π/4) (ρ L' / (e ΔT))².
15. Donahue, Cleary, Hesterberg and Holmgren, US patent 5,355,931 (1994), Table I: silica sand
    0.61-0.90 W/(m K), 1500 kg/m³, 1130-1172 J/(kg K), heat diffusivity √(k ρ c) 1017-1258
    W s^½/(m² K).
16. Pehlke and Berry, "Investigation of heat transfer at the mold/metal interface in permanent
    mold casting of light alloys", final technical report, US DOE (2005), doi:10.2172/861448:
    reported coefficients 500-16,000 W/(m² K); Ho and Pehlke, "Metal-mold interfacial heat
    transfer", Metallurgical Transactions B 16 (1985) 585-594; Hamasaiid, Dargusch, Davidson,
    Tovar, Loulou, Rezaï-Aria and Dour, "Effect of mold coating materials and thickness on heat
    transfer in permanent mold casting of aluminum alloys", Metallurgical and Materials
    Transactions A 38 (2007) 1303-1316.
17. The pouring-time rules of gating design, t = K_f (1.41 + T/14.59) √W for grey iron up to
    450 kg (K_f the iron's spiral fluidity in inches over 40) and t = (2.4335 - 0.3953 log W) √W
    for steel, W in kg, t in s, as reproduced in gating-design course notes; their original
    handbook source was not checked.
18. Wlodawer, Directional Solidification of Steel Castings (Pergamon, 1966): the feeder's modulus
    at least 1.2 times the casting's.
19. Łągiewka, "Determination of thermophysical properties for selected molding sands", Acta
    Physica Polonica A 136 (2019) 992-995: measured 1141 (bentonite-bonded) and 1304 (oil-bonded)
    W s^½/(m² K); 793 and 1037 from handbook properties.
20. IES Virtual Environment, material database, "Table 6: thermal conductivity, specific heat
    capacity and density": dense plaster 0.50 W/(m K), 1300 kg/m³, 1000 J/(kg K); gypsum
    plastering 0.42, 1200, 837; plaster ceiling tiles 0.38, 1120, 840; gypsum plasterboard 0.16,
    950, 840 (building plasters, not a casting investment).
21. MIT OpenCourseWare 2.008, Design and Manufacturing II (spring 2025), lecture 21a, "Casting:
    solidification and cooling", after Flemings: h = 1000 W/(m² K) with a carbon coating, 5000
    under high pressure, 10,000 for a polished die.
22. Long, Thornhill, Armstrong and Watson, "Determination of the heat transfer coefficient at the
    metal-die interface for high pressure die cast AlSi9Cu3Fe", Applied Thermal Engineering 31
    (2011) 3996-4006: a peak of 42,000 W/(m² K).
23. Quested, Dinsdale, Robinson, Mills and Hunt, "The prediction of the thermophysical properties
    and the solidification path of commercial alloys", NPL Report CMMT(A)275 (2000): the enthalpy
    of fusion estimated as the liquidus times the mole-weighted sum of the elements' entropies of
    fusion (each element's heat of fusion over its melting point, from [1]).
24. Mills, Recommended Values of Thermophysical Properties for Selected Commercial Alloys
    (Woodhead and ASM, 2002), LM25 (A356): enthalpy of fusion 425 ± 5 J/g by DSC, solidus 567 °C,
    liquidus 614-615 °C (read through excerpts, not the book's page); Overfelt, Bakhtiyarov and
    Taylor, "Thermophysical properties of A201, A319, and A356 aluminium casting alloys", High
    Temperatures-High Pressures 34 (2002) 401-409: 424 kJ/kg by DSC for A356, as a later paper
    cites it.
25. US patent 8,950,465 (aluminium die-casting alloys and methods): a die cavity fills in 1-100 ms,
    thin-walled castings in 6-7 ms, medium and thick walls in 30-80 ms.
26. Shimizu and Nomura, "Die-cast Al-Si-Cu alloy (ADC12) as a phase change material for
    medium-high-temperature heat storage", Journal of Alloys and Compounds 1017 (2025) 179006:
    melts at 516-590 °C, latent heat 411.1 J/g.
27. Heraeus Electro-Nite, Thermal Analysis of Cast Iron (booklet after W. Van der Perre): the
    liquidus T_L = 1623.6 - 112.36 (C + Si/4 + P/2) °C; the iron-carbon diagram's stable eutectic
    at 1153 °C, the metastable at 1147 °C, and 1150 °C taken as the reference eutectic.
28. Carlson and Beckermann, "Sensitivity of steel casting simulation results to alloy property
    datasets", SFSA Technical and Operating Conference (2012), paper 5.3: the benchmark WCB
    dataset, liquidus 1502 °C, freezing range 91 °C, latent heat 180 kJ/kg; MAGMA's C19Mn5,
    1501 °C, 39 °C, 274 kJ/kg; CF8M's liquidus 1430 °C (a 1530 °C pour, 100 °C of superheat).
29. Pichler, Simonds, Sowards and Pottlacher, "Measurements of thermophysical properties of solid
    and liquid NIST SRM 316L stainless steel", Journal of Materials Science 55 (2020) 4081-4093:
    solidus 1675 K (1402 °C), liquidus 1708 K (1435 °C), latent heat 290 kJ/kg, 7904 kg/m³.
