import ast
import operator

from mcp.server import MCPServer

mcp = MCPServer("calculator")

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def evaluate(node: ast.AST) -> float:
    """Compute an expression tree made of numbers and the four operations"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        left = evaluate(node.left)
        right = evaluate(node.right)
        return OPERATORS[type(node.op)](left, right)
    raise ValueError("unsupported expression")


@mcp.tool()
def calculate(expression: str) -> str:
    """Compute a simple arithmetic expression"""
    return str(evaluate(ast.parse(expression, mode="eval").body))
