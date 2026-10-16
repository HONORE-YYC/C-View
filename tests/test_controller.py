from cvisualizer.controller import Controller


def test_pause_stop_restart_and_step():
    c = Controller('int x=0; while(x<5){x++;}')
    c.play()
    c.tick()
    assert c.engine.runtime.snapshot()['x']['value'] == 0
    c.pause()
    c.tick()
    assert c.engine.count == 1
    c.step()
    assert c.state == 'paused'
    c.stop()
    assert c.state == 'stopped'
    c.play()
    assert c.engine.count == 0
    c.tick()
    assert c.engine.runtime.snapshot()['x']['value'] == 0


def test_seek_stops_before_target_and_next_loop_occurrence():
    c = Controller('int x=0;\nwhile(x<3){\n x++;\n}')
    target = next(t for t in c.targets if t.line == 3)
    c.seek(target)
    c.tick()
    assert c.state == 'paused'
    assert c.engine.runtime.snapshot()['x']['value'] == 0
    c.step()
    assert c.engine.runtime.snapshot()['x']['value'] == 1
    c.seek(target)
    c.tick()
    assert c.engine.runtime.snapshot()['x']['value'] == 1
    assert c.engine.peek().line == 3


def test_unreachable_target_and_infinite_loop_budget():
    c = Controller('if(0){int never=1;}')
    c.seek(next(t for t in c.targets if 'never' in t.text))
    c.tick()
    assert c.state == 'finished'
    assert '未到达' in c.message
    c = Controller('while(1){}', max_steps=12)
    c.play()
    for _ in range(20):
        c.tick()
    assert c.state == 'error'
    assert '步数' in c.message


def test_seeking_can_pause_and_stop_before_budget():
    c = Controller('while(1){}\nint never=2;')
    c.seek(next(t for t in c.targets if t.line == 2))
    c.tick(batch=5)
    assert c.state == 'seeking'
    assert c.engine.count == 5
    c.pause()
    c.tick()
    assert c.engine.count == 5
    c.stop()
    assert c.state == 'stopped'


def test_multiple_statements_same_line_have_distinct_targets():
    c = Controller('int x=1; x++; x+=2;')
    c.seek(c.targets[-1])
    c.tick()
    assert c.engine.runtime.snapshot()['x']['value'] == 2
    c.step()
    assert c.engine.runtime.snapshot()['x']['value'] == 4
    assert c.state == 'finished'
