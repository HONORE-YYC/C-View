from cvisualizer.views import MemoryView
from cvisualizer.arrays import Array


def members():
    return {
        'p': {'value': object(), 'type': 'struct Point', 'identity': 1, 'declaration': ('p', 1, 1), 'is_struct': True},
        'p.x': {'value': 3, 'type': 'int', 'identity': 2, 'declaration': ('p.x', 1, 1), 'struct_owner': 'Point', 'struct_root': 'p'},
        'p.y': {'value': None, 'type': 'int', 'identity': 3, 'declaration': ('p.y', 1, 1), 'struct_owner': 'Point', 'struct_root': 'p'},
        'count': {'value': 1, 'type': 'int', 'identity': 4, 'declaration': ('count', 2, 1)},
    }


def test_struct_definition_then_function_then_fields_with_owner(app):
    view = MemoryView()
    view.resize(900, 700)
    view.render(members(), [], functions=['move'], structures=['Point'], animate=False)
    structure = view.structure_boxes['Point']
    function = view.function_boxes['move']
    field = view.boxes['p.x', None, 2]
    assert structure.rect().top() < function.rect().top() < field.rect().top()
    assert structure.brush().color().name() == '#fee2e2'
    assert structure.pen().color().name() == '#dc2626'
    assert field.brush().color().name() == '#dcfce7'
    assert view.boxes['p.y', None, 3].brush().color().name() == '#e5e7eb'
    assert ('p', None, 1) not in view.boxes
    assert field.owner_label.toPlainText() == 'Point'
    assert field.owner_label.defaultTextColor().name() == '#dc2626'
    assert field.owner_label.sceneBoundingRect().bottom() <= field.value_label.sceneBoundingRect().top()+2
    view.set_dark_mode(True)
    assert structure.brush().color().name() == '#fee2e2'
    assert field.owner_label.defaultTextColor().name() == '#dc2626'
    view.close()


def test_struct_array_member_has_owner_on_each_card_and_survives_redraw(app):
    view = MemoryView()
    view.resize(900, 700)
    cell = {'value': Array(3, 0), 'type': 'int', 'identity': 2, 'declaration': ('s.data', 1, 1), 'struct_owner': 'Stack', 'struct_root': 's'}
    view.render({'s.data': cell}, [], structures=['Stack'], animate=False)
    assert all(view.boxes['s.data', i, 2].owner_label.toPlainText() == 'Stack' for i in range(3))
    view.render(*view._data, animate=False, force=True)
    assert 'Stack' in view.structure_boxes
    assert view.boxes['s.data', 0, 2].owner_label.defaultTextColor().name() == '#dc2626'
    view.close()


def test_pointer_to_structure_targets_visible_member(app):
    from cvisualizer.engine import Engine
    engine = Engine('struct Pair{int x;int y;};struct Pair p={1,2};struct Pair *q=&p;')
    while engine.peek():
        engine.step()
    snapshot = engine.runtime.snapshot()
    view = MemoryView()
    view.resize(900, 700)
    view.render(snapshot, [], structures=engine.program.structure_names, animate=False)
    marker = view.motion.pointers['address', snapshot['q']['identity']]
    assert marker.isVisible()
    assert view._marker_targets['address', snapshot['q']['identity']][0] == 'p.x'
    view.close()


def test_real_struct_copy_connects_matching_visible_members(app):
    from cvisualizer.engine import Engine
    engine = Engine('typedef struct P{int x;int y;}P;int main(){P a={1,2};P b;b=a;}')
    view = MemoryView()
    view.resize(900, 700)
    while engine.peek():
        event = engine.step()
        view.render(event.variables, [], event, structures=engine.program.structure_names)
        if engine.peek():
            view.motion.finish()
    assert len(view.motion.arrows) == 2
    assert all(source[0].split('.')[-1] == target[0].split('.')[-1] for source,target in event.transfers)
    assert view.boxes['b.x', None, event.variables['b.x']['identity']].owner_label.toPlainText() == 'P'
    view.motion.finish()
    view.close()


def test_sparse_struct_array_only_draws_materialized_members(app):
    from cvisualizer.engine import Engine
    engine = Engine('struct P{int x;};struct P a[1000000];a[999999].x=7;')
    while engine.peek():
        engine.step()
    view = MemoryView()
    view.resize(900, 700)
    view.render(engine.runtime.snapshot(), [], structures=engine.program.structure_names, animate=False)
    assert len(view.scene().items()) < 100
    assert any(key[0] == 'a[999999].x' for key in view.boxes)
    assert not any(key[0] == 'a' for key in view.boxes)
    view.close()
