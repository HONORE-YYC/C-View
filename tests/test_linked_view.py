from types import SimpleNamespace
from PySide6.QtCore import QPointF
from cvisualizer.pointers import Pointer
from cvisualizer.views import MemoryView


def snapshot(edges):
    result = {}
    for identity, target in edges.items():
        name = f'n{identity}'
        result[name] = dict(value=object(), type='struct N', identity=identity, is_struct=True,
                            linked_node={'data': 'payload', 'next': 'tail'})
        result[name+'.payload'] = dict(value=identity*10, type='int', identity=identity*10+1, struct_root=name)
        result[name+'.tail'] = dict(value=Pointer(target, None, 'struct N', 'renamed') if target is not ... else None,
                                  type='struct N*', identity=identity*10+2, struct_root=name)
    result['head'] = dict(value=Pointer(next(iter(edges), None), None, 'struct N', 'alias'), type='struct N*', identity=99999)
    return result


def event(before, after):
    return SimpleNamespace(before=before, variables=after, function='', text='next = node', writes=[], reads=[], calls=[], transfers=[], expanded=False)


def test_linked_identity_edges_aliases_and_member_suppression(app):
    view = MemoryView(); view.resize(900, 500)
    cells = snapshot({1: 2, 2: None, 3: ..., 4: 404})
    view.render(cells, [], animate=False)
    layer = view.linked_layer
    assert set(layer.nodes) == {1, 2, 3, 4}
    assert layer.model[1]['target'] == 2
    assert layer.model[2]['status'] == 'NULL'
    assert layer.model[3]['status'] == '未初始化'
    assert layer.model[4]['status'] == '悬空'
    assert 'head' in layer.model[1]['aliases']
    assert view.boxes['n1.payload', None, 11].parentItem() is layer.nodes[1]
    assert not any(key[0] == 'n1.tail' for key in view.boxes)
    assert layer.nodes[1].pen().color().name() == '#dc2626'
    view.set_dark_mode(True)
    assert layer.nodes[1].brush().color().name() == '#fee2e2'
    view.close()


def test_linked_motion_creation_deletion_pause_and_finish(app):
    view = MemoryView(); view.resize(900, 500)
    before = snapshot({1: 2, 2: None}); after = snapshot({1: 3, 3: 2, 2: None})
    view.render(before, [], animate=False)
    view.render(after, [], event(before, after), duration=10000)
    view.motion.pause(); view.motion.frame(0)
    layer = view.linked_layer
    assert layer.nodes[3].opacity() == 0
    origin = QPointF(layer.nodes[2].pos())
    view.motion.frame(.5)
    assert 0 < layer.nodes[3].opacity() < 1
    assert layer.nodes[2].pos() != origin
    view.motion.finish()
    assert layer.nodes[3].opacity() == 1
    removed = snapshot({1: 2, 2: None})
    view.render(removed, [], event(after, removed), duration=10000)
    view.motion.pause(); view.motion.frame(.5)
    assert 3 in view.linked_layer.nodes
    assert 0 < view.linked_layer.nodes[3].opacity() < 1
    view.motion.finish()
    assert not view.linked_layer.nodes[3].isVisible()
    view.close()


def test_linked_large_list_bounded_and_scroll_stable(app):
    view = MemoryView(); view.resize(900, 400)
    cells = snapshot({i: i+1 if i < 3000 else None for i in range(1, 3001)})
    view.render(cells, [], animate=False)
    assert len(view.scene().items()) < 500
    view.array_scroll.setValue(1200)
    offset = view.array_scroll.value()
    view.render(cells, [], animate=False, force=True)
    assert view.array_scroll.value() == offset
    assert len(view.scene().items()) < 500
    view.close()

def test_cycle_shared_tail_and_ordinary_struct_fallback(app):
    view = MemoryView(); view.resize(900, 500)
    cells = snapshot({1: 2, 2: 1, 3: 2})
    cells['other'] = dict(value=object(), type='struct P', identity=800, is_struct=True)
    cells['other.x'] = dict(value=7, type='int', identity=801, struct_root='other')
    view.render(cells, [], animate=False)
    assert len(view.linked_layer.edges) == 3
    assert view.linked_layer.model[2]['target'] == 1
    assert ('other.x', None, 801) in view.boxes
    view.render({}, [], animate=False)
    assert not view.linked_layer.nodes
    assert not view.motion.busy
    view.close()


def test_linked_summary_reveals_topology_with_effects(app):
    view = MemoryView(); view.resize(900, 500)
    before = snapshot({1: None}); after = snapshot({1: 2, 2: None})
    step = event(before, after)
    step.calls = [dict(name='insert', inputs=[], **{'return': None})]
    view.render(before, [], animate=False)
    view.render(after, [], step, duration=10000)
    view.motion.pause()
    view.motion.frame(.4)
    assert view.linked_layer.nodes[2].opacity() == 0
    view.motion.frame(.84)
    assert 0 < view.linked_layer.nodes[2].opacity() < 1
    view.motion.finish()
    assert view.linked_layer.nodes[2].opacity() == 1
    view.close()


def test_real_linked_runtime_snapshot_and_data_transfer(app):
    from cvisualizer.engine import Engine
    engine = Engine('typedef struct Item {int data; struct Item *next;} Item; int main(){Item *head=new Item();head->data=7;head->next=0;}')
    view = MemoryView(); view.resize(900, 500)
    while engine.peek():
        step = engine.step()
        view.render(step.variables, [], step)
        if 'head->data' in step.text:
            assert len(view.motion.arrows) == len(step.transfers)
        view.motion.finish()
    nodes = view.linked_layer.model
    assert len(nodes) == 1
    assert next(iter(nodes.values()))['data'] == 7
    view.close()

def test_alias_traversal_moves_between_actual_identity_nodes(app):
    view = MemoryView(); view.resize(900, 500)
    before = snapshot({1: 2, 2: None}); after = dict(before)
    after['head'] = dict(before['head'], value=Pointer(2, None, 'struct N', 'unchanged'))
    view.render(before, [], animate=False)
    view.render(after, [], event(before, after), duration=10000)
    view.motion.pause(); view.motion.frame(0)
    alias = view.linked_layer.aliases['head'][0]
    start = QPointF(alias.pos())
    view.motion.frame(.5)
    assert alias.pos() != start
    middle = QPointF(alias.pos())
    view.motion.finish()
    assert alias.pos() != middle
    view.close()


def test_nested_linked_members_only_draw_in_nodes(app):
    view = MemoryView(); view.resize(900, 500)
    cells = snapshot({1: None})
    for suffix in ['', '.payload', '.tail']:
        cells['obj.node'+suffix] = cells.pop('n1'+suffix)
        cells['obj.node'+suffix]['struct_root'] = 'obj'
    view.render(cells, [], animate=False)
    assert ('obj.node.payload', None, 11) in view.boxes
    assert getattr(view.boxes['obj.node.payload', None, 11], '_linked', False)
    assert ('obj.node.tail', None, 12) not in view.boxes
    view.close()

def test_transfer_arrow_tracks_moving_linked_data_card(app):
    view = MemoryView(); view.resize(900, 500)
    before = snapshot({1: 2, 2: None}); after = snapshot({1: 3, 3: 2, 2: None})
    for cells in [before, after]:
        cells['value'] = dict(value=7, type='int', identity=100001)
    step = event(before, after)
    step.transfers = [(('value', None, 100001), ('n2.payload', None, 21))]
    view.render(before, [], animate=False)
    view.render(after, [], step, duration=10000)
    view.motion.pause()
    arrow = view.motion.arrows[0]
    view.motion.frame(.25)
    start = arrow.route.pointAtPercent(1)
    view.motion.frame(.5)
    assert arrow.route.pointAtPercent(1) != start
    view.close()

def test_external_node_labels_follow_dark_theme_contrast(app):
    view = MemoryView(); view.resize(900, 500)
    view.render(snapshot({1: None}), [], animate=False)
    view.set_dark_mode(True)
    card = view.linked_layer.nodes[1]
    assert card.name_label.defaultTextColor().name() == '#ffffff'
    assert card.alias_label.defaultTextColor().name() == '#ffffff'
    assert card.next_label.defaultTextColor().name() == '#991b1b'
    view.close()

def assert_edges_clear(layer):
    for source, spec, _, _, edge in layer.edges:
        if edge.opacity() < .01:
            continue
        for identity, card in layer.nodes.items():
            if identity in (source, spec['target']) or card.opacity() < .01:
                continue
            rect = card.mapRectToParent(card.rect()).adjusted(.5, .5, -.5, -.5)
            for sample in range(401):
                assert not rect.contains(edge.path().pointAtPercent(sample/400)), (source, identity, sample)


def test_compact_layout_and_clear_routes_during_topology_changes(app):
    view = MemoryView(); view.resize(900, 500)
    variants = [snapshot({i: i+1 if i < 10 else None for i in range(1, 11)}),
                snapshot({1: 20, 20: 2, **{i: i+1 if i < 10 else None for i in range(2, 11)}}),
                snapshot({1: 2, 2: 9, **{i: i+1 if i < 10 else 1 for i in range(3, 11)}})]
    view.render(variants[0], [], animate=False)
    assert view.linked_layer.nodes[1].rect().width() <= 90
    assert view.linked_layer.nodes[1].rect().height() <= 42
    for before, after in zip(variants, variants[1:]+variants[:1]):
        view.render(after, [], event(before, after), duration=10000)
        view.motion.pause()
        for progress in (index/20 for index in range(21)):
            view.motion.frame(progress)
            assert_edges_clear(view.linked_layer)
        view.motion.finish()
    view.close()


def test_thirty_linked_nodes_redraw_when_scrolled(app):
    view = MemoryView(); view.resize(500, 260)
    cells = snapshot({i: i+1 if i < 30 else None for i in range(1, 31)})
    view.render(cells, [], animate=False)
    view.array_scroll.setValue(view.array_scroll.maximum())
    app.processEvents()
    assert 30 in view.linked_layer.nodes
    assert view.linked_layer.nodes[30].isVisible()
    view.close()


def test_head_order_hidden_nodes_and_heap_tooltips(app):
    from cvisualizer.linked_visuals import node_model, layout
    cells = snapshot({3: None, 1: 2, 2: 3, 4: None})
    cells['n1']['linked_head'] = True
    cells['head']['value'] = Pointer(1, None, 'struct N', 'alias')
    cells['n4']['linked_hidden'] = True
    model = node_model(cells)
    assert 4 not in model
    positions, _ = layout(model, 600, 100)
    assert positions[1].x() < positions[2].x() < positions[3].x()
    view = MemoryView(); view.resize(900, 500)
    cells['堆#9'] = cells.pop('n1')
    cells['堆#9.payload'] = cells.pop('n1.payload')
    cells['堆#9.tail'] = cells.pop('n1.tail')
    view.render(cells, [], animate=False)
    card = view.linked_layer.nodes[1]
    assert '堆#9' not in card.name_label.toPlainText()
    assert '堆#9' in card.toolTip()
    view.close()


def test_narrow_canvas_keeps_three_compact_columns():
    from cvisualizer.linked_visuals import layout, node_model
    positions, _ = layout(node_model(snapshot({1: 2, 2: 3, 3: 4, 4: None})), 380, 100)
    assert positions[1].y() == positions[2].y() == positions[3].y()
    assert positions[4].y() > positions[3].y()
    assert positions[4].x() == positions[1].x()

def test_linked_nested_nodes_coexist_with_scalar_array_addresses_and_green_transfers(app):
    view = MemoryView(); view.resize(900, 600); view.show(); app.processEvents()
    before = snapshot({1: None})
    for suffix in ('', '.payload', '.tail'):
        before['holder.node'+suffix] = before.pop('n1'+suffix)
        before['holder.node'+suffix]['struct_root'] = 'holder'
    before.update(value=dict(value=7, type='int', identity=700),
                  arr=dict(value=[1, 2], type='int[2]', identity=800),
                  scalar_address=dict(value=Pointer(700, None, 'int', 'value'), type='int*', identity=701),
                  array_address=dict(value=Pointer(800, 0, 'int', 'arr'), type='int*', identity=801))
    after = dict(before)
    after['value'] = dict(before['value'], value=10)
    step = event(before, after)
    step.transfers = [(('holder.node.payload', None, 11), ('value', None, 700)),
                      (('value', None, 700), ('arr', 0, 800))]
    view.render(before, [], animate=False)
    view.render(after, [], step, duration=10000)
    view.motion.pause(); view.motion.frame(.5)
    assert ('address', 701) in view.motion.pointers
    assert ('address', 801) in view.motion.pointers
    assert len(view.motion.arrows) == 2
    assert all(arrow.pen().color().name() == '#16a34a' for arrow in view.motion.arrows)
    assert ('holder.node.payload', None, 11) in view.boxes
    view.close()
