"""CLI workflow/handover progress output for the agentic report workflow.

``ProgressReporter`` emits short human-readable lines as the agentic workflow
runs so the agent communication and handovers are visible at the CLI. It is
dependency-free: the default sink is ``print`` (only when ``verbose=True``), and
a ``callback`` overrides it.
"""

from __future__ import annotations

from collections.abc import Callable


class ProgressReporter:
    def __init__(
        self,
        *,
        verbose: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> None:
        self.verbose = verbose
        self.callback = callback

    def emit(self, message: str) -> None:
        if self.callback is not None:
            self.callback(message)
        elif self.verbose:
            print(message)
