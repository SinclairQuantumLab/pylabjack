import ast
import inspect
from pathlib import Path

import pylabjack._stream as stream_module


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_DOCUMENT = REPOSITORY_ROOT / "docs" / "stream-capabilities.md"


def test_stream_module_docstring_states_the_execution_boundary():
    docstring = stream_module.__doc__

    assert docstring is not None
    assert "all-AIN" in docstring
    assert "input-only" in docstring
    assert "Stream-Out" in docstring
    assert "docs/stream-capabilities.md" in docstring


def test_capability_ledger_covers_every_ljm_call_in_stream_module():
    source = inspect.getsource(stream_module)
    syntax_tree = ast.parse(source)
    ljm_calls = {
        node.func.attr
        for node in ast.walk(syntax_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ljm"
    }
    document = CAPABILITY_DOCUMENT.read_text(encoding="utf-8")

    assert ljm_calls
    for function_name in ljm_calls:
        assert f"`ljm.{function_name}()`" in document


def test_capability_ledger_names_deferred_stream_out_primitives_and_boundaries():
    document = CAPABILITY_DOCUMENT.read_text(encoding="utf-8")

    for function_name in (
        "periodicStreamOut",
        "initializeAperiodicStreamOut",
        "writeAperiodicStreamOut",
    ):
        assert f"`ljm.{function_name}()`" in document
    for boundary in (
        "Digital Stream-In (DI/DIO state)",
        "Output-only session",
        "Combined input/output session",
        "External clock",
        "Repeated input address",
        "Native LJM and physical-hardware validation",
    ):
        assert boundary in document
