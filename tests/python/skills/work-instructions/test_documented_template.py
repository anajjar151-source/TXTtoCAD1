"""The work-instructions skill's template is run, not just proofread.

An agent copies the template in `references/instruction-api.md`, so a template
that has drifted from `cadgen.work_instruction` is a generator of broken
scripts. It is extracted and run here against a three-part assembly written by
the test with the part names it uses, and must write its PDF with the open
items its placeholders leave. The pictures are left out (they are the snapshot
runtime's, tested with the engine), so this needs no browser.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import runpy
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

REFERENCE = repo_path("skills/work-instructions/references/instruction-api.md")
SKILL = repo_path("skills/work-instructions/SKILL.md")


def _template() -> str:
    text = REFERENCE.read_text(encoding="utf-8")
    section = text.split("## Template", 1)[1]
    found = re.search(r"```python\n(.*?)```", section, re.S)
    assert found, "the reference's Template section has no python block"
    return found.group(1)


class DocumentedTemplateTests(unittest.TestCase):
    def test_the_skill_links_the_template(self) -> None:
        self.assertIn("references/instruction-api.md#template", SKILL.read_text(encoding="utf-8"))

    def test_the_template_runs_and_leaves_its_placeholders_open(self) -> None:
        from build123d import Box, Compound, Pos
        from cadgen.step_export import export_build123d_step_file

        temporary = generated_cad_directory(prefix="wi-template-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(root / "store"), "CADGEN_DAEMON": "0", "CADGEN_COMPONENT_WORKERS": "1",
        }))
        parts = []
        for label, z, size in (("base_plate", 0, 10), ("bracket", 25, 40), ("pin", 50, 4)):
            part = Pos(0, 0, z) * Box(size * 2, size, size)
            part.label = label
            parts.append(part)
        (root / "STEP").mkdir()
        export_build123d_step_file(Compound(children=parts, label="bracket_assembly"),
                                   root / "STEP/bracket_assembly.step")
        (root / "src").mkdir()
        script = root / "src/bracket_assembly_wi.py"
        script.write_text(_template(), encoding="utf-8")

        printed = io.StringIO()
        with mock.patch("cadgen._internal.work_instruction_pages.render_pictures", return_value={}), \
                contextlib.redirect_stdout(printed):
            runpy.run_path(str(script), run_name="__main__")
        self.assertTrue((root / "PDF/bracket_assembly_wi.pdf").is_file())
        self.assertIn("open item: step 2 (bond): pot life not stated", printed.getvalue())
        self.assertIn("open item: step 4 (fasten): torque not stated", printed.getvalue())


if __name__ == "__main__":
    unittest.main()
