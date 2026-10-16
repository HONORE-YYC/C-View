"""Parse the documented C subset while retaining original source locations."""
from dataclasses import dataclass
import re

from pycparser import c_ast as ast, c_parser, c_generator
from .errors import CError
from .preprocessor import Preprocessor


@dataclass(frozen=True)
class Location:
    line: int
    column: int
    text: str
    kind: str = 'statement'


_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
_GENERATOR = c_generator.CGenerator()


class Program:
    def __init__(self, source):
        if len(source) > 64000:
            raise CError('代码超过 64000 字符，请缩小教学示例')
        self.source = source
        self.preprocessed = Preprocessor().process(source)
        cleaned = self.preprocessed.text
        # A string such as printf("main(") is not a function definition.
        masked = _TOKENS.sub(lambda m: ' ' * len(m[0]), cleaned)
        self.offset = 0 if re.search(r'\bmain\s*\(', masked) else 1
        parsed_source = cleaned if not self.offset else 'int main(void) {\n' + cleaned + '\n}'
        try:
            self.tree = c_parser.CParser().parse(parsed_source)
        except (c_parser.ParseError, RecursionError) as exc:
            match = re.search(r':(\d+):(\d+):', str(exc))
            line, column = self.preprocessed.original(max(1, int(match[1])-self.offset), int(match[2])) if match else (0, 0)
            detail = str(exc).split(': ', 1)[-1]
            raise CError(f'C 语法错误：{detail}', line, column) from None
        self.globals = []
        self.main = None
        for node in self.tree.ext:
            if isinstance(node, ast.FuncDef):
                if self.main is not None or node.decl.name != 'main':
                    self.fail(node, '第一版仅支持一个 main 函数；自定义函数暂不支持')
                signature = node.decl.type
                if (not isinstance(signature.type, ast.TypeDecl)
                        or not isinstance(signature.type.type, ast.IdentifierType)
                        or signature.type.type.names != ['int']):
                    self.fail(node, 'main 必须返回 int')
                params = signature.args.params if signature.args else []
                if params and not (len(params) == 1 and isinstance(params[0], ast.Typename)
                                   and isinstance(params[0].type, ast.TypeDecl)
                                   and isinstance(params[0].type.type, ast.IdentifierType)
                                   and params[0].type.type.names == ['void']):
                    self.fail(node, 'main 暂不支持参数，请使用 int main(void)')
                self.main = node.body
                self._check(node.body)
            elif isinstance(node, ast.Decl):
                self._check(node)
                self.globals.append(node)
            else:
                self.fail(node, '暂不支持此顶层声明')
        if self.main is None:
            raise CError('缺少 int main(void) 函数')

    def location(self, node, kind='statement'):
        coord = node.coord
        line, column = self.preprocessed.original(max(1, coord.line-self.offset), coord.column) if coord else (1, 1)
        return Location(line, column, _GENERATOR.visit(node), kind)

    def fail(self, node, message):
        # Reporting invalid/deep ASTs must not regenerate the invalid subtree.
        coord = node.coord
        line, column = self.preprocessed.original(max(1, coord.line-self.offset), coord.column) if coord else (1, 1)
        raise CError(message, line, column)

    def _check(self, node, loops=0, depth=0):
        if node is None:
            return
        if depth > 100:
            self.fail(node, '表达式或代码块嵌套过深（最多 100 层）')
        allowed = (ast.Compound, ast.Decl, ast.TypeDecl, ast.IdentifierType, ast.ArrayDecl,
                   ast.InitList, ast.Constant, ast.ID, ast.Assignment, ast.BinaryOp,
                   ast.UnaryOp, ast.ArrayRef, ast.If, ast.For, ast.While, ast.Break,
                   ast.Continue, ast.Return, ast.EmptyStatement, ast.DeclList,
                   ast.FuncCall, ast.ExprList)
        if not isinstance(node, allowed):
            self.fail(node, f'第一版暂不支持 {type(node).__name__}')
        if isinstance(node, ast.IdentifierType) and node.names not in (['int'], ['float'], ['double']):
            self.fail(node, '仅支持 int、float、double 类型')
        if isinstance(node, ast.Decl) and (node.quals or node.storage or node.funcspec or node.bitsize):
            self.fail(node, '暂不支持类型修饰符、存储修饰符或位域')
        if isinstance(node, ast.ArrayDecl):
            if not isinstance(node.type, ast.TypeDecl) or node.dim is None or node.dim_quals:
                self.fail(node, '仅支持有明确容量的一维数组')
            if not self._constant_integer(node.dim):
                self.fail(node, '数组容量必须为整数常量表达式，可使用 #define 宏')
        if isinstance(node, ast.Constant) and node.type not in ('int', 'float', 'double', 'string'):
            self.fail(node, f'暂不支持 {node.type} 常量')
        if isinstance(node, ast.Constant) and node.type == 'int' and len(node.value) > 32:
            self.fail(node, '整数字面量过长；第一版仅支持 32 位有符号整数')
        if isinstance(node, ast.Constant) and node.type in ('float', 'double') and node.value.lower().startswith('0x'):
            self.fail(node, '第一版暂不支持十六进制浮点字面量，请使用十进制')
        if isinstance(node, ast.Assignment) and node.op not in ('=', '+=', '-=', '*=', '/=', '%='):
            self.fail(node, f'暂不支持运算符 {node.op}')
        if isinstance(node, ast.BinaryOp) and node.op not in ('+', '-', '*', '/', '%', '<', '<=', '>', '>=', '==', '!=', '&&', '||'):
            self.fail(node, f'暂不支持运算符 {node.op}')
        if isinstance(node, ast.UnaryOp) and node.op not in ('+', '-', '!', 'p++', 'p--', '++', '--'):
            self.fail(node, f'暂不支持运算符 {node.op}')
        if isinstance(node, (ast.Break, ast.Continue)) and not loops:
            self.fail(node, 'break/continue 只能出现在循环内')
        if isinstance(node, ast.FuncCall) and not (isinstance(node.name, ast.ID) and node.name.name in ('printf', 'abs', 'rand', 'srand')):
            self.fail(node, '当前仅支持 printf、abs、rand、srand 调用')
        child_loops = loops + isinstance(node, (ast.For, ast.While))
        for _, child in node.children():
            self._check(child, child_loops, depth + 1)

    @staticmethod
    def _constant_integer(node, depth=0):
        if depth > 100:
            return False
        if isinstance(node, ast.Constant):
            return node.type == 'int'
        if isinstance(node, ast.UnaryOp) and node.op in ('+', '-', '!'):
            return Program._constant_integer(node.expr, depth+1)
        if isinstance(node, ast.BinaryOp):
            return Program._constant_integer(node.left, depth+1) and Program._constant_integer(node.right, depth+1)
        return False

    def targets(self):
        result = []

        def walk(node):
            if node is None:
                return
            if isinstance(node, ast.Compound):
                for child in node.block_items or []:
                    walk(child)
            elif isinstance(node, ast.DeclList):
                for child in node.decls:
                    walk(child)
            elif isinstance(node, (ast.For, ast.While, ast.If)):
                if isinstance(node, ast.For):
                    walk(node.init)
                result.append(self.location(node.cond or node, 'condition'))
                walk(node.stmt if isinstance(node, (ast.For, ast.While)) else node.iftrue)
                if isinstance(node, ast.If):
                    walk(node.iffalse)
                if isinstance(node, ast.For) and node.next:
                    result.append(self.location(node.next, 'update'))
            else:
                result.append(self.location(node))

        for node in self.globals:
            walk(node)
        walk(self.main)
        return result
