from cvisualizer.controller import Controller


SOURCE = 'int add(int x){\nint y=x+1;\nreturn y;\n}\nint main(){\nint a=2;\nint b=add(a);\nb++;\n}'


def advance(controller):
    for _ in range(100):
        if controller.state not in ('running', 'seeking'):
            return
        controller.tick()
    raise AssertionError('Playback did not settle')


def test_gutter_function_call_automatically_plays_body_then_pauses():
    c = Controller(SOURCE)
    c.play_statement(next(loc for loc in c.targets if loc.line == 7))
    seen = []
    for _ in range(100):
        seen.extend(c.tick())
        if c.state not in ('running', 'seeking'):
            break
    assert any(event.function == 'add' for event in seen)
    assert c.state == 'paused'
    assert c.engine.runtime.snapshot()['b']['value'] == 3
    assert c.engine.peek().line == 8


def test_plain_step_uses_summary_unless_expansion_is_requested():
    c = Controller(SOURCE)
    c.step()
    event = c.step()
    assert event.calls and not event.function and not event.expanded
    c.reset(); c.step()
    event = c.step(expand_calls=True)
    assert event.function == 'add'
    c.pause()
    count = c.engine.count
    c.tick()
    assert c.engine.count == count
    c.play()
    advance(c)
    assert c.state == 'paused'
    assert c.engine.runtime.snapshot()['b']['value'] == 3


def test_gutter_body_statement_uses_real_call_parameters():
    c = Controller(SOURCE)
    c.play_statement(next(loc for loc in c.targets if loc.line == 2))
    advance(c)
    # Selecting a callee statement completes its ongoing function presentation.
    assert c.engine.runtime.snapshot()['b']['value'] == 3


def test_seek_inside_function_then_step_executes_only_target_statement():
    c = Controller(SOURCE)
    c.seek(next(loc for loc in c.targets if loc.line == 2))
    advance(c)
    event = c.step()
    assert event.line == 2
    assert event.function == 'add'
    assert event.variables['y']['value'] == 3


def test_seeking_main_skips_long_function_without_building_detail_trace():
    c = Controller('void f(){for(int i=0;i<1000;i++){} }\nint main(){\nf();\nint result=1;\n}')
    c.seek(next(loc for loc in c.targets if loc.line == 4))
    advance(c)
    assert c.state == 'paused', c.message
    assert c.step().variables['result']['value'] == 1


def test_seeking_nested_function_expands_its_callers():
    c = Controller('int inner(int x){\nreturn x+1;\n}\nint outer(int x){return inner(x);}\nint main(){int y=outer(4);}')
    c.seek(next(loc for loc in c.targets if loc.line == 2))
    advance(c)
    assert c.state == 'paused', c.message
    event = c.step()
    assert event.function == 'inner'
    assert event.variables['x']['value'] == 4


def test_seeking_out_of_detail_does_not_pause_subsequent_full_play():
    c = Controller(SOURCE.replace('b++;', 'b++;\nb++;\nb++;'))
    c.step()
    c.step(expand_calls=True)
    c.pause()
    c.seek(next(loc for loc in c.targets if loc.line == 9))
    advance(c)
    assert c.state == 'paused'
    c.play()
    advance(c)
    assert c.state == 'finished', c.message
    assert c.engine.runtime.snapshot()['b']['value'] == 6
