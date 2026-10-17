import pytest

from cvisualizer.engine import Engine
from cvisualizer.language import CError


def finish(engine, expand=False):
    events = []
    while engine.peek():
        events.append(engine.step(expand_calls=expand))
    return events


def test_custom_call_returns_value_without_changing_scalar_argument():
    engine = Engine('int twice(int x){x*=2;return x;} int main(){int a=3;int b=twice(a);}')
    events = finish(engine)
    values = engine.runtime.snapshot()
    assert values['a']['value'] == 3
    assert values['b']['value'] == 6
    assert events[-1].calls[0]['name'] == 'twice'
    assert events[-1].calls[0]['inputs'][0]['value'] == 3
    assert len(events) == 2


def test_function_array_alias_and_globals_are_visible_in_caller():
    engine = Engine('int total=0; void add(int a[],int n){for(int i=0;i<n;i++){a[i]+=2;total+=a[i];}} int main(){int a[3]={1,2,3};add(a,3);}')
    finish(engine)
    values = engine.runtime.snapshot()
    assert values['a']['value'] == [3,4,5]
    assert values['total']['value'] == 12


def test_function_cannot_read_caller_local_and_error_rolls_back():
    engine = Engine('int global=0; int bad(){global=9;return hidden;} int main(){int hidden=3;int result=bad();}')
    engine.step(); engine.step()
    with pytest.raises(CError, match='未声明'):
        engine.step()
    assert engine.runtime.snapshot()['global']['value'] == 0
    assert 'result' not in engine.runtime.snapshot()


def test_detailed_steps_show_local_states_then_restore_main():
    engine = Engine('int inc(int x){int y=x; y++;return y;} int main(){int a=4;int b=inc(a);}')
    engine.step()
    events = finish(engine, expand=True)
    local = [event for event in events if event.function == 'inc']
    assert local and any(event.variables.get('y', {}).get('value') == 5 for event in local)
    assert all('a' not in event.variables for event in local)
    assert engine.runtime.snapshot()['b']['value'] == 5
    assert events[-1].function == ''


def test_nested_calls_and_short_circuit_have_exactly_once_side_effects():
    engine = Engine('int g=0; int inner(int x){g++;return x+1;} double outer(int x){return inner(x)*0.5;} int main(){int i=2;double y=outer(i++);int z=0&&inner(8);}')
    finish(engine, expand=True)
    values = engine.runtime.snapshot()
    assert values['g']['value'] == 1
    assert values['i']['value'] == 3
    assert values['y']['value'] == 1.5


def test_function_loop_budget_still_applies_when_collapsed():
    engine = Engine('void forever(){while(1){}} int main(){forever();}', max_steps=20)
    with pytest.raises(CError, match='步数'):
        finish(engine)
