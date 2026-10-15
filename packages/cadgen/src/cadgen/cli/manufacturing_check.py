"""``cadgen manufacturing check`` — a GENERATED CLI over :func:`cadgen.manufacturing.check`.

No parser here on purpose: everything the command accepts is derived from the
verb function's signature by :mod:`cadgen._internal.cli_from_function`, so a
flag cannot drift from a parameter (README law 6). A check that ran and failed
its ``--fail-on`` gate exits 3 (``GATE_EXIT``).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen manufacturing check"
VERB = ("cadgen.manufacturing", "check")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
