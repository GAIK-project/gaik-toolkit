"""Settings shared by every operation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._runtime import maybe_quiet, need


@dataclass(frozen=True)
class OperationSettings:
    """How the operations reach a model and where they keep working files.

    The defaults change nothing in a request except the timeout: ``temperature=0.0`` and
    ``reasoning_effort=None`` are the components' own defaults.
    """

    config: Mapping[str, Any] | None = field(default=None, repr=False)
    """A gaik config dict. It holds the key, so it stays out of ``repr``."""
    provider: str | None = None
    """Used only when ``config`` is None: ``get_llm_config(provider)``."""
    timeout: float | None = 120.0
    """Seconds per model request. A timeout already in ``config`` wins."""
    quiet: bool = True
    """Keep what gaik prints out of stdout."""
    work_dir: str | Path | None = None
    """Parent of temporary working folders. None: the system's temporary folder."""
    temperature: float | None = 0.0
    reasoning_effort: str | None = None

    def llm_config(self) -> dict[str, Any]:
        """The config dict the components get: ``config`` or the provider's, with the timeout."""
        if self.config is not None:
            config = dict(self.config)
        else:
            with maybe_quiet(self.quiet):
                try:
                    from gaik.software_components.llm import get_llm_config
                except ImportError as error:
                    raise need("the model configuration", "openai") from error
                config = get_llm_config(self.provider)
        if self.timeout is not None:
            config.setdefault("timeout", self.timeout)
        return config
