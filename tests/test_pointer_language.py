import pytest
from pycparser import c_ast as ast

from cvisualizer.language import CError, Program
from cvisualizer.preprocessor import Preprocessor


@pytest.mark.parametrize('base', ['int', 'float', 'double'])
def test_numeric_pointer_variables_parameters_and_returns(base):
    program = Program(f'''{base} global=1;
{base} *address=&global;
{base} *identity({base} *p);
{base} *identity({base} *p) {{ *p=p[0]; return &p[0]; }}
int main(void) {{ {base} data[2]={{1,2}}; {base} *p=data;
  p=identity(p); p++; p--; p+=1; p-=1;
  return p==address || p<address || *(p+1)>0;
}}''')
    assert isinstance(program.globals[1].type, ast.PtrDecl)
    assert isinstance(program.functions['identity'].params[0].type, ast.PtrDecl)
    assert program.functions['identity'].return_type == base + '*'


@pytest.mark.parametrize('prototype,definition', [
    ('int *', 'int a[]'), ('int []', 'int *a'),
])
def test_array_and_pointer_parameter_declarations_are_compatible(prototype, definition):
    Program(f'int f({prototype}); int f({definition}){{return a[0];}} int main(){{return 0;}}')


@pytest.mark.parametrize('declaration', [
    'int **p;', 'void *p;', 'int *p[2];', 'int (*p)[2];', 'int (*p)(int);',
    'restrict int *p;', 'int *static p;', 'struct A {int x;};', 'typedef int number;',
])
def test_unsupported_pointer_shapes_and_types_are_rejected(declaration):
    with pytest.raises(CError):
        Program(declaration + ' int main(){return 0;}')


@pytest.mark.parametrize('signature', [
    'int **f(void)', 'void *f(void)', 'int *f(int **p)',
    'int *f(int *p[2])', 'int *f(int (*p)[2])', 'int *f(int (*p)(int))',
    'int *f(void *p)', 'int *f(restrict int p)', 'int *f(int *static p)',
    'int *main(void)',
])
def test_unsupported_pointer_function_signatures_are_rejected(signature):
    with pytest.raises(CError):
        Program(signature + '{return 0;} int main(){return 0;}')


@pytest.mark.parametrize('header', ['stdio.h', 'stdlib.h', 'cstdlib', 'stddef.h'])
def test_null_macro_is_provided_by_supported_headers(header):
    program = Program(f'#include <{header}>\nint *p=NULL;')
    initializer = program.main.block_items[0].init
    assert isinstance(initializer, ast.Constant)
    assert initializer.value == '0'


def test_null_is_an_ordinary_header_macro_with_undef_and_redefinition():
    output = Preprocessor().process('''int before=NULL;
#include <stdio.h>
int first=NULL;
#undef NULL
int absent=NULL;
#define NULL 7
int changed=NULL;
''').text
    assert output.splitlines() == ['int before = NULL ;', '', 'int first = 0 ;', '',
                                   'int absent = NULL ;', '', 'int changed = 7 ;']
    with pytest.raises(CError, match='重复定义'):
        Preprocessor().process('#include <stdio.h>\n#define NULL 7\n')


def test_pointer_return_and_parameter_mismatch_is_rejected():
    for source in [
        'int *f(int *); float *f(int *p){return p;}',
        'int *f(int *); int *f(float *p){return p;}',
        'int *f(int *); int *f(int p){return 0;}',
    ]:
        with pytest.raises(CError, match='声明'):
            Program(source + 'int main(){return 0;}')
