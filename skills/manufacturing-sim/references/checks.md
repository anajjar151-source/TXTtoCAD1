# The verdict and the checks

Every `cadgen manufacturing check` runs every check its process makes and gives one verdict, the
sidecar's `verdict` and the last line of the command's output:

- **Ready** (`verdict.status` `ready`): no check found an error. Warnings may remain: weigh each.
  The headline says what the process says ("Ready to cast · solid in 41 s", "Ready to cut · 0.0185
  mm under the cut").
- **N to fix** (`fix`): N errors, each kind named once ("1 to fix · shrinkage hot spot").

`--fail-on error` makes a check that ran and found an error exit 3, as a failing CI check does;
`--fail-on warning` fails on a warning too. Exit 1 means the check did not run (a study it refused,
a part it could not read), and then nothing is beside the part: an earlier check's result is
removed before each run.

Each finding is one object in the result's `findings` (and one line of the command's output):
`check` (the process, or `fea` for the run's own), `severity` (`error`, `warning` or `info`),
`type` (the kind, below), `summary` (one plain sentence), `description`, `items` (where: a face
`ref` and the point `at` in part mm), `measured` (its `value` against its `limit`, `units`,
`pass_when` `below` or `above`, and the `quantity` it is) and `fix` (`action`, `summary`, `where`:
face refs or points, `params`: the target values, and `alternatives` of the same shape, in order of
preference). An `info` with `measured` is a check that passed; one without is a note. The command's
lines end on a checklist, failures first (`FAIL`, `WARN`, `PASS`: the type, what it measured
against its limit, where, and the fix), then the verdict.

The `type`s are a closed set, so an agent can act on one by name; so are the fix actions each can
carry. A test keeps the tables below in step with cadgen.

## The fix actions

Where each action changes, so you know who makes it:

- **The model** (change the model script with `$cad` and rebuild the STEP): `thicken`, `thin`,
  `add_rib`, `add_fillet`, `add_relief`, `extend_bend`, `increase_radius`, `reduce_radius`,
  `set_thickness`.
- **The study, the run's own settings** (change them freely): `add_feeder` and `enlarge_feeder` (the
  study's `feeders`; the riser it needs is in `params`, modelled only if the user wants the gating in
  the model), `set_duration`, `coarsen_mesh`, `refine_mesh`, `raise_time_limit`, `check_inputs`
  (compare the inputs with what the shop really uses), `set_study_thickness`.
- **The study, the user's choices** (ask before you change them: they are the shop's process, not
  the part): `raise_mold_temperature`, `change_process`, `change_material`, `change_quenchant`,
  `reduce_depth`, `change_speed`, `raise_chamber_temperature`, `change_orientation`,
  `reduce_heat_input`.
- **The shop** (nothing in the model or the study changes: tell the user what to do and where):
  `add_chill`, `move_gate`, `support`, `rough_before_finishing`, `stress_relieve`, `add_brim`,
  `balance_welds`, `preset`, `overbend`, `test_bend`, `form_in_die`, `turn_blank`, `softer_temper`.

## `casting`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `misrun` | error | a section is solid through before the mould has filled: a misrun or cold shut | `thicken`, `raise_mold_temperature`, `move_gate` |
| `misrun_risk` | warning | a section is solid within 3 times the fill time | `thicken`, `raise_mold_temperature`, `move_gate` |
| `thinnest_section` | info | the thinnest section stays liquid 3 times the fill time or more | none (a pass) |
| `shrinkage_hot_spot` | error | a region freezing after everything around it is cut off from every feeder (with none named, the region that freezes last): shrinkage porosity | `add_feeder`, `enlarge_feeder`, `thin`, `add_chill` |
| `no_hot_spot` | info | it freezes toward its feeders: no liquid pocket is cut off from them | none (a pass) |
| `low_niyama` | warning | Niyama under the alloy's critical value: porosity likely | `add_feeder`, `enlarge_feeder`, `add_chill` |
| `niyama_ok` | info | Niyama stays at the alloy's critical value or above | none (a pass) |
| `niyama_no_threshold` | info | the alloy has no published critical Niyama: the lowest and where | none (a note) |
| `hand_check` | info | Chvorinov's rule for the casting's V/A against the simulation, within 3 times | none (a pass) |
| `hand_check_far` | warning | the two more than 3 times apart | `check_inputs` |
| `not_solid` | warning | not solid at the end of the run | `set_duration`, `coarsen_mesh` |
| `no_feeder` | info | no feeder named: every region that freezes last reads as unfed | none (a note) |
| `pure_metal` | info | a pure metal, solved over 1 °C: Niyama means little for it | none (a note) |

## `molding`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `cooling_time` | info | when every point is below the ejection temperature, and where it is last | none (a note) |
| `not_ejectable` | warning | not ejectable everywhere at the end of the run | `check_inputs` |
| `sink_void` | error | a section stays hot 3 times as long as the nominal wall or more: a sink mark or a void | `thin` |
| `sink_risk` | warning | a section stays hot 1.2 times as long or more: a sink mark opposite it | `thin` |
| `no_sink` | info | no section stays hot that long | none (a pass) |
| `thin_wall` | warning | the thinnest wall is under the resin's range: a short shot | `thicken` |
| `thinnest_wall` | info | the thinnest wall is within the resin's range | none (a pass) |
| `thick_wall` | warning | the thickest section is over the resin's range | `thin` |
| `thickest_wall` | info | the thickest section is within the resin's range | none (a pass) |
| `warp` | info | the warp, an estimate, with no `warp_tolerance_mm` to judge it by | none (a note) |
| `warp_over_tolerance` | error | the warp estimate is over `warp_tolerance_mm` | `thin` |
| `warp_within_tolerance` | info | the warp estimate is within `warp_tolerance_mm` | none (a pass) |
| `melt_window` | info | the melt is within the resin's processing window | none (a pass) |
| `melt_outside_window` | warning | the melt is outside it | `change_process` |
| `mold_window` | info | the mould is within the resin's processing window | none (a pass) |
| `mold_outside_window` | warning | the mould is outside it | `change_process` |
| `mesh_across_wall` | info | about 3 elements or more across the nominal wall | none (a pass) |
| `coarse_mesh` | warning | fewer (under 2.7): the wall's middle cools too slowly | `refine_mesh` |
| `hand_check` | info | the plate formula for the thickest wall against the simulation, within 3 times | none (a pass) |
| `hand_check_far` | warning | the two more than 3 times apart | `check_inputs` |
| `fibre_filled` | info | a glass-filled resin shrinks less along the flow, which the warp estimate does not see | none (a note) |

## `heat_treatment`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `hardness` | info | the hardness as quenched at the surface and the core | none (a note) |
| `target_hardness` | info | the surface reaches `target_hrc` everywhere, and how deep | none (a pass) |
| `soft_spot` | error | a surface point under `target_hrc` | `change_material`, `change_quenchant`, `thin` |
| `quench_stress` | info | the quench's tension stays under the hot strength: it does not yield | none (a pass) |
| `quench_yield` | warning | the quench's tension passes the hot strength: residual stress and distortion stay | `change_quenchant` |
| `crack_risk` | info or warning | a sharp edge pulled past its strength as it turns to martensite (info: none is) | `add_fillet` |
| `distortion` | info or warning | the distortion at the largest spread (warning: it yields, so part of it stays) | `change_quenchant` |
| `section_change` | info or warning | a thick section beside a thin one, more than 3 times as thick (info: none is) | `thin` |
| `hand_check` | info | the series solution's centre cooling rate against the simulation's | none (a pass) |
| `hand_check_far` | warning | the two further apart than the hand check allows | `refine_mesh` |
| `not_cooled` | warning | not cooled through at the end of the run | `check_inputs`, `coarsen_mesh` |
| `beyond_jominy` | info | part of it cools slower than the grade's Jominy curve reaches | none (a note) |
| `estimated_curve` | info | the grade's Jominy curve is an estimate | none (a note) |
| `core_only` | info | a carburising grade: the core's hardness, not the case's | none (a note) |

## `machining`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `deflection_within_tolerance` | info | the part moves under half the tolerance under the cut | none (a pass) |
| `deflection_close_to_tolerance` | warning | it moves over half the tolerance | `reduce_depth`, `support` |
| `deflection_over_tolerance` | error | it moves more than the tolerance: the face is cut out of tolerance | `reduce_depth`, `support` |
| `thin_wall_too_flexible` | warning or error | a thin wall too flexible for the cut, and how much stiffer it must be (as its deflection is) | `thicken`, `rough_before_finishing`, `support` |
| `slender_part_too_flexible` | warning or error | a slender turned part too flexible for the cut (as its deflection is) | `support`, `thicken` |
| `clamp_stress_ok` | info | the cut's stress keeps the study's margin under yield | none (a pass) |
| `clamp_stress_close` | warning | the safety factor is under the margin | `reduce_depth`, `support` |
| `yields_under_cut` | error | it yields under the cut | `reduce_depth`, `support` |
| `chatter_stable` | info | the depth is under 0.8 of the chatter limit at the spindle speed | none (a pass) |
| `chatter_close` | warning | the depth is within 20 % of the chatter limit | `reduce_depth`, `change_speed` |
| `chatter` | error | the depth is past the chatter limit: it chatters | `reduce_depth`, `change_speed` |
| `hand_check` | info | Tlusty's one-mode limit against the lobes' lowest | none (a note) |
| `cutting_force_estimated` | info | the material has no published Kienzle values: its force is an estimate | none (a note) |
| `default_tolerance` | info | no `tolerance_mm`: judged against ISO 2768-1 fine | none (a note) |

## `printing`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `warp` | info or error | the bottom's flatness off the plate against the tolerance | `raise_chamber_temperature`, `change_orientation`, `stress_relieve`, `add_rib` |
| `release_distortion` | info or error | the distortion off the plate against the tolerance | `raise_chamber_temperature`, `change_orientation`, `stress_relieve`, `add_rib` |
| `distortion` | info or error | the distortion as printed (left on the plate) against the tolerance | `raise_chamber_temperature`, `change_orientation`, `stress_relieve`, `add_rib` |
| `residual_stress` | info or warning | the residual stress against yield | `stress_relieve`, `raise_chamber_temperature`, `change_orientation` |
| `recoater_collision` | info or warning | a band's top rising past the layer: the recoater may hit it | `support` |
| `bed_adhesion` | info or warning | the plate's pull on the bottom against `bed_adhesion_MPa` (FDM; info with none given) | `add_brim` |
| `starts_in_air` | info | regions that start in mid-air, held where they start | none (a note) |
| `sls_no_build_shrinkage` | info | SLS: nothing shrinks in the build | none (a note) |
| `hand_check` | info | the first band against a band fully held on the plate | none (a pass) |
| `hand_check_far` | warning | the two further apart than the hand check allows | `check_inputs` |

## `welding`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `distortion` | info or error | the welds' distortion against the tolerance | `reduce_heat_input`, `balance_welds`, `preset`, `thicken` |
| `angular_distortion` | info | each weld's angular distortion | none (a note) |
| `bowing` | info or warning | the bow along the longest-bowing weld against beam theory (or, too small to tell, the tolerance) | `check_inputs` |
| `residual_stress` | info or warning | the tension along the welds against 80 % of yield, judged when `fatigue_critical` | `stress_relieve` |
| `hand_check` | info | each joint's angle against Satoh and Terasaki's, within 2 times | none (a pass) |
| `hand_check_far` | warning | the two more than 2 times apart | `check_inputs` |

## `sheet_metal`

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `bend_may_crack` | error | a bend's outer strain past what its minimum R/t allows | `increase_radius`, `turn_blank`, `softer_temper` |
| `bend_formable` | info | a bend's outer strain within it | none (a pass) |
| `bend_takes_no_set` | error | a bend too gentle to yield through: it springs back flat | `reduce_radius`, `form_in_die` |
| `springback_over_tolerance` | warning | a bend's springback past `tolerance_deg`: overbend it | `overbend` |
| `springback_within_tolerance` | info | a bend's springback within it | none (a pass) |
| `springback_work_hardening` | warning | with work hardening, a bend Gardiner passes springs back past the tolerance | `test_bend` |
| `springback_work_hardening_within_tolerance` | info | with work hardening every bend stays within it | none (a pass) |
| `angle_error_over_tolerance` | warning | the far flat ends past the tolerance off its CAD angle | `overbend` |
| `angle_error_within_tolerance` | info | the far flat ends within it | none (a pass) |
| `relief_missing` | warning | a bend ends inside a flat with no relief cut | `add_relief`, `extend_bend` |
| `reliefs` | info | every bend ends at an edge or a relief | none (a pass) |
| `thickness_differs` | warning | the study's `thickness_mm` is not the part's | `set_thickness`, `set_study_thickness` |
| `thickness_matches` | info | it is | none (a pass) |
| `bend_closes_loop` | info | a bend closes a loop of flats: its springback is not solved | none (a note) |
| `sheet_metal_estimate` | info | this is an estimate by hand formulas, not a forming simulation | none (a note) |

## `fea`

The run's own findings, whatever the process: what fea's pipeline adapted or where it stopped.

| `type` | severity | what it checks | fix actions |
| --- | --- | --- | --- |
| `time_limit` | warning | a march (casting, molding, heat treatment) stopped at its time limit: nothing after is solved | `raise_time_limit` |
| `fit_iterative` | info | it solved with an iterative solver to fit its memory or time | none (a note) |
| `fit_defeature` | info | it left small features out of the mesh to fit | none (a note) |
| `fit_linear_elements` | info | it meshed with linear elements to fit | none (a note) |
| `fit_budget` | info | it did not fit the budget, or did not re-solve finer to stay in it | none (a note) |
