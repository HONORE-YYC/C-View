"""Pause before any observable C operation; emit independent post-step snapshots."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from pycparser import c_ast as ast

from .language import CError, Location, Program
from .runtime import Runtime
from .motion import index_bindings, index_markers


@dataclass
class Action:
    location: Location
    run: Callable

    @property
    def line(self):
        return self.location.line

    @property
    def column(self):
        return self.location.column


@dataclass
class Event:
    line: int
    column: int
    text: str
    kind: str
    message: str
    variables: dict
    output: str
    reads: list = field(default_factory=list)
    writes: list = field(default_factory=list)
    number: int = 0
    before: dict = field(default_factory=dict)
    transfers: list = field(default_factory=list)


class _Flow(Exception):
    def __init__(self, kind):
        self.kind = kind


class Engine:
    def __init__(self, source, max_steps=100000):
        self.program = Program(source)
        self.runtime = Runtime(self.program)
        self._index_bindings = index_bindings(self.program)
        self.index_lanes = {}
        for array, _ in self._index_bindings:
            self.index_lanes[array] = self.index_lanes.get(array, 0) + 1
        self.max_steps, self.count = max_steps, 0
        self.last = None
        self._pending = None
        self.finished = False
        self._iterator = self._program()

    def index_markers(self):
        return index_markers(self._index_bindings, self.runtime.snapshot())

    def peek(self):
        if self._pending is None and not self.finished:
            try:
                self._pending = next(self._iterator)
            except StopIteration:
                self.finished = True
        return self._pending

    def step(self):
        action = self.peek()
        if action is None:
            return None
        loc = action.location
        if self.count >= self.max_steps:
            raise CError(f'达到 {self.max_steps} 步数限制，请检查循环条件', loc.line, loc.column)
        rt = self.runtime
        backup, old_output, old_random = deepcopy(rt.scopes), rt.output, rt.random_state
        before = rt.snapshot()
        rt.reads, rt.writes = [], []
        rt.transfers = []
        try:
            description = action.run()
        except CError:
            rt.scopes, rt.output, rt.random_state = backup, old_output, old_random
            raise
        self.count += 1
        self.last = Event(loc.line, loc.column, loc.text, loc.kind, str(description),
                          rt.snapshot(), rt.output, list(rt.reads), list(rt.writes), self.count, before,
                          list(rt.transfers))
        self._pending = None
        return self.last

    def _action(self, node, fn, kind='statement'):
        return Action(self.program.location(node, kind), fn)

    def _program(self):
        for node in self.program.globals:
            yield self._action(node, lambda n=node: self.runtime.declare(n, True))
        # Keep globals and main separate, but preserve main's variables at termination.
        self.runtime.scopes.append({})
        try:
            for node in self.program.main.block_items or []:
                yield from self._walk(node)
        except _Flow as flow:
            if flow.kind != 'return':
                raise

    def _condition(self, expr, origin, result):
        def check():
            value = self.runtime.evaluate(expr) if expr is not None else 1
            result[0] = self.runtime.truth(value, expr or origin)
            return f'条件结果 = {value} → ' + ('真' if result[0] else '假')
        return self._action(expr or origin, check, 'condition')

    def _walk(self, node):
        if node is None:
            return
        rt = self.runtime
        if isinstance(node, ast.Compound):
            rt.scopes.append({})
            try:
                for child in node.block_items or []:
                    yield from self._walk(child)
            finally:
                rt.scopes.pop()
        elif isinstance(node, ast.DeclList):
            for decl in node.decls:
                yield from self._walk(decl)
        elif isinstance(node, ast.Decl):
            yield self._action(node, lambda: rt.declare(node))
        elif isinstance(node, ast.If):
            result = [False]
            yield self._condition(node.cond, node, result)
            yield from self._walk(node.iftrue if result[0] else node.iffalse)
        elif isinstance(node, (ast.For, ast.While)):
            rt.scopes.append({})
            try:
                if isinstance(node, ast.For):
                    yield from self._walk(node.init)
                while True:
                    result = [False]
                    yield self._condition(node.cond, node, result)
                    if not result[0]:
                        break
                    try:
                        yield from self._walk(node.stmt)
                    except _Flow as flow:
                        if flow.kind == 'break':
                            break
                        if flow.kind != 'continue':
                            raise
                    if isinstance(node, ast.For) and node.next:
                        yield self._action(node.next, lambda: self._expression(node.next), 'update')
            finally:
                rt.scopes.pop()
        elif isinstance(node, (ast.Break, ast.Continue, ast.Return)):
            kind = type(node).__name__.lower()
            def perform():
                if isinstance(node, ast.Return) and node.expr:
                    value = rt.convert(rt.evaluate(node.expr), 'int', node)
                    return f'return {value}：结束程序'
                return {'break': 'break：退出本层循环', 'continue': 'continue：进入下一轮',
                        'return': 'return：结束程序'}[kind]
            yield self._action(node, perform)
            raise _Flow(kind)
        elif isinstance(node, ast.EmptyStatement):
            yield self._action(node, lambda: '空语句')
        else:
            yield self._action(node, lambda: self._expression(node))

    def _expression(self, node):
        value = self.runtime.evaluate(node)
        if value is None:
            return f'{self.program.location(node).text}：已设置随机种子'
        return f'{self.program.location(node).text} → {value}'
