import pytest

from cvisualizer.engine import Engine
from cvisualizer.language import CError
from cvisualizer.controller import Controller


def run(source):
    engine = Engine(source)
    while engine.peek():
        engine.step()
    return engine


def test_define_array_size_and_expression_macro():
    e = run('#define N 3\n#define SQUARE(x) ((x)*(x))\nint a[N];\nfor(int i=0;i<N;i++){a[i]=SQUARE(i+1);}')
    assert e.runtime.snapshot()['a']['value'] == [1, 4, 9]


def test_nested_macros_and_constant_expression_dimensions():
    e = run('#define BASE 2\n#define N (BASE+1)\n#define ADD(x,y) ((x)+(y))\nint a[N]={ADD(1, ADD(2,3))};')
    assert e.runtime.snapshot()['a']['value'] == [6, 0, 0]


def test_expansion_preserves_text_replacement_precedence_and_strings():
    e = run('#define N 1+2\nint NN=3; int x=3*N; printf("N=%d", NN); // N\n')
    assert e.runtime.snapshot()['x']['value'] == 5
    assert e.runtime.output == 'N=3'


def test_define_undef_and_definition_order():
    e = run('#define X 2\nint a=X;\n#undef X\n#define X 4\nint b=X;')
    assert e.runtime.snapshot()['a']['value'] == 2
    assert e.runtime.snapshot()['b']['value'] == 4


def test_continuations_and_multiline_arguments():
    e = run('#define SUM(x,y) ((x) + \\\n(y))\nint x=SUM(\n2,\n3);\nint y=4;')
    assert e.runtime.snapshot()['x']['value'] == 5
    assert e.last.line == 6


def test_macro_expansion_keeps_later_statement_original_column_for_seek():
    source = '#define LONG_NAME 123456789\nint x=LONG_NAME; x++;'
    c = Controller(source)
    target = next(t for t in c.targets if t.text == 'x++')
    assert target.column == source.splitlines()[1].index('x++') + 1
    c.seek(target)
    c.tick()
    assert c.state == 'paused'
    assert c.engine.runtime.snapshot()['x']['value'] == 123456789


def test_error_in_macro_points_to_invocation():
    e = Engine('#define BAD (1/0)\n\nint x=BAD;')
    with pytest.raises(CError) as error:
        e.step()
    assert error.value.line == 3
    assert error.value.column == 7


@pytest.mark.parametrize('source', [
    '#define A B\n#define B A\nint x=A;',
    '#define F(x) ((x)+1)\nint y=F(1,2);',
    '#define F(x) #x\nint y=1;', '#define F(x,y) x##y\nint y=1;',
    '#if 1\nint x=1;\n#endif', '#define F(...) 1\nint x=F(1);',
])
def test_invalid_or_unsupported_macros_are_controlled_errors(source):
    with pytest.raises(CError):
        run(source)


@pytest.mark.parametrize('header', ['cstdlib', 'stdlib.h'])
def test_stdlib_header_abs_and_rand_range(header):
    e = run(f'#include <{header}>\nint x=abs(-7); srand(42); int r=rand(); int max=RAND_MAX;')
    v = e.runtime.snapshot()
    assert v['x']['value'] == 7
    assert 0 <= v['r']['value'] <= v['max']['value'] == 32767


def test_seed_repeatability_and_reset():
    source = '#include <cstdlib>\nsrand(7); int a=rand(); int b=rand(); srand(7); int c=rand();'
    a, b = run(source), run(source)
    assert a.runtime.snapshot() == b.runtime.snapshot()
    assert a.runtime.snapshot()['a']['value'] == a.runtime.snapshot()['c']['value']


@pytest.mark.parametrize('source', ['int x=abs(-2147483648);', 'int x=abs(1.5);',
                                   'rand(1);', 'srand();', 'int x=srand(1);'])
def test_stdlib_signature_type_and_range_checks(source):
    with pytest.raises(CError):
        run(source)


def test_macro_tokens_do_not_merge_into_a_new_operator():
    e = run('#define NEG(x) -x\nint a=NEG(-1);')
    assert e.runtime.snapshot()['a']['value'] == 1


@pytest.mark.parametrize('source', ['if(srand(1)){}', 'int x=!srand(1);',
                                   'int x=-srand(1);', 'int x=srand(1)&&0;'])
def test_void_function_cannot_be_used_as_a_condition_or_unary_operand(source):
    with pytest.raises(CError):
        run(source)


def test_deep_macro_with_empty_argument_reports_controlled_error():
    with pytest.raises(CError):
        run('#define F(x) x\nint x=' + 'F('*33 + ')'*33 + ';')


@pytest.mark.parametrize('header', ['<cstdlib"', '"stdlib.h>'])
def test_include_requires_matching_delimiters(header):
    with pytest.raises(CError):
        run(f'#include {header}\nint x=1;')


def test_failed_statement_restores_random_generator():
    engine = Engine('srand(7); int x = rand() / 0;')
    engine.step()
    seed = engine.runtime.random_state
    with pytest.raises(CError):
        engine.step()
    assert engine.runtime.random_state == seed
