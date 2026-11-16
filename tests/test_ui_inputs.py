"""Regression checks for Streamlit's number input type discipline."""
import ast
from pathlib import Path

from reliflow.presets import PRESETS


class StrictStreamlit:
    session_state = {"preset_name": "default"}

    def __init__(self):
        self.calls = []

    def number_input(self, label, *, min_value, max_value, value, step, format, key):
        values = [x for x in (value, min_value, max_value, step) if x is not None]
        assert values and all(type(x) is float for x in values), (label, values)
        assert min_value is None or value >= min_value, label
        assert max_value is None or value <= max_value, label
        self.calls.append((label, key, value))
        return value


def _extract_number_wrapper():
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "number")
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    stub = StrictStreamlit()
    env = {"st": stub}
    exec(compile(module, str(source), "exec"), env)
    return env["number"], stub, tree


def test_integer_percentage_bounds_are_normalized_to_floats():
    number, stub, _ = _extract_number_wrapper()
    result = number("Minimum allowable optimization speed (%)", {"minimum": 65}, "minimum",
                    min_value=20, max_value=140, step=1.0, fmt="%.0f")
    assert result == 65.0
    assert stub.calls[0][2] == 65.0


def test_all_preset_numeric_widgets_have_compatible_types():
    number, stub, tree = _extract_number_wrapper()
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "number"]
    assert len(calls) >= 20
    suction_assignment = next(node for node in ast.walk(tree)
                             if isinstance(node, ast.Assign)
                             and any(isinstance(t, ast.Name) and t.id == "suction_defaults" for t in node.targets))
    suction_defaults = ast.literal_eval(suction_assignment.value)
    for preset_name, preset in PRESETS.items():
        stub.session_state["preset_name"] = preset_name
        test_values = {**preset, **suction_defaults}
        for call in calls:
            key = ast.literal_eval(call.args[2])
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
            number(key, test_values, key, **kwargs)
    assert len(stub.calls) == len(calls) * len(PRESETS)
