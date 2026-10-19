import json
from pathlib import Path

import pytest

from cvisualizer.engine import Engine
from cvisualizer.example_catalog import EXAMPLE_CATALOG, EXAMPLE_DIRECTORY
from cvisualizer.structures import Binding, describe


EXAMPLES = EXAMPLE_DIRECTORY


@pytest.mark.parametrize('filename,expected', [
    ('basics.c', {'pending': None, 'source': 3, 'target': 7, 'average': 3.5}),
    ('types_casts.c', {'whole': 12, 'half': 6.0, 'population': 8000000000, 'ready': 1, 'grade': 65, 'score': 7}),
    ('bool_math.c', {'distance': 5.0, 'direct': 5.0, 'rounded': 3.0, 'magnitude': 2.5, 'nearby': 1, 'outside': 0, 'safe': 1, 'skipped': 0, 'x': 2.0, 'wave': 1.0, 'logarithm': 3.0}),
    ('list.c', {'length': 4, 'found': 1}),
    ('stack.c', {'top': 2, 'popped': 30}),
    ('queue.c', {'front': 2, 'rear': 1}),
    ('mixed.c', {'length': 4, 'top': 1, 'front': 1, 'rear': 4, 'popped': 6, 'first': 2}),
    ('loops_arrays.c', {'sum': 8, 'count': 0, 'i': 4, 'j': 1, 'a': [2, 4, 4, 2]}),
    ('matrices.c', {'total': 27, 'a': [[2, 3, 4], [5, 6, 3]], 'wide': [[0]*8, [0]*7+[3]]}),
    ('functions.c', {'source': 3, 'answer': 6, 'numbers': [7, 8, 9, 10], 'total': 34}),
    ('pointers.c', {'x': 7, 'values': [2, 17, 4, 5]}),
    ('input.c', {'count': 8000000000, 'price': 2.5, 'grade': 65, 'matched': 4}),
    ('strings_arrays.c', {'count': 3, 'total': 12, 'length': 6, 'same': 0}),
    ('large_arrays.c', {'capacity': 1000000}),
])
def test_examples_execute_and_bindings_are_valid(filename, expected):
    path = EXAMPLES / filename
    engine = Engine(path.read_text(encoding='utf-8'))
    if filename == 'input.c':
        engine.runtime.input_provider = lambda prompt: '8000000000 2.5 A Alice'
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


def test_catalog_lists_every_editable_example_once_in_learning_order():
    names = [name for name, _ in EXAMPLE_CATALOG]
    assert len(names) == len(set(names))
    assert set(names) == {path.name for path in EXAMPLES.glob('*.c')}
    for number, (_, title) in enumerate(EXAMPLE_CATALOG, 1):
        assert title.startswith(f'{number:02d} ')
    assert names.index('basics.c') < names.index('types_casts.c')
    assert names.index('loops_arrays.c') < names.index('functions.c')
    assert names.index('loops_arrays.c') < names.index('matrices.c') < names.index('functions.c')
    assert names.index('functions.c') < names.index('pointers.c')
    assert names.index('large_arrays.c') < names.index('list.c')
    assert names[-1] == 'mixed.c'
