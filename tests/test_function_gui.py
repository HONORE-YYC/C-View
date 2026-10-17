from cvisualizer.window import MainWindow


SOURCE = 'int inc(int x){\nint y=x;\ny++;\nreturn y;\n}\nint main(){\nint a=3;\nint b=inc(a);\nb++;\n}'


def tick_until_paused(window):
    for _ in range(100):
        window.visuals.motion.finish()
        if window.controller.state not in ('running', 'seeking'):
            return
        window.on_tick()
    raise AssertionError('Playback did not settle')


def test_function_cards_and_expansion_offer_keep_plain_step_fast(app):
    window = MainWindow()
    window.load_code(SOURCE, [])
    assert 'inc' in window.visuals.function_boxes
    assert window.visuals.function_boxes['inc'].brush().color().name() == '#f3e8ff'
    window.step()
    assert not window.function_offer.isHidden()
    window.step()
    assert window.controller.engine.last.calls
    assert not window.controller.engine.last.expanded
    assert window.visuals.motion.summary is not None
    window.stop(); window.close()


def test_expansion_temporarily_shows_only_callee_in_purple_then_restores(app):
    window = MainWindow()
    window.load_code(SOURCE, [])
    window.step()
    window.function_offer.click()
    assert window.controller.engine.last.function == 'inc'
    assert {key[0] for key in window.visuals.boxes} == {'x'}
    assert all(box.brush().color().name() == '#f3e8ff' for box in window.visuals.boxes.values())
    window.pause()
    count = window.controller.engine.count
    window.on_tick()
    assert window.controller.engine.count == count
    window.play()
    tick_until_paused(window)
    assert window.controller.state == 'paused'
    assert window.controller.engine.runtime.snapshot()['b']['value'] == 4
    assert {key[0] for key in window.visuals.boxes} == {'a', 'b'}
    assert all(box.brush().color().name() == '#dcfce7' for box in window.visuals.boxes.values())
    window.close()


def test_gutter_call_click_starts_detailed_playback_without_moving_cursor(app):
    window = MainWindow()
    window.load_code(SOURCE, [])
    cursor = window.editor.textCursor().position()
    window.play_line(8)
    tick_until_paused(window)
    assert window.controller.engine.last.expanded
    assert window.controller.engine.runtime.snapshot()['b']['value'] == 4
    assert window.editor.textCursor().position() == cursor
    window.reset()
    assert 'inc' in window.visuals.function_boxes
    window.close()


def test_first_statement_call_offers_expansion_before_plain_step(app):
    window = MainWindow()
    window.load_code('int inc(int x){return x+1;}\nint main(){int a=inc(3);}', [])
    window.step()
    assert not window.function_offer.isHidden()
    assert window.controller.engine.count == 0
    window.step()
    assert window.controller.engine.last.calls
    assert not window.controller.engine.last.expanded
    assert window.controller.engine.runtime.snapshot()['a']['value'] == 4
    window.stop(); window.close()
