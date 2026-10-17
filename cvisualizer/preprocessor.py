"""Bounded teaching preprocessor, with original source coordinates for every character.

No shell invocation, filesystem includes, conditional compilation or token pasting.
"""
from dataclasses import dataclass, replace
import re

from .errors import CError


LITERALS_COMMENTS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\s+|'
                   r'(?:\d|\.\d)(?:[eEpP][+-]|[\w.])*|[A-Za-z_]\w*|##|\.\.\.|'
                   r'<<=|>>=|\+\+|--|->|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|/=|%=|<<|>>|.', re.DOTALL)
IDENTIFIER = re.compile(r'[A-Za-z_]\w*\Z')


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    column: int
    expanded: bool = False
    blocked: frozenset = frozenset()


@dataclass
class Macro:
    parameters: list | None
    body: list


def tokenize(text, line=1):
    column = 1
    result = []
    for match in TOKEN.finditer(text):
        word = match[0]
        result.append(Token(word, line, column))
        for char in word:
            if char == '\n':
                line, column = line + 1, 1
            else:
                column += 1
    return result


class Preprocessed:
    def __init__(self, tokens):
        text, rows = [], [[]]
        # Token boundaries matter: NEG(-1) expands to - -1, never --1.
        separated = []
        for token in tokens:
            if separated and not separated[-1].text[-1:].isspace() and not token.text[:1].isspace():
                separated.append(Token(' ', token.line, token.column, True))
            separated.append(token)
        for token in separated:
            line, column = token.line, token.column
            for char in token.text:
                rows[-1].append((line, column))
                text.append(char)
                if char == '\n':
                    rows.append([])
                if not token.expanded:
                    if char == '\n':
                        line, column = line + 1, 1
                    else:
                        column += 1
        self.text, self.rows = ''.join(text), rows

    def original(self, line, column):
        row = self.rows[min(max(line-1, 0), len(self.rows)-1)]
        if not row:
            return max(1, line), max(1, column)
        return row[min(max(column-1, 0), len(row)-1)]


class Preprocessor:
    def __init__(self):
        self.macros = {}
        self.expansions = 0

    @staticmethod
    def fail(token, message):
        raise CError(message, token.line, token.column)

    def expand(self, tokens, depth=0):
        if not tokens:
            return []
        if depth > 32:
            self.fail(tokens[0], '宏调用嵌套超过 32 层')
        work = list(tokens)
        i = 0
        while i < len(work):
            token = work[i]
            macro = self.macros.get(token.text)
            if macro is None:
                i += 1
                continue
            if token.text in token.blocked:
                self.fail(token, f'不支持递归宏：{token.text}')
            end = i+1
            arguments = {}
            if macro.parameters is not None:
                opening = end
                while opening < len(work) and work[opening].text.isspace():
                    opening += 1
                if opening >= len(work) or work[opening].text != '(':
                    i += 1
                    continue
                args, arg, balance = [], [], 1
                end = opening+1
                while end < len(work):
                    part = work[end]
                    if part.text == '(':
                        balance += 1
                    elif part.text == ')':
                        balance -= 1
                        if balance == 0:
                            args.append(arg)
                            end += 1
                            break
                    if part.text == ',' and balance == 1:
                        args.append(arg)
                        arg = []
                    else:
                        arg.append(part)
                    end += 1
                if balance:
                    self.fail(token, f'宏 {token.text} 的参数缺少右括号')
                if not macro.parameters and len(args) == 1 and not any(not t.text.isspace() for t in args[0]):
                    args = []
                if len(args) != len(macro.parameters):
                    self.fail(token, f'宏 {token.text} 需要 {len(macro.parameters)} 个参数')
                arguments = {name: self.expand(arg, depth+1) for name, arg in zip(macro.parameters, args)}
            blocked = token.blocked | {token.text}
            result = []
            for part in macro.body:
                if part.text in arguments:
                    result.extend(replace(p, blocked=p.blocked | blocked) for p in arguments[part.text])
                else:
                    result.append(Token(part.text, token.line, token.column, True, blocked))
            self.expansions += 1
            if self.expansions > 10000 or len(blocked) > 32:
                self.fail(token, '宏展开次数或层级超过教学限制')
            work[i:end] = result
            if len(work) > 100000 or sum(len(t.text) for t in work) > 256000:
                self.fail(token, '宏展开结果过大（最多 256000 字符）')
        return work

    def directive(self, text, line):
        token = Token('', line, 1)
        include = re.fullmatch(r'\s*#\s*include\s*(?:<(stdio\.h|stdlib\.h|cstdlib|stddef\.h|string\.h|cstring)>|"(stdio\.h|stdlib\.h|cstdlib|stddef\.h|string\.h|cstring)")\s*', text)
        if include:
            self.macros.setdefault('NULL', Macro(None, tokenize('0')))
            if (include[1] or include[2]) in ('stdlib.h', 'cstdlib'):
                self.macros.setdefault('RAND_MAX', Macro(None, tokenize('32767')))
            return
        undef = re.fullmatch(r'\s*#\s*undef\s+([A-Za-z_]\w*)\s*', text)
        if undef:
            self.macros.pop(undef[1], None)
            return
        define = re.fullmatch(r'\s*#\s*define\s+([A-Za-z_]\w*)(.*)', text, re.DOTALL)
        if not define:
            self.fail(token, '不支持此预处理指令；支持 stdio.h/stdlib.h/cstdlib/stddef.h/string.h/cstring、#define 和 #undef')
        name, rest = define[1], define[2]
        parameters = None
        if rest.startswith('('):
            close = rest.find(')')
            if close < 0:
                self.fail(token, '宏参数列表缺少右括号')
            params = rest[1:close].strip()
            parameters = [p.strip() for p in params.split(',')] if params else []
            if any(not IDENTIFIER.fullmatch(p) for p in parameters) or len(set(parameters)) != len(parameters):
                self.fail(token, '宏参数必须是不同的标识符，暂不支持变参宏')
            rest = rest[close+1:]
        body = tokenize(rest.strip(), line)
        if any(t.text in ('#', '##', '...', ';', '{', '}') for t in body):
            self.fail(token, '宏暂不支持字符串化、拼接、变参或多语句块')
        value = Macro(parameters, body)
        if name in self.macros:
            old = self.macros[name]
            if old.parameters != parameters or ''.join(t.text for t in old.body) != ''.join(t.text for t in body):
                self.fail(token, f'宏 {name} 重复定义为不同内容；请先 #undef')
        self.macros[name] = value
        if len(self.macros) > 256:
            self.fail(token, '宏定义超过 256 个')

    def process(self, source):
        cleaned = LITERALS_COMMENTS.sub(
            lambda m: re.sub(r'[^\n]', ' ', m[0]) if m[0].startswith('/') else m[0], source)
        lines = cleaned.splitlines(keepends=True)
        output, pending = [], []
        start, i = 1, 0

        def flush():
            if pending:
                output.extend(self.expand(tokenize(''.join(pending), start)))
                pending.clear()

        while i < len(lines):
            line = lines[i]
            if line.lstrip().startswith('#'):
                flush()
                first, logical = i, line
                while logical.rstrip('\r\n').endswith('\\'):
                    logical = logical.rstrip('\r\n')[:-1]
                    i += 1
                    if i >= len(lines):
                        raise CError('预处理续行缺少下一行', first+1)
                    logical += lines[i]
                self.directive(logical, first+1)
                for row in range(first, i+1):
                    output.append(Token('\n', row+1, max(1, len(lines[row].rstrip('\r\n'))+1)))
            else:
                if not pending:
                    start = i+1
                pending.append(line)
            i += 1
        flush()
        if sum(len(t.text) for t in output) > 256000:
            raise CError('宏展开结果超过 256000 字符')
        return Preprocessed(output)
