# examples models

Standalone demo parts as one cad-project: every script directly under
`src/` is runnable and its artifact lands in a format folder at the project
root (`STEP/`, `STL/`, `3MF/`, `GLB/`, `PDF/`). The `*_drawing.py` scripts are
`@eng_drawing` documents over the part beside them, which is why each imports
that model's constants; the rest are part models. Assemblies live in the
sibling `models/assemblies/` project (one group per assembly) and 2D drawings
in `models/drawings/`. The `src/` tree is committed; build the outputs you need.

```bash
python models/examples/src/mounting_plate.py     # one model
ls models/examples/src/*.py | xargs -n1 -P4 python   # every part
```

Unchanged models are no-ops, so "build if missing" and "rebuild" are the same
command. Shared helper modules live in `src/lib/` (`part_common`,
`simple_model_library`) — plain modules, never models.
Because the scripts sit directly in `src/`, `from lib import ...` resolves with
no path setup.

A handful of models declare mesh exports so the STL/3MF/GLB doors have real
fixtures to work against.

### Parts

| Script | Artifact | Description |
|--------|----------|-------------|
| `angle_bracket.py` | `STEP/angle_bracket.step` | Base plate with a tab leaning 30 degrees, a hole square through the tab |
| `angle_bracket_drawing.py` | `PDF/angle_bracket_drawing.pdf` | **Engineering drawing** of the bracket: an auxiliary view (VIEW C) square onto the inclined tab, its hole called out there; the sheet chooses its own size and scale. Run the model above first. |
| `basic_shape_mating_test_fixture.py` | `STEP/basic_shape_mating_test_fixture.step + 3MF/basic_shape_mating_test_fixture.3mf` | Primitive-shape mating fixture (box/cone/sphere/cylinder on a base plate) |
| `cam_follower_roller.py` | `STEP/cam_follower_roller.step` | Cam follower roller with central bearing bore and rounded outer profile |
| `centrifugal_impeller.py` | `STEP/centrifugal_impeller.step` | Single solid centrifugal impeller |
| `circular_flange.py` | `STEP/circular_flange.step` | Circular flange model |
| `circular_flange_drawing.py` | `PDF/circular_flange_drawing.pdf` | **Engineering drawing** of the flange on A4: the bolt circle (count, size and pitch circle) and bore called out from the part, a section through the holes, the edge radius called out where the section shows it. Run the model above first. |
| `clevis_bracket_lightening_cutouts.py` | `STEP/clevis_bracket_lightening_cutouts.step` | Clevis bracket model |
| `cylindrical_cap.py` | `STEP/cylindrical_cap.step` | Cylindrical cap with hollow interior, top boss, and rounded external edges |
| `cylindrical_spacer_sleeve.py` | `STEP/cylindrical_spacer_sleeve.step` | Cylindrical spacer sleeve with a central through-bore and rounded rim edges |
| `electronics_enclosure_base.py` | `STEP/electronics_enclosure_base.step` | Single solid open-top electronics enclosure base |
| `electronics_enclosure_base_drawing.py` | `PDF/electronics_enclosure_base_drawing.pdf` | **Engineering drawing** (`@eng_drawing`) of that part: a section through the standoffs, measured dimensions, hole and boss callouts read off the part, title block. Run the model above first. |
| `flywheel_disk.py` | `STEP/flywheel_disk.step` | Flywheel disk with central bore, annular rim, and lightening holes |
| `guide_bar.py` | `STEP/guide_bar.step` | 600 mm round bar with an end spigot, a cross hole near each end and a chamfered end |
| `guide_bar_drawing.py` | `PDF/guide_bar_drawing.pdf` | **Engineering drawing** of the bar: front and top views broken, the overall length still stated true, diameters on the profile, the end chamfer called out. Run the model above first. |
| `gusset_plate.py` | `STEP/gusset_plate.step` | Gusset plate with a triangular web, base holes, and softened perimeter edges |
| `keyed_shaft_hub.py` | `STEP/keyed_shaft_hub.step` | Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern |
| `l_bracket.py` | `STEP/l_bracket.step` | L-bracket model |
| `l_bracket_drawing.py` | `PDF/l_bracket_drawing.pdf` | **Engineering drawing** of the bracket: both hole patterns called out in the views that look down them, plate and gusset sizes. Run the model above first. |
| `mounting_plate.py` | `STEP/mounting_plate.step + STL/mounting_plate.stl, 3MF/mounting_plate.3mf, GLB/mounting_plate.glb` | Mounting plate with central circular cutout, elongated side slot, four corner holes, and rounded edges |
| `mounting_plate_drawing.py` | `PDF/mounting_plate_drawing.pdf` | **Engineering drawing** of the plate: its holes and slot called out from the part, the hole pitch, the slot's position and the corner radius. Run the model above first. |
| `open_top_electronics_enclosure.py` | `STEP/open_top_electronics_enclosure.step` | Open-top electronics enclosure model |
| `perforated_plate.py` | `STEP/perforated_plate.step` | Plate with two rows of holes, dowel holes, a bore, a slot and rounded corners |
| `perforated_plate_drawing.py` | `PDF/perforated_plate_drawing.pdf` | **Engineering drawing** of the plate: a hole table (each hole and the slot tagged, positioned from the corner, sized from the part), the corner radius called out. Run the model above first. |
| `print_in_place_hinge.py` | `STEP/print_in_place_hinge.step` | Print-in-place barrel hinge for FDM printing |
| `print_in_place_multi_pivot_phone_holder.py` | `STEP/print_in_place_multi_pivot_phone_holder.step` | Print-in-place multi-pivot holder with a phone/tablet cradle for FDM printing |
| `pulley_wheel.py` | `STEP/pulley_wheel.step` | Pulley wheel with a central hub, outer groove, and circular through-bore |
| `radial_engine_cylinder.py` | `STEP/radial_engine_cylinder.step` | Radial-engine-style cylinder model |
| `rectangular_calibration_block.py` | `STEP/rectangular_calibration_block.step` | Rectangular calibration block model |
| `rectangular_clamp_block.py` | `STEP/rectangular_clamp_block.step` | Rectangular clamp block with a split slot and two transverse screw holes |
| `retainer_plate.py` | `STEP/retainer_plate.step` | Retainer plate with elongated slot, two circular holes, and chamfered perimeter |
| `shaft_collar.py` | `STEP/shaft_collar.step` | Shaft collar with a central bore, radial set-screw hole, and chamfered faces |
| `small_enclosure_cover.py` | `STEP/small_enclosure_cover.step` | Small enclosure cover with raised rim, corner screw holes, and shallow recessed center |
| `spur_gear_blank.py` | `STEP/spur_gear_blank.step + STL/spur_gear_blank.stl, 3MF/spur_gear_blank.3mf, GLB/spur_gear_blank.glb` | Spur gear blank with central bore, raised hub, and simplified perimeter teeth |
| `square_mounting_block.py` | `STEP/square_mounting_block.step` | Square mounting block with a vertical through-hole and two side clearance holes |
| `stepped_shaft_keyway.py` | `STEP/stepped_shaft_keyway.step` | Stepped shaft with keyway model |
| `stepped_shaft_keyway_drawing.py` | `PDF/stepped_shaft_keyway_drawing.pdf` | **Engineering drawing** of the shaft: diameters on the profile, the keyway located, a section through it, a 5:1 detail of the end chamfer. Run the model above first. |
| `t_slot_slider_block.py` | `STEP/t_slot_slider_block.step` | T-slot slider block with central channel, side relief cuts, and mounting holes |

Build: `python src/<script>` per row; unchanged models are no-ops.
