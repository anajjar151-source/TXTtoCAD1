"""The engine behind :mod:`cadgen.manufacturing`: what happens to a part while it is made, checked as CI checks code.

``processes/`` holds each process (``casting``, ``molding``, ``heat_treatment``, ``machining``, ``printing``,
``welding``, ``sheet_metal``) and the physics beside it, with the closed set of the findings each makes
(``processes/base.py``); ``run.py`` reads a study, hands it to fea's pipeline with its process and returns the verdict.
The generic machinery (the mesh, the element space, the thermal, static and modal solvers, the materials, the
fit-the-budget ladder, the GLB and sidecar writers) is fea's (``cadgen._internal.fea``), imported, never copied.
"""
