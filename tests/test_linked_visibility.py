from cvisualizer.engine import Engine

PREFIX = 'struct N{int x;struct N *next;};'


def events(body, detail=False):
    engine = Engine(PREFIX + body)
    result = []
    while engine.peek():
        result.append(engine.step(expand_calls=detail))
    return engine, result


def nodes(event):
    return [c for c in event.variables.values() if c.get('linked_node')]


def test_unused_orphan_hides_next_event_without_freeing():
    engine, trace = events('int main(){struct N *head=0;struct N *p=new N();int x=1;int y=2;}')
    trace = [e for e in trace if nodes(e)]
    assert not nodes(trace[0])[0]['linked_hidden']
    assert nodes(trace[1])[0]['linked_hidden']
    assert len(engine.runtime.heap) == 1 and not engine.runtime.freed
    assert nodes(trace[2])[0]['identity'] in {c['identity'] for c in engine.runtime.snapshot().values()}


def test_future_insert_preserves_orphan_and_tracks_head_cell():
    engine, trace = events('int main(){struct N *head;struct N *p=new N();int x=1;head=p;int y=2;}')
    assert all(not c['linked_hidden'] for e in trace for c in nodes(e))
    assert nodes(trace[-1])[0]['linked_head']
    assert nodes(trace[-1])[0]['identity'] == engine.display_snapshot()['p']['value'].identity


def test_reused_loop_pointer_kills_old_allocation():
    _, trace = events('int main(){struct N *head=0;struct N *p=0;for(int i=0;i<2;i++){p=new N();p->x=i;}int done=1;}')
    second = next(e for e in trace if len(nodes(e)) == 2)
    old = min(nodes(second), key=lambda c: c['identity'])
    assert old['linked_hidden']
    assert not max(nodes(second), key=lambda c: c['identity'])['linked_hidden']


def test_custom_function_and_global_reads_keep_future_nodes():
    _, trace = events('struct N *head=0;struct N *global=0;void renamed(){global->x=4;}int main(){global=new N();int x=1;renamed();int y=2;}', True)
    before_call = next(e for e in trace if e.text.startswith('int x'))
    assert not nodes(before_call)[0]['linked_hidden']


def test_detail_preserves_callers_future_insert():
    _, trace = events('void custom(){int a=1;int b=2;}int main(){struct N *head=0;struct N *p=new N();custom();head=p;}', True)
    detail = [e for e in trace if e.function]
    assert detail and all(not c['linked_hidden'] for e in detail for c in nodes(e))


def test_display_refresh_does_not_age_orphans_and_ordinary_struct_unaffected():
    engine = Engine(PREFIX + 'struct Other{int x;int y;};int main(){struct N *head=0;struct N *p=new N();struct Other o;}')
    while not any(c.get('linked_node') for c in engine.display_snapshot().values()):
        engine.step()
    for _ in range(5):
        assert not next(c for c in engine.display_snapshot().values() if c.get('linked_node'))['linked_hidden']
    event = engine.step()
    assert 'linked_hidden' not in event.variables['o']


def test_input_cancel_does_not_age_display_state():
    import pytest
    from cvisualizer.formatted_io import InputCancelled
    engine = Engine(PREFIX + 'int main(){struct N *head=0;struct N *p=new N();int x;scanf("%d",&x);}')
    while not engine.peek().location.text.startswith('scanf'):
        engine.step()
    before = engine.display_snapshot()
    with pytest.raises(InputCancelled):
        engine.step()
    assert engine.display_snapshot() == before

def test_broken_unused_head_follows_same_orphan_grace():
    _, trace = events('int main(){struct N *head=new N;int a=1;int b=2;}')
    trace = [e for e in trace if nodes(e)]
    assert nodes(trace[0])[0]['linked_head']
    assert not nodes(trace[0])[0]['linked_hidden']
    assert nodes(trace[1])[0]['linked_hidden']


def test_cycle_is_incomplete_but_future_read_keeps_it():
    _, trace = events('int main(){struct N *head=new N();head->next=head;int a=1;int b=head->x;int c=2;}')
    observed = next(e for e in trace if e.text.startswith('int a'))
    assert not nodes(observed)[0]['linked_hidden']
    assert nodes(trace[-1])[0]['linked_hidden']


def test_live_struct_member_pointer_preserves_target():
    _, trace = events('struct Holder{struct N *slot;int extra;};int main(){struct N *head=0;struct N *p=new N();struct Holder h;h.slot=p;int a=1;int b=1;h.slot->x=5;}')
    for prefix in ('int a', 'int b'):
        event = next(e for e in trace if e.text.startswith(prefix))
        assert not nodes(event)[0]['linked_hidden']


def test_branch_future_read_and_completed_link_restore_visibility():
    _, trace = events('int main(){struct N *head=0;struct N *p=new N();int choose=1;if(choose){p->x=3;}head=p;int a=1;}')
    assert all(not c['linked_hidden'] for e in trace for c in nodes(e))
    assert nodes(trace[-1])[0]['linked_head']


def test_hidden_metadata_persists_in_next_before_snapshot():
    _, trace = events('int main(){struct N *head=0;struct N *p=new N();int a=1;int b=2;int c=3;}')
    last = trace[-1]
    assert nodes(last)[0]['linked_hidden']
    assert next(c for c in last.before.values() if c.get('linked_node'))['linked_hidden']


def test_fast_function_first_pointer_declaration_remains_canonical_head():
    engine, trace = events('void custom(){struct N *first=0;}int main(){custom();struct N *later=new N();int a=1;}')
    assert not nodes(trace[-1])[0]['linked_head']


def test_future_array_capacity_reads_pointer():
    _, trace = events('int main(){struct N *head=0;struct N *p=new N();p->x=2;int a=1;int values[p->x];}')
    event = next(e for e in trace if e.text.startswith('int a'))
    assert not nodes(event)[0]['linked_hidden']


def test_last_read_keeps_node_for_current_observable_event():
    _, trace = events('int main(){struct N *head=0;struct N *p=new N();int a=1;int value=p->x;int done=1;}')
    read = next(e for e in trace if e.text.startswith('int value'))
    assert not nodes(read)[0]['linked_hidden']
    assert nodes(trace[-1])[0]['linked_hidden']


def test_custom_function_entry_retains_parameter_future_access():
    _, trace = events('void use(struct N *q){int gap=0;q->x=7;}int main(){struct N *head=0;struct N *p=new N();int gap=0;use(p);int done=0;}', True)
    entry = next(e for e in trace if e.function == 'use' and e.kind == 'function')
    assert nodes(entry) and all(not c['linked_hidden'] for c in nodes(entry))


def test_custom_function_entry_retains_global_only_future_access():
    _, trace = events('struct N *head=0;struct N *global=0;void use(){int gap=0;global->x=7;}int main(){global=new N();int gap=0;use();int done=0;}', True)
    entry = next(e for e in trace if e.function == 'use' and e.kind == 'function')
    assert nodes(entry) and all(not c['linked_hidden'] for c in nodes(entry))


def test_nested_custom_function_entries_retain_future_access():
    _, trace = events('void inner(struct N *target){int gap=0;target->x=7;}void outer(struct N *q){int gap=0;inner(q);}int main(){struct N *head=0;struct N *p=new N();int gap=0;outer(p);int done=0;}', True)
    entries = [e for e in trace if e.function and e.kind == 'function']
    assert {e.function for e in entries} == {'outer', 'inner'}
    assert all(nodes(e) and all(not c['linked_hidden'] for c in nodes(e)) for e in entries)


def test_shadowed_pointer_keeps_outer_future_target():
    _, trace = events('int main(){struct N *head=0;struct N *p=new N();int gap=0;{int p=1;p=2;int v=2;}p->x=7;}')
    assert all(not c['linked_hidden'] for e in trace for c in nodes(e))


def test_loop_shadow_keeps_outer_future_target():
    _, trace = events('int main(){struct N *head=0;struct N *p=new N();int gap=0;for(int p=0;p<2;p++){int v=2;}p->x=7;}')
    assert all(not c['linked_hidden'] for e in trace for c in nodes(e))


def test_global_initializers_keep_future_pointer_reads():
    _, trace = events('struct N *head=0;struct N *p=new N();int gap=0;struct N *q=p;int main(){q->x=7;}')
    assert all(not c['linked_hidden'] for e in trace for c in nodes(e))


def test_hidden_node_member_is_not_a_visible_alias():
    from cvisualizer.linked_visuals import node_model
    _, trace = events('int main(){struct N *head=new N();struct N *p=new N();p->next=head;int gap=0;}')
    model = node_model(trace[-1].variables)
    assert len(model) == 1
    assert next(iter(model.values()))['aliases'] == ['head']
