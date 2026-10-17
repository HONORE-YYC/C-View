import json
from pathlib import Path

import pytest

from cvisualizer.engine import Engine
from cvisualizer.structures import Binding, describe


EXAMPLES = Path(__file__).resolve().parents[1] / 'cvisualizer/examples'


@pytest.mark.parametrize('filename,expected', [
    ('basics.c', {'sum': 16, 'count': 0, 'average': 3.2}),
    ('list.c', {'length': 4, 'found': 1}),
    ('stack.c', {'top': 2, 'popped': 30}),
    ('queue.c', {'front': 2, 'rear': 1}),
    ('mixed.c', {'length': 4, 'top': 1, 'front': 1, 'rear': 4, 'popped': 6, 'first': 2}),
    ('macros.c', {'x': 7, 'pending': None}),
    ('animation.c', {'target': 4, 'i': 2, 'j': 1, 'a': [2, 4, 4, 2]}),
    ('functions.c', {'source': 3, 'answer': 6, 'numbers': [7, 8, 9, 10], 'total': 34}),
    ('pointers.c', {'x': 7, 'values': [2, 17, 4, 5]}),
    ('input.c', {'count': 3000000000, 'price': 2.5, 'grade': 65, 'matched': 4}),
    ('strings_arrays.c', {'count': 3, 'total': 12, 'length': 6, 'same': 0}),
    ('large_arrays.c', {'capacity': 1000000}),
])
def test_examples_execute_and_bindings_are_valid(filename, expected):
    path = EXAMPLES / filename
    engine = Engine(path.read_text(encoding='utf-8'))
    if filename == 'input.c':
        engine.runtime.input_provider = lambda prompt: '3000000000 2.5 A Alice'
    while engine.peek():
        engine.step()
    snapshot = engine.runtime.snapshot()
    for name, value in expected.items():
        assert snapshot[name]['value'] == value
    sidecar = path.with_suffix('.cview.json')
    if sidecar.exists():
        models = {b['array']: describe(Binding(**b), snapshot)
                  for b in json.loads(sidecar.read_text(encoding='utf-8'))}
        assert all(not model.error for model in models.values())
        if filename == 'queue.c':
            assert models['queue'].logical == [30, 40, 50, 60]
        if filename == 'list.c':
            assert models['data'].logical == [10, 99, 20, 40]
        if filename == 'mixed.c':
            assert models['data'].logical == [2, 9, 4, 6]
            assert models['stack'].logical == [2, 4]
            assert models['queue'].logical == [4, 6, 99]
