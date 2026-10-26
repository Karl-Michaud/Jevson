"""Static name bindings of a module, for `pins.python_items` (RC5-1, B10 review round 5).

A frozen item of an amendable module is keyed `<path>::<name>`. A second binding of that name (`usage_of =
wrap(usage_of)`, a second `def usage_of`, `import x as usage_of`, `usage_of.__code__ = ...`) is not an item of its
own, so without this check it left the frozen-item map unchanged. Only static bindings are seen: a rebinding done at
run time (`setattr`, `globals()`, `exec`, `sys.modules`, or any code inside a function body) is the residual the
appendix discloses.
"""

from __future__ import annotations

import ast
from collections.abc import Collection, Sequence


def _bound(node: ast.AST, prefix: str) -> list[tuple[str, bool]]:
    """The names one node binds in the scope `prefix` (`""` or `<Class>.`), each with whether it is an attribute
    store (RC5-1): assignment, deletion, `for`, `with`, walrus, `except` and `match` targets, imports (a star import
    binds `*`), `global` and `nonlocal` declarations (module names), a `def` or `class` name, and an attribute
    store or deletion, as its root name (`A.b = ...` stores into `A`)."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
        return [(prefix + node.id, False)]
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store | ast.Del):
        root: ast.expr = node
        while isinstance(root, ast.Attribute):
            root = root.value
        return [(prefix + root.id, True)] if isinstance(root, ast.Name) else []
    if isinstance(node, ast.Import | ast.ImportFrom):
        return [(prefix + (a.asname or a.name.split(".")[0]), False) for a in node.names]
    if isinstance(node, ast.Global | ast.Nonlocal):
        return [(name, False) for name in node.names]
    named = getattr(node, "name", None) or getattr(node, "rest", None)
    binder = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler, ast.MatchAs, ast.MatchStar,
              ast.MatchMapping)  # fmt: skip
    return [(prefix + named, False)] if isinstance(node, binder) and isinstance(named, str) else []


def _bindings(nodes: Sequence[ast.AST], prefix: str = "") -> list[tuple[str, bool]]:
    """Every binding of a module or class scope, in source order. Class bodies are entered as `<Class>.`; function
    and lambda bodies are not (their names are local), except for their `global` and `nonlocal` declarations, and
    neither are comprehension targets. An annotation without a value binds nothing."""
    found: list[tuple[str, bool]] = []
    for node in nodes:
        if isinstance(node, ast.AnnAssign) and node.value is None:
            continue
        found += _bound(node, prefix)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            outer = [*getattr(node, "decorator_list", []), *node.args.defaults, *node.args.kw_defaults]
            found += _bindings([n for n in outer if n is not None], prefix)
            found += [(name, False) for n in ast.walk(node) if isinstance(n, ast.Global | ast.Nonlocal)
                      for name in n.names]  # fmt: skip
        elif isinstance(node, ast.ClassDef):
            found += _bindings([*node.decorator_list, *node.bases, *node.keywords], prefix)
            found += _bindings(node.body, f"{prefix}{node.name}.")
        elif isinstance(node, ast.comprehension):
            found += _bindings([node.iter, *node.ifs], prefix)
        else:
            found += _bindings(list(ast.iter_child_nodes(node)), prefix)
    return found


def rebinding(tree: ast.Module, frozen: Collection[str]) -> str | None:
    """RC5-1: the first of the `frozen` names (an amendable module's constants and `FROZEN_FUNCTIONS`) bound more than
    once in its scope, or has an attribute stored into or deleted (`*` for a star import), else None. Without this,
    `usage_of = wrap(usage_of)` or a second `def usage_of` left the map unchanged: its item shared the definition's
    key `<path>::usage_of`, and the definition's overwrote it (exp/b48b/rev-correct/r5/collision5.out)."""
    roots = {name.split(".")[0] for name in frozen}
    seen: set[str] = set()
    for name, attribute in _bindings(tree.body):
        if name == "*" or (attribute and (name in frozen or name in roots)):
            return name
        if name in frozen and name in seen:
            return name
        seen.add(name)
    return None
