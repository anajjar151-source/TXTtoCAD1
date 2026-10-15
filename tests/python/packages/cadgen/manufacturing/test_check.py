"""``cadgen manufacturing check``: one door per question, the closed set of what each process finds, and the skill.

- fea's registry holds no process, and naming one as fea's ``analysis`` is refused in a sentence that names
  ``cadgen manufacturing check``; a manufacturing study names its ``process``, never an ``analysis``;
- every process is registered with its class, imports stdlib-only, and makes only the findings ``FINDING_TYPES`` lists
  (law 9): a type, a severity or a fix action outside it is refused where it is made;
- the skill's checks.md lists every check and finding type with its severity and fix actions, each process's reference
  lists its findings at their severities, and the router runs each process today with its command.

Stdlib only: nothing here meshes or solves (each process's own suite does, and casting's runs the CLI's gate).
"""

from __future__ import annotations

import re
import unittest

from tests.python.support.fea_fixtures import heavy_at_import, read_study, value_error
from tests.python.support.paths import REPO_ROOT

from cadgen._internal.manufacturing.processes import PROCESS_NAMES, REGISTRY, get_process
from cadgen._internal.manufacturing.processes.base import FINDING_TYPES, RUN, closed, finding_of

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
#: Each process's reference page.
PAGES = {"casting": "casting.md", "molding": "molding.md", "heat_treatment": "heat-treatment.md",
         "machining": "machining.md", "printing": "printing.md", "welding": "welding.md", "sheet_metal": "sheet_metal.md"}


def rows(path, heading: str) -> list[list[str]]:
    """The cells of each row of the first table under ``heading``, past its header."""
    text = path.read_text(encoding="utf-8")
    section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
    return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]


def severities(cell: str) -> set[str]:
    return set(re.findall(r"\b(error|warning|info)\b", cell))


class OneDoor(unittest.TestCase):
    def test_fea_holds_no_process_and_refuses_one_naming_the_manufacturing_check(self):
        from cadgen._internal.fea.analyses import REGISTRY as FEA
        from cadgen._internal.fea.study import parse_study

        self.assertEqual(sorted(set(FEA) & set(PROCESS_NAMES)), [])
        for name in PROCESS_NAMES:
            with self.subTest(process=name):
                message = value_error(self, parse_study, {"analysis": name})
                self.assertIn(f"'{name}' is a manufacturing process", message)
                self.assertIn("cadgen manufacturing check", message)

    def test_a_manufacturing_study_names_its_process_and_never_an_analysis(self):
        self.assertIn("study.process: the process to check, one of casting, molding", value_error(self, read_study, {}))
        self.assertIn('names its process with "process"',
                      value_error(self, read_study, {"analysis": "static", "process": "casting"}))
        self.assertIn("process: \"forging\" is not a process cadgen checks", value_error(self, read_study, {"process": "forging"}))
        self.assertIn("'modal' is an analysis, not a manufacturing process: solve it with `cadgen fea solve",
                      value_error(self, read_study, {"process": "modal"}))
        # An unknown key names the process's own keys, led by the one that names it.
        self.assertIn("casting studies take process, material, alloy, ",
                      value_error(self, read_study, {"process": "casting", "alloy": "a356", "mold": "sand", "gate": 1}))


class Results(unittest.TestCase):
    def test_a_study_named_as_the_result_is_refused_and_left_as_it_is(self):
        import json
        import tempfile
        from pathlib import Path

        from cadgen import manufacturing

        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "part.casting.result.json"
            study.write_text(json.dumps({"process": "casting", "alloy": "a356", "mold": "sand"}), encoding="utf-8")
            message = value_error(self, manufacturing.check, Path(directory) / "part.step", study=study)
            self.assertIn("part.casting.result.json is where the check writes its result; name the study "
                          "part.casting.json", message)
            self.assertTrue(study.is_file())


class Registry(unittest.TestCase):
    def test_every_process_is_its_registered_class_and_imports_stdlib_only(self):
        self.assertEqual(PROCESS_NAMES, ("casting", "molding", "heat_treatment", "machining", "printing", "welding",
                                         "sheet_metal"))
        for name, entry in REGISTRY.items():
            with self.subTest(process=name):
                process = get_process(name)
                self.assertEqual((type(process).__name__, process.name, process.word), (entry.cls, name, entry.word))
                self.assertEqual(process.estimate_only, entry.status == "estimate")
                self.assertIs(get_process(name), process)
                self.assertIsNone(process.material_from_spec("steel") if name != "machining" else None)
        # The registry, the base and every process module load without numpy, scipy, scikit-fem, netgen or OCP: a
        # malformed study fails before any of them is imported.
        modules = ["cadgen._internal.manufacturing.processes", "cadgen._internal.manufacturing.run",
                   *(entry.module for entry in REGISTRY.values())]
        self.assertEqual(heavy_at_import(*modules), "")


class ClosedFindings(unittest.TestCase):
    def test_a_finding_outside_its_processs_set_is_refused_where_it_is_made(self):
        finding = finding_of("casting")
        made = finding("error", "misrun", "a misrun", "", fix={"action": "thicken", "summary": "", "where": [],
                                                               "params": {}, "alternatives": [{"action": "move_gate"}]})
        self.assertEqual((made["check"], made["type"]), ("casting", "misrun"))
        self.assertIn("'chill' of 'casting' is not in FINDING_TYPES", value_error(self, finding, "info", "chill", "", ""))
        self.assertIn("made at error, not 'warning'", value_error(self, finding, "warning", "misrun", "", ""))
        self.assertIn("no fix action 'add_rib'",
                      value_error(self, finding, "error", "misrun", "", "", fix={"action": "thicken",
                                                                                 "alternatives": [{"action": "add_rib"}]}))
        # The run's own findings are fea's, of the run's set; another check's are no process's.
        closed("casting", [made, {"check": RUN, "type": "fit_iterative", "severity": "info"}])
        self.assertIn("made a finding of 'molding'",
                      value_error(self, closed, "casting", [{**made, "check": "molding"}]))

    def test_every_rung_a_process_takes_is_a_finding_of_the_run(self):
        for name in PROCESS_NAMES:
            for rung in get_process(name).ladder:
                with self.subTest(process=name, rung=rung):
                    self.assertIn(f"fit_{rung}", FINDING_TYPES[RUN])


class SkillDocs(unittest.TestCase):
    def test_checks_md_lists_every_check_and_finding_with_its_severity_and_fix_actions(self):
        page = SKILL / "references" / "checks.md"
        for check, kinds in FINDING_TYPES.items():
            listed = {}
            for cells in rows(page, f"## `{check}`"):
                found = re.fullmatch(r"`([a-z_0-9]+)`", cells[0])
                if found:
                    listed[found.group(1)] = (severities(cells[1]), set(re.findall(r"`([a-z_]+)`", cells[3])))
            with self.subTest(check=check):
                self.assertEqual(sorted(listed), sorted(kinds), f"checks.md's {check} table names other types")
            for kind, spec in kinds.items():
                with self.subTest(check=check, type=kind):
                    self.assertEqual(listed[kind], (set(spec.severities), set(spec.actions)))

    def test_each_process_reference_lists_its_findings_at_their_severities(self):
        for name, page in PAGES.items():
            listed = {}
            for cells in rows(SKILL / "references" / page, "## Findings"):
                found = re.fullmatch(r"`([a-z_0-9]+)`", cells[0])
                if found:
                    listed[found.group(1)] = severities(cells[1])
            kinds = FINDING_TYPES[name]
            with self.subTest(process=name):
                self.assertEqual(sorted(set(listed) - set(FINDING_TYPES[RUN])), sorted(kinds))
            for kind, spec in kinds.items():
                with self.subTest(process=name, type=kind):
                    self.assertEqual(listed[kind], set(spec.severities))

    def test_the_router_runs_each_process_today_with_its_command_and_estimates_the_rest(self):
        running = {}
        for cells in rows(SKILL / "SKILL.md", "## Choose the process"):
            with self.subTest(row=cells[0]):
                self.assertEqual(len(cells), 5, cells)
                status, named = cells[3], re.match(r"`([a-z_]+)`", cells[1])
                if status.startswith("**Runs today**"):
                    running[named.group(1)] = cells
                else:
                    self.assertTrue(status.startswith("**Estimate**"), status)
                    self.assertIn("references/estimates.md", cells[4])
        self.assertEqual(sorted(running), sorted(PROCESS_NAMES))
        for name, cells in running.items():
            with self.subTest(process=name):
                self.assertEqual(cells[2], REGISTRY[name].word)
                self.assertTrue(cells[3].startswith(f"**Runs today** ({REGISTRY[name].status}"), cells[3])
                self.assertIn(f"`cadgen manufacturing check part.step --study part.{name}.json`", cells[3])
                self.assertIn(f"references/{PAGES[name]}", cells[4])

    def test_a_reference_page_studies_name_their_process(self):
        for name, page in PAGES.items():
            text = (SKILL / "references" / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertIn(f'"process": "{name}"', text)
                self.assertNotIn('"analysis"', text)
                self.assertNotIn("cadgen fea solve", text)
                self.assertNotIn(".fea.glb", text)
