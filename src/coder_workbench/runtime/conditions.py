from __future__ import annotations

import ast
from typing import Any


class ConditionError(ValueError):
    pass


def evaluate_condition(expression: str | None, data: dict[str, Any]) -> bool:
    if not expression:
        return True
    tree = ast.parse(expression, mode="eval")
    return bool(_eval(tree.body, data))


def _eval(node: ast.AST, data: dict[str, Any]) -> Any:
    if isinstance(node, ast.BoolOp):
        values = [_eval(value, data) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, data)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, data)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, data)
            if not _compare(left, op, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        return data.get(node.id)
    if isinstance(node, ast.Attribute):
        value = _eval(node.value, data)
        if isinstance(value, dict):
            return value.get(node.attr)
        return getattr(value, node.attr, None)
    if isinstance(node, ast.Subscript):
        value = _eval(node.value, data)
        key = _eval(node.slice, data)
        return value[key]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_eval(item, data) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval(item, data) for item in node.elts)

    raise ConditionError(f"Unsupported condition expression: {ast.dump(node)}")


def _compare(left: Any, op: ast.cmpop, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.In):
        return left in right
    if isinstance(op, ast.NotIn):
        return left not in right
    raise ConditionError(f"Unsupported comparison operator: {type(op).__name__}")
