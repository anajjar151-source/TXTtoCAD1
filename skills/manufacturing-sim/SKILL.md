---
name: manufacturing-sim
description: Check how a part fares while it is made by simulating its process with cadgen - casting (sand, investment and lost-wax jewellery, permanent mould, die), injection moulding, heat treatment and quenching, 3D printing (FDM, resin, SLS, metal powder bed), CNC milling and turning, welding and sheet metal bending - with labelled hand estimates for reflow soldering, forging, extrusion and deep drawing. Each check ends on a verdict and the fix for every problem, so a design is checked, fixed and checked again as CI checks code. Use when the user asks whether a part will cast or fill, where shrinkage or porosity forms, how long it takes to freeze or cool, whether it will sink, warp or curl, harden or crack in the quench, deflect or chatter when machined, distort when welded, spring back or crack when bent, or how hot its parts get through a reflow oven.
license: MIT
---

# Manufacturing simulation: what happens to the part while it is made

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the repository link is only for
provenance and release review.

Use this skill for questions about a process rather than about the finished part in service: will
it cast soundly, will it sink or warp when moulded, will the core harden in the quench, will it
curl off the plate when printed, will the wall chatter under the cutter, will the weldment stay
square, will it spring back or crack when bent. It is a router: [Choose the
process](#choose-the-process) maps the user's question to a process and its reference page.

Seven processes run today, each as `cadgen manufacturing check` with a study that names its
`process`: `casting`, `molding`, `heat_treatment`, `printing`, `machining`, `welding` and
`sheet_metal`. The check meshes the saved STEP, simulates the part being made on the same mesher and
solvers `$fea` uses, and writes a result the Viewer draws beside a sidecar with every number. Its
findings read as a CI check: each says what it measured against its limit, passes included, and
each error and warning carries the fix that makes it pass; the verdict is ready or fix, and
`--fail-on error` makes a failing check exit 3. [checks.md](references/checks.md) lists every
check, its severity and its fixes. Each simulation is lite (its reference says what it leaves out)
and sheet metal is an estimate by hand formulas: say so when you report. Reflow soldering and
forming get honest hand estimates, labelled as such, from [estimates.md](references/estimates.md).

## Choose the process

Match the user's question to a row first. Only a **Runs today** row runs in cadgen; one whose
status says estimate runs hand formulas on the part, not a simulation.

| The user asks | `process` | Plain word | Status | Reference |
| --- | --- | --- | --- | --- |
| "Will it cast", "where will it shrink or be porous", "will this 1 mm frame fill", "how long until it is solid", "where do I put the riser or the sprue": sand, investment (lost-wax jewellery), permanent mould or die casting | `casting` | Casting | **Runs today** (lite: the cavity starts full, the mould is a heat transfer coefficient, no shrinkage flow or microstructure; `cadgen manufacturing check part.step --study part.casting.json`) | [casting.md](references/casting.md) |
| Injection moulding: "how long to cool", "will it sink", "will it warp", "is this wall too thin or too thick for the resin", "will it fill" | `molding` | Injection molding | **Runs today** (lite: the cavity starts full and packed, no fill or pack; the mould is a heat transfer coefficient; the warp is an estimate from cadgen's own shrinkage model, not a published law; `cadgen manufacturing check part.step --study part.molding.json`) | [molding.md](references/molding.md); its hand check, [estimates.md](references/estimates.md#injection-moulding) |
| Heat treatment and quenching: "how hard will it be", "will the core harden", "will it crack or distort in the quench", "oil or water" | `heat_treatment` | Heat treatment | **Runs today** (lite: thermal only, no transformation; a constant h per quenchant; hardness through the grade's Jominy curve; elastic stress at the largest gradient; `cadgen manufacturing check part.step --study part.heat_treatment.json`) | [heat-treatment.md](references/heat-treatment.md) |
| 3D printing (FDM, resin, SLS/MJF, metal powder bed): "will it warp or curl", "will the corners lift", "how much does it move off the plate", "residual stress", "will the recoater hit it" | `printing` | 3D printing | **Runs today** (lite: layers lumped into bands of one inherent strain each, linear elastic, a rigid plate; no thermal history, no supports; printability is `$dfam-check`'s; `cadgen manufacturing check part.step --study part.printing.json`) | [printing.md](references/printing.md); by hand: [estimates.md](references/estimates.md#3d-printing) |
| CNC machining: "will this thin wall deflect under the cutter or the clamp", "will it chatter", "which spindle speeds are chatter-free", milling or turning | `machining` | Machining | **Runs today** (lite: Kienzle's force at the most flexible point of the cut faces, only the part flexes, zero-order lobes along the face's normal; `cadgen manufacturing check part.step --study part.machining.json`) | [machining.md](references/machining.md) |
| Welding: "how much will it distort", "how far will the joint close", "will it bow", "residual stress at the weld" | `welding` | Welding | **Runs today** (lite: each weld's zone an inherent strain from its heat input by the classical relations, all welds at once, linear elastic; no sequence or clamping; `cadgen manufacturing check part.step --study part.welding.json`) | [welding.md](references/welding.md); by hand: [estimates.md](references/estimates.md#welding) |
| Sheet metal bending: "how much will it spring back", "what overbend", "will it crack at this bend", the bend allowance | `sheet_metal` | Sheet metal | **Runs today** (estimate: per bend from the STEP by hand formulas, Gardiner's springback, the outer strain against the minimum R/t, DIN 6935's K-factor; no forming simulation; bend rules are `$dfm`'s; `cadgen manufacturing check part.step --study part.sheet_metal.json`) | [sheet_metal.md](references/sheet_metal.md) |
| Reflow soldering of a board: "how hot do the parts get through the profile", "is the big connector above liquidus long enough" | none yet | Reflow | **Estimate** (the temperatures run today in `$fea` as heat over time with the oven's profile; no solder flow) | [estimates.md](references/estimates.md#reflow-soldering) |
| Forging, extrusion and deep drawing: "what press force", "will the die fill" | none yet | Forming | **Estimate** (slab-method forging load, extrusion pressure, deep-drawing force by hand; no die fill) | [estimates.md](references/estimates.md#forging-extrusion-and-deep-drawing) |

A test keeps this table's **Runs today** rows in step with the processes cadgen checks.

### When the process is an estimate

- Say "estimate" every time you quote one, and give its assumptions and its source with the
  number. Never pass an estimate off as a simulation, or a simulation of something else (a static
  stress, a temperature) off as the process's.
- Say plainly what is not in this version, in the user's words: "a mould filling simulation is not
  in this version".
- Where `$fea` honestly answers part of the question, offer it and say which part: a reflow oven's
  temperatures over time are `thermal_transient`. Each estimate in
  [estimates.md](references/estimates.md) says how to set that study up.
- Geometry rules (draft, rib to wall ratios, bend reliefs, overhangs) are `$dfm`'s and
  `$dfam-check`'s: send the user there for a review rather than restating them.

## Say what the run did

- **Lite limits.** Every result carries what its simulation leaves out: the `lite:` lines of the
  command's output (`estimate:` for sheet metal), the sidecar's `limits`. Quote them whenever you
  quote its numbers.
- **The process's own cautions.** Each reference's Limits say what to warn about: a casting's
  instant fill makes a thin section look better than it is, and its feeders are taken to stay
  liquid; a moulding's warp is an estimate from cadgen's own model, not a published law; a print's strain is lumped into bands. Say so.
- **Values it estimated.** A fill time from the mass, a tolerance from ISO 2768, a cutting force or
  a Jominy curve that is an estimate: the result says so in a finding. Say it was estimated, and
  ask for the real one when the answer depends on it.
- **Adapted steps.** As in `$fea`: report every `adapted:` line and `fit_` finding.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/). `cadgen fea faces` shares one installation
with the `$cad` skill and the CAD app's server; `cadgen manufacturing check` needs the `fea` extra,
so it runs from its own installation, made the first time it is needed (below):

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.21 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.21 python`

Checking needs cadgen's opt-in `fea` extra (the mesher and the solver). The first time a check runs,
`cadgen manufacturing check` fails with "cadgen's fea extra is not installed"; that is a missing
install, not a modelling error. Run the same command with the extra in the requirement, and keep
using that form for `manufacturing check` from then on (the first run downloads the mesher and
solver; later runs reuse them):

```bash
uvx --no-config --managed-python --python 3.13 --from "cadgen[fea]==0.7.21" cadgen manufacturing check part.step --study part.casting.json
```

Units: mm for geometry, °C for temperatures, s for times, W/(m² K) for a heat transfer coefficient,
rpm for a spindle, kJ/mm for a weld's heat input.

## Workflow

1. **List the faces** the study names, if it names any (a casting's feeders, a cut's faces and the
   faces held, a weld's faces, a sheet's held flat). Prefer faces the user selected in the Viewer
   (`part.step#o1.f12`); otherwise list them and match by description.

   ```bash
   cadgen fea faces part.step
   ```

2. **Write the study** as `part.<process>.json` beside the part, from the process's reference page.
   A casting of a silver pendant, `part.casting.json`:

   ```json
   {"process": "casting", "alloy": "sterling-silver-925", "mold": "investment",
    "feeders": [{"faces": ["#o1.f12"]}], "fill_time_s": 0.5}
   ```

   Every study names its `process`; the rest is that process's own keys (here the alloy, its mould,
   the feeders and the fill time), and the user's own numbers override the defaults when they know
   them (a jeweller's flask temperature, a foundry's pour temperature). Leave `mesh` out on the
   first run.

3. **Check.**

   ```bash
   cadgen manufacturing check part.step --study part.casting.json --fail-on error
   ```

   This writes `part.casting.glb` (the casting coloured by the time to fully solid: the last to
   freeze is red) and `part.casting.result.json` (the verdict, every finding and number, the study, the
   mesh and timings) beside the part, replacing an earlier check's. Progress lines print to stderr;
   `--json` prints the result as one JSON line. It exits 0 when the verdict passes the gate, 3 when it
   ran and an error stands, and 1 when it could not run: a study with an unknown key, an unknown
   alloy or a pour below the liquidus is refused with a message naming the field, and nothing is
   left beside the part.

4. **Read the findings**: the lines end on the checklist and the verdict
   ([checks.md](references/checks.md)), and the process's reference says what each means.

5. **Report**: the verdict and its headline; each FAIL and WARN with where it is and its fix; the
   numbers the user asked about, from the summary; the hand check; the limits. Show the result GLB
   with `$cad` (its Show the model step), beside the STEP: each process opens on what it judges, and
   one that changes over time (a freeze, a quench, a build) plays it.

## Check, fix, check again

A check is a gate on the design, as CI is on code: when the user wants a part that can be made,
fix what it finds and run it again until it passes, then tell the user what changed.

1. **Run it** with the gate (Workflow step 3). It exits 3 while the verdict fails `--fail-on
   error`, and its lines end on a checklist, failures first, then the verdict:

   ```text
   FAIL  shrinkage_hot_spot  liquid cut off: 6667 mm³, needs below 15.9 mm³; at [50.263, -1.105, 14.134] mm; fix: Feed it from #o1.f7: ...
   WARN  low_niyama          lowest Niyama: 0.044 (°C·s)^½/mm, needs above 0.3 (°C·s)^½/mm; at [49.665, 1.287, 12.304] mm; fix: ...
   PASS  thinnest_section    section solid through: 20.8 s, needs above 0.876 s; at #o1.f5 [0.667, -4.333, 3.0] mm
   PASS  hand_check          simulation against the rule: 1.11×, needs below 3×
   Verdict: 1 to fix · shrinkage hot spot · 1 failed, 1 warning, 2 passed; fails --fail-on error
   ```

2. **Read the verdict and every fix** from the sidecar (`part.casting.result.json`): `verdict.status` is
   `ready` (no error) or `fix`. Each error and warning carries `measured` (its `value` against its
   `limit`, `units`, `pass_when`) and `fix`: `action`, `where` (face refs or points), `params` (the
   target values), `summary`, and `alternatives` for when the first cannot be made.
3. **Make the fix** its `action` names, by who makes it ([checks.md](references/checks.md#the-fix-actions)):
   - the model (`thicken`, `thin`, `add_rib`, `add_fillet`, `add_relief`, a bend's radius): change
     the model script with `$cad` to `params`, and rebuild the STEP;
   - the study's own settings (`add_feeder`, `enlarge_feeder`, `set_duration`, a mesh, a time
     limit, `check_inputs`): change the study;
   - the user's process choices (a mould or melt temperature, a steel or quenchant, a depth of cut
     or spindle speed, a chamber temperature, a build direction, a weld's heat input): ask first;
   - the shop's (a chill, a gate, support, stress relief, a brim, an overbend, a test bend): tell
     the user what and where; the run does not model it, so the finding stays.

   Never change the alloy, the material, the resin, the steel or the user's tolerances to clear a
   finding: they are the user's.
4. **Rebuild and run again** until the command exits 0 (the verdict is `ready`), weighing each
   warning left. After three rounds that do not converge, stop and ask the user.
5. **Report the checklist**: each FAIL and WARN with the fix made, the PASS lines, the verdict and
   the limits.
