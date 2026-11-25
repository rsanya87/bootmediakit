"""Find user-visible text literals in the GUI sources (0.4.0 T5 test helper).

A string literal counts as user text when it has at least two letters and
a space or a non-ASCII character (Hungarian text practically always has
one of them; identifiers, object names, settings keys and command-line
options do not). Not counted: docstrings, ``raise`` arguments (developer
errors, not shown as such), the style sheet template, and the argument of
the ``tr()`` helper's own ``translate`` call.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

TR_NAMES = {"tr", "translate"}
SKIPPED_ASSIGNMENTS = {"STYLE_TEMPLATE"}


@dataclass(frozen=True)
class TextLiteral:
    line: int
    text: str
    in_tr: bool


def _is_user_text(value: str) -> bool:
    letters = sum(ch.isalpha() for ch in value)
    if letters < 2:
        return False
    return any(ch.isspace() for ch in value) or not value.isascii()


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def text_literals(source: str) -> list[TextLiteral]:
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def skipped(node: ast.AST) -> bool:
        parent = parents.get(node)
        if isinstance(parent, ast.Expr):
            return True  # docstring or bare string
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.Raise):
                return True
            if isinstance(current, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in SKIPPED_ASSIGNMENTS
                for target in current.targets
            ):
                return True
        return False

    def inside_tr(node: ast.AST) -> bool:
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.Call) and _call_name(current) in TR_NAMES:
                return True
        return False

    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if not _is_user_text(node.value) or skipped(node):
            continue
        found.append(TextLiteral(node.lineno, node.value, inside_tr(node)))
    return sorted(found, key=lambda item: (item.line, item.text))


def tr_calls_without_literal(source: str) -> list[int]:
    """Lines of ``tr()`` calls whose first argument is not a plain literal.

    A future message extractor can only collect literal source texts, so
    ``tr(f"...")`` or ``tr(variable)`` are not allowed (the helper's own
    ``QCoreApplication.translate(context, text)`` is the one exception).
    """
    tree = ast.parse(source)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) == "tr":
            if not node.args or not (
                isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            ):
                bad.append(node.lineno)
    return bad
