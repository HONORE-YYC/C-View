import pytest


def test_function_definition_parameter_tag_is_visible_in_body():
    from cvisualizer.language import Program
    Program('int f(struct P{int x;} p){struct P q=p;return q.x;} int main(){return 0;}')


def test_prototype_parameter_tag_does_not_escape_to_file_scope():
    from cvisualizer.language import Program, CError
    with pytest.raises(CError, match='不完整'):
        Program('int f(struct P{int x;} p); struct P q; int main(){return 0;}')


@pytest.mark.parametrize('source', [
    'int main(){int n=2;typedef int A[n++];A a;A b;}',
    'int n=2;struct P{int a[n];};int main(){return 0;}',
    'int main(){int n=2;struct P{int a[n];};}',
])
def test_dynamic_alias_and_member_array_capacities_are_rejected(source):
    from cvisualizer.language import Program, CError
    with pytest.raises(CError,match='常量'):
        Program(source)


def test_constant_expression_and_omitted_alias_array_capacity():
    from cvisualizer.language import Program
    Program('typedef int A[1+2];typedef int B[];struct P{int data[2*3];};int main(){A a;B b={1,2};}')
from pycparser import c_ast as ast
from cvisualizer.language import Program, CError


def test_aliases_preserve_declarator_binding_and_const():
    p = Program('typedef int A[3]; typedef A B; typedef int *P; int main(){ B a; const P ptr=0; return 0;}')
    a, ptr = p.main.block_items[:2]
    assert isinstance(a.type, ast.ArrayDecl)
    assert p._scalar_type(a.type.type) == 'int'
    assert isinstance(ptr.type, ast.PtrDecl) and 'const' in ptr.type.quals
    assert 'const' not in ptr.type.type.quals


def test_scoped_aliases_and_structure_tags():
    p = Program('typedef int T; struct S {int x;}; int main(){T a; {typedef double T; struct S {double x;}; T b; struct S s;} T c; struct S s;}')
    inner = p.main.block_items[1]
    assert p._scalar_type(inner.block_items[2].type) == 'double'
    assert p._scalar_type(p.main.block_items[2].type) == 'int'
    assert p._scalar_type(inner.block_items[3].type) != p._scalar_type(p.main.block_items[3].type)


def test_structs_anonymous_nested_array_and_self_pointer():
    p = Program('typedef struct {int x; int a[2];} Point; struct Node {Point point; struct Node *next;}; int main(){struct Node n; n.point.x=1; return n.point.x;}')
    assert p.structure_names == ['Point', 'Node']
    node = p.structs['struct Node']
    assert [f.name for f in node.fields] == ['point', 'next']
    assert p.structs[p._scalar_type(node.fields[0].type)].name == 'Point'
    assert p._scalar_type(node.fields[1].type) == 'struct Node*'


def test_declaration_location_keeps_alias_spelling():
    p = Program('typedef int Number; int main(){ Number n=1; return n;}')
    assert p.location(p.main.block_items[0]).text == 'Number n = 1'


@pytest.mark.parametrize('body', ['union U {int x;} u;', 'struct S {int x:2;};', 'struct S {int a[];};', 'typedef int (*F)(int);', 'struct S {struct S self;};', 'struct S; struct S s;'])
def test_unsupported_or_incomplete_aggregates_fail(body):
    with pytest.raises(CError):
        Program(body + ' int main(){return 0;}')


def test_field_named_like_builtin_is_valid():
    Program('struct S {int printf;}; int main(){struct S s; s.printf=1; return s.printf;}')


def test_forward_tag_can_complete_and_support_pointer_alias():
    p = Program('typedef struct Node Node; struct Node {int x; Node *next;}; int main(){Node n; return 0;}')
    assert p._scalar_type(p.main.block_items[0].type) == 'struct Node'
    assert p._scalar_type(p.structs['struct Node'].fields[1].type) == 'struct Node*'


@pytest.mark.parametrize('source', [
    'struct S; struct S s; struct S {int x;}; int main(){return 0;}',
    'struct S; struct S f(){return 0;} int main(){return 0;}',
    'int n; struct S {int a[n];}; int main(){return 0;}',
    'struct S {unsigned x;}; int main(){return 0;}',
    'typedef int F(int); int main(){return 0;}',
    'typedef int A[2]; A *p; int main(){return 0;}',
])
def test_invalid_types_rejected_before_execution(source):
    with pytest.raises(CError):
        Program(source)


def test_alias_chain_and_const_array_element_type():
    p = Program('typedef int A[2]; typedef A B; int main(){const B a={1,2}; return a[0];}')
    assert p.main.block_items[0].type.type.quals == ['const']


def test_named_structure_keeps_tag_display_when_typedef_has_other_name():
    p = Program('typedef struct Tag {int x;} Alias; int main(){Alias a; return 0;}')
    assert p.structure_names == ['Tag']
    assert p.structs['struct Tag'].name == 'Tag'
