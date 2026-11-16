"""App workflow regression with a Streamlit stub (no live server required)."""

import runpy
import sys

import pytest


class StopRender(Exception):
    pass


class StreamlitStub:
    def __init__(self):
        self.sidebar = self
        self.session_state = {}
        self.submitted = False
        self.preset = None
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def form(self, *a, **kw):
        return self

    def spinner(self, *a, **kw):
        return self

    def expander(self, *a, **kw):
        return self

    def popover(self, *a, **kw):
        return self

    def selectbox(self, label, options, key=None):
        choice = self.preset or options[0]
        if key is not None:
            self.session_state[key] = choice
        return choice

    def number_input(self, label, *, value, **kwargs):
        return value

    def slider(self, label, *, value, **kwargs):
        return value

    def checkbox(self, label, value=False, **kwargs):
        return value

    def form_submit_button(self, label, **kwargs):
        assert label == "🧮 Calculate & Optimize"
        return self.submitted

    def stop(self):
        raise StopRender()

    def columns(self, count, **kwargs):
        return [self] * (count if isinstance(count, int) else len(count))

    def tabs(self, labels, **kwargs):
        return [self] * len(labels)

    def info(self, message, **kwargs):
        self.messages.append(str(message))

    def error(self, message, **kwargs):
        self.messages.append(str(message))

    def __getattr__(self, name):
        return lambda *a, **kw: None


def run_app(stub, monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    return runpy.run_path("app.py", run_name="__main__")


def test_calculate_button_controls_results_and_preset_switch(monkeypatch):
    st = StreamlitStub()
    with pytest.raises(StopRender):
        run_app(st, monkeypatch)
    assert "reliflow_last_result" not in st.session_state
    assert any("Calculate & Optimize" in msg for msg in st.messages)

    st.submitted = True
    run_app(st, monkeypatch)
    saved = st.session_state["reliflow_last_result"]
    assert saved["strategies"][0].annual_total_cost > 0

    st.submitted = False
    run_app(st, monkeypatch)
    assert st.session_state["reliflow_last_result"] is saved

    from reliflow.presets import PRESETS
    st.preset = next(name for name in PRESETS if name != saved["preset"])
    with pytest.raises(StopRender):
        run_app(st, monkeypatch)
    assert st.session_state["reliflow_last_result"] is saved

    st.submitted = True
    run_app(st, monkeypatch)
    assert st.session_state["reliflow_last_result"]["preset"] == st.preset
