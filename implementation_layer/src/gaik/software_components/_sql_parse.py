"""Parse SQL with sqlglot and notice a function call that ignores one of its arguments.

sqlglot builds many functions from their written arguments by position and ignores
any argument it has no slot for. DuckDB's ``date_trunc('month', ts, 'Europe/Helsinki')``
is read as ``DATE_TRUNC('MONTH', ts)``: the parse succeeds, the render matches the tree,
and the query would run with a different meaning than the one written. ``parse``
marks every such call, and ``dropped_argument`` finds the mark in the finished tree,
so the SQL validators can refuse the query and the agent can write it another way.

Two checks find these calls; both treat an argument as ignored only when the call
comes out the same with a probe value in its place, so a value sqlglot rewrites on
the way in still counts as used: a date part (``'d'`` becomes ``DAY``), a format
string, a JSON path, or a sort order that picks another function.

* **The builder check** wraps the parser's table of function builders. An argument
  the built node holds is used; any other one is replaced with a probe and the call
  built again from copies, so the parsed tree is not touched.
* **The written-call check** reads the calls from the tokens: each name followed by a
  parenthesis, with its top-level arguments split at the commas between them. An
  argument is used when a node of the parsed tree comes from one of its tokens. Any
  other one is replaced in the call's text with a probe (a string and a column, in
  turn), and the call alone is parsed again; when every probe parses to the same
  node as the call, the argument was ignored. It does not hook into the parser, so
  it covers the functions sqlglot reads with a parser of its own (``ARG_MAX``,
  ``QUANTILE``, ``CEIL``, DuckDB's ``MAP`` and others), which the builder table does
  not reach.

With sqlglot's compiled build (``sqlglot[c]``, the ``sqlglotc`` package) the builder
check cannot run: its parser classes are native, and an instance attribute cannot be
set on them. The written-call check then covers every call, so both builds refuse
the same lossy calls.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Collection, Iterator, Sequence
from functools import cache
from typing import Any

from sqlglot import exp
from sqlglot.dialects.dialect import Dialect
from sqlglot.tokens import TokenType

_DROPPED = "gaik_dropped_argument"

# Two probes, so one of them always differs from the argument it replaces.
_PROBES = (exp.Literal.string("gaik_probe_a"), exp.Literal.string("gaik_probe_b"))

# The written-call check replaces an argument with each probe of one of these pairs,
# a string and a column; the second pair stands in where the argument is the first.
_TEXT_PROBES = (("'gaik_probe_a'", "gaik_probe_a"), ("'gaik_probe_b'", "gaik_probe_b"))

_OPENING = frozenset({TokenType.L_PAREN, TokenType.L_BRACKET, TokenType.L_BRACE})
_CLOSING = frozenset({TokenType.R_PAREN, TokenType.R_BRACKET, TokenType.R_BRACE})


def parse(sql: str, dialect: str) -> list[exp.Expression | None]:
    """Parse ``sql`` like ``sqlglot.parse(sql, read=dialect)``, marking lossy calls."""
    reader = Dialect.get_or_raise(dialect)
    parser = reader.parser()
    parser_class = type(parser)
    # The written-call check covers the calls the builder check cannot see.
    unchecked: frozenset[str] | None = _parsed_without_builder(parser_class)
    try:
        # An instance attribute, so the dialect's own parser class is left as it is.
        parser.FUNCTIONS = _checked_functions(parser_class)
    except AttributeError:
        unchecked = None  # the compiled build: every call is checked from its text
    tokens = reader.tokenize(sql)
    trees = parser.parse(tokens, sql)
    _mark_written_calls(sql, tokens, trees, reader, parser_class, unchecked)
    return trees


def dropped_argument(tree: exp.Expression) -> exp.Expression | None:
    """Return the first call in ``tree`` that was built without one of its arguments."""
    return next((node for node in tree.walk() if node.meta.get(_DROPPED)), None)


# ---------------------------------------------------------------- builder check


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


# ----------------------------------------------------------- written-call check


@cache
def _parsed_without_builder(parser_class: type) -> frozenset[str]:
    """Names sqlglot reads with a parser of its own, which the builder check misses."""
    return frozenset(
        name.upper()
        for name in (*parser_class.FUNCTION_PARSERS, *parser_class.NO_PAREN_FUNCTION_PARSERS)
    )


def _mark_written_calls(
    sql: str,
    tokens: Sequence[Any],
    trees: list[exp.Expression | None],
    reader: Dialect,
    parser_class: type,
    names: frozenset[str] | None,
) -> None:
    """Mark each call, of ``names`` or of any name, that ignores a written argument."""
    roots = [tree for tree in trees if tree is not None]
    if not roots:
        return
    # Where a node of the tree comes from: the first character of its token.
    starts = sorted(
        {
            node.meta["start"]
            for root in roots
            for node in root.walk()
            if isinstance(node.meta.get("start"), int)
        }
    )
    for name, arguments, close in _written_calls(tokens, parser_class.FUNC_TOKENS):
        if names is not None and tokens[name].text.upper() not in names:
            continue
        unheld = [
            (tokens[first].start, tokens[last].end)
            for first, last in arguments
            if not _holds(starts, tokens[first].start, tokens[last].end)
        ]
        if not unheld:
            continue
        built = _ignoring_call(sql, tokens[name].start, tokens[close].end, unheld, reader)
        if built is not None:
            _mark(roots, built)


def _written_calls(
    tokens: Sequence[Any], func_tokens: Collection[Any]
) -> Iterator[tuple[int, list[tuple[int, int]], int]]:
    """``(name, [(first, last) token of each top-level argument], closing parenthesis)``.

    One pass: each opening bracket collects the commas directly inside it.
    """
    # (index of the opening bracket, indices of the commas directly inside it)
    open_brackets: list[tuple[int, list[int]]] = []
    for index, token in enumerate(tokens):
        kind = token.token_type
        if kind in _OPENING:
            open_brackets.append((index, []))
        elif kind == TokenType.COMMA and open_brackets:
            open_brackets[-1][1].append(index)
        elif kind in _CLOSING and open_brackets:
            opening, commas = open_brackets.pop()
            name = opening - 1
            if (
                tokens[opening].token_type != TokenType.L_PAREN
                or name < 0
                or tokens[name].token_type not in func_tokens
                # A method call or a qualified name; the parse handles it.
                or (name and tokens[name - 1].token_type == TokenType.DOT)
            ):
                continue
            bounds = [opening, *commas, index]
            arguments = [
                (start + 1, end - 1) for start, end in zip(bounds, bounds[1:]) if start + 1 < end
            ]
            yield name, arguments, index


def _holds(starts: list[int], start: int, end: int) -> bool:
    """Whether a node of the tree comes from a token between ``start`` and ``end``."""
    at = bisect_left(starts, start)
    return at < len(starts) and starts[at] <= end


def _ignoring_call(
    sql: str, start: int, end: int, unheld: list[tuple[int, int]], reader: Dialect
) -> exp.Expression | None:
    """The call at ``sql[start:end + 1]`` as built, if it ignores one of ``unheld``."""
    text = sql[start : end + 1]
    built = _parse_call(text, reader)
    if built is None:
        return None
    for arg_start, arg_end in unheld:
        before, written, after = (
            text[: arg_start - start],
            text[arg_start - start : arg_end - start + 1],
            text[arg_end - start + 1 :],
        )
        probes = _TEXT_PROBES[1] if written in _TEXT_PROBES[0] else _TEXT_PROBES[0]
        if all(_parse_call(before + probe + after, reader) == built for probe in probes):
            return built
    return None


def _parse_call(text: str, reader: Dialect) -> exp.Expression | None:
    """The node ``SELECT <text>`` builds for ``text``, or ``None`` if it does not parse."""
    try:
        statements = reader.parse(f"SELECT {text}")
    except Exception:
        return None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return None
    selected = statements[0].expressions
    return selected[0] if len(selected) == 1 else None


def _mark(roots: list[exp.Expression], built: exp.Expression) -> None:
    """Mark the node of the tree that is ``built``, or the statement if none is."""
    for root in roots:
        for node in root.walk():
            if node == built:
                node.meta[_DROPPED] = True
                return
    roots[0].meta[_DROPPED] = True
