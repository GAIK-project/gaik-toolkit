"""Option dictionaries that a module forwards to its components, checked by name.

``DocumentsToStructuredData`` and ``AudioToStructuredData`` take dictionaries
such as ``parser_ctor`` or ``extract_options`` and pass them on to a parser, the
transcriber or the extractor. A name must be a parameter of the component it
goes to, and a stage config (the provider credentials, the endpoint and its
allowed hosts) comes from the module's own constructor and is never accepted in
such a dictionary. Component parameters stay accepted under their own names:
``transcriber_ctor`` takes ``local_api_base`` / ``local_api_key``, which the
Transcriber checks against the allowed hosts, and write locations such as
``output_dir`` or ``json_path`` are not confined by this check.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from typing import Any

# A stage config carries the key, the endpoint and the list of allowed hosts.
STAGE_CONFIG_KEYS = frozenset({"config", "api_config", "openai_config"})

# The arguments a module passes to ``DataExtractor.extract`` itself.
EXTRACT_SET_BY_MODULE = ("extraction_model", "requirements", "user_requirements", "documents")


def checked_options(
    options: Mapping[str, Any] | None,
    target: Callable[..., Any] | None,
    *,
    what: str,
    set_by_module: Iterable[str] = (),
) -> dict[str, Any]:
    """Return ``options`` as a new dict once every name in it is allowed for ``target``.

    Args:
        options: The caller's dictionary, or ``None``.
        target: The class or method the options are passed to.
        what: The dictionary's name, for the error message.
        set_by_module: Parameters the module fills in itself.

    Raises:
        ValueError: For a stage config key, a parameter the module sets, or a
            name ``target`` does not take.
    """
    options = dict(options or {})
    if target is None:
        # A stand-in without the method (a test double): only stage configs are checked.
        for key in options:
            if key in STAGE_CONFIG_KEYS:
                raise ValueError(
                    f"{what}: {key!r} is not accepted here; pass the stage's config to "
                    "the module's constructor."
                )
        return options
    own = set(set_by_module)
    parameters = inspect.signature(target).parameters
    takes_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    names = {
        name
        for name, p in parameters.items()
        if name != "self" and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    }
    allowed = sorted(names - own - STAGE_CONFIG_KEYS)
    for key in options:
        if key in STAGE_CONFIG_KEYS:
            raise ValueError(
                f"{what}: {key!r} is not accepted here; pass the stage's config to the "
                "module's constructor (api_config, transcription_config, "
                "extraction_config or parser_config)."
            )
        if key in own:
            raise ValueError(f"{what}: {key!r} is set by the module itself.")
        if not takes_any and key not in names:
            raise ValueError(
                f"{what}: unknown option {key!r} for {_name(target)}; "
                f"allowed: {', '.join(allowed) or 'none'}."
            )
    return options


def _name(target: Callable[..., Any]) -> str:
    return getattr(target, "__qualname__", getattr(target, "__name__", repr(target)))
