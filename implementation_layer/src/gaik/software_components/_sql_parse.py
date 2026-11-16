"""Parse SQL with sqlglot and notice a function call that ignores one of its arguments.

sqlglot builds many functions from their written arguments by position and ignores
any argument it has no slot for. DuckDB's ``date_trunc('month', ts, 'Europe/Helsinki')``
is read as ``DATE_TRUNC('MONTH', ts)``: the parse succeeds, the render matches the tree,
and the query would run with a different meaning than the one written. ``parse``
marks every such call, and ``dropped_argument`` finds the mark in the finished tree,
so the SQL validators can refuse the query and the agent can write it another way.

An argument the built node holds is used. Any other argument is replaced with a
probe value and the call built again from copies, so the parsed tree is not touched;
when the two builds are equal, the argument was ignored. Comparing builds rather than
looking for the argument in the result keeps the values sqlglot rewrites on the way
in: a date part (``'d'`` becomes ``DAY``), a format string, a JSON path, or a sort
order that picks another function.

Functions that sqlglot reads with a parser of their own (``CAST``, ``TRIM``,
``ARG_MAX`` and some others) are not built from a list of written arguments, so this
check does not cover them.

With sqlglot's compiled build (``sqlglot[c]``, the ``sqlglotc`` package) the check is
skipped: its parser classes are native, an instance attribute cannot be set on them and
a Python class cannot derive from them. ``parse`` then logs a warning once per dialect
and returns plain sqlglot's tree, so every read-only check of the validators still runs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import cache

from sqlglot import exp
from sqlglot.dialects.dialect import Dialect

logger = logging.getLogger(__name__)

_DROPPED = "gaik_dropped_argument"

# Two probes, so one of them always differs from the argument it replaces.
_PROBES = (exp.Literal.string("gaik_probe_a"), exp.Literal.string("gaik_probe_b"))


def parse(sql: str, dialect: str) -> list[exp.Expression | None]:
    """Parse ``sql`` like ``sqlglot.parse(sql, read=dialect)``, marking lossy calls."""
    reader = Dialect.get_or_raise(dialect)
    parser = reader.parser()
    functions = _checked_functions(type(parser))
    try:
        # An instance attribute, so the dialect's own parser class is left as it is.
        parser.FUNCTIONS = functions
    except AttributeError:
        _warn_unchecked(dialect)
    return parser.parse(reader.tokenize(sql), sql)


@cache
def _warn_unchecked(dialect: str) -> None:
    logger.warning(
        "sqlglot's compiled build (sqlglot[c]) is installed, so %s SQL is parsed without "
        "the check for function arguments that sqlglot drops while parsing. The read-only "
        "checks still run. Uninstall sqlglotc to keep the argument check.",
        dialect,
    )


def dropped_argument(tree: exp.Expression) -> exp.Expression | None:
    """Return the first call in ``tree`` that was built without one of its arguments."""
    return next((node for node in tree.walk() if node.meta.get(_DROPPED)), None)


@cache
def _checked_functions(parser_class: type) -> dict[str, Callable]:
    return {name: _checked(build) for name, build in parser_class.FUNCTIONS.items()}


def _checked(build: Callable) -> Callable:
    # ``dialect`` has no default: sqlglot calls a builder with the arguments only and
    # retries with ``dialect=`` on a TypeError, so this always receives it.
    def checked_build(args: list, dialect: Dialect) -> exp.Expression:
        node = _call(build, args, dialect)
        if not isinstance(node, exp.Expression):
            return node
        # An argument the node holds, or holds part of, is used. Only the others,
        # rewritten or dropped, need a probe build.
        held = {id(part) for part in node.walk()}
        for index, arg in enumerate(args):
            if not isinstance(arg, exp.Expression):
                continue
            if any(id(part) in held for part in arg.walk()):
                continue
            if _ignores(build, args, index, node, dialect):
                node.meta[_DROPPED] = True
                break
        return node

    return checked_build


def _call(build: Callable, args: list, dialect: Dialect):
    """Call a builder the way sqlglot's parser does."""
    try:
        return build(args)
    except TypeError:
        return build(args, dialect=dialect)


def _ignores(
    build: Callable, args: list, index: int, built: exp.Expression, dialect: Dialect
) -> bool:
    """Whether the call is built the same when argument ``index`` is another value."""
    probe = _PROBES[1] if args[index] == _PROBES[0] else _PROBES[0]
    trial = [a.copy() if isinstance(a, exp.Expression) else a for a in args]
    trial[index] = probe.copy()
    try:
        other = _call(build, trial, dialect)
    except Exception:
        return False  # the builder reads the argument, so it is not ignored
    return other == built
