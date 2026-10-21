"""Pause before any observable C operation; emit independent post-step snapshots."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable
from collections import deque

from pycparser import c_ast as ast

from .language import CError, Location, Program
from .runtime import Runtime
from .motion import index_bindings, index_markers, pointer_slots, indirect_index_slots
from .member_motion import member_index_bindings, member_index_markers
from .qualifiers import qualifiers
from .value_format import display


@dataclass
class Action:
    location: Location
    run: Callable
    functions: tuple = ()
    live: frozenset = frozenset()

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
    calls: list = field(default_factory=list)
    function: str = ''
    expanded: bool = False
    booleans: list = field(default_factory=list)


class _Flow(Exception):
    def __init__(self, kind, value=None):
        self.kind, self.value = kind, value


class Engine:
    def __init__(self, source, max_steps=100000):
        self.program = Program(source)
        self.runtime = Runtime(self.program)
        from .linked_liveness import LinkedLiveness
        from .linked_state import LinkedState
        self.linked_liveness = LinkedLiveness(self.program)
        self.linked_state = LinkedState(self.program.linked_types)
        self._live_stack = []
        self._linked_candidates = []
        from .function_execution import FunctionExecution
        self.functions = FunctionExecution(self)
        self.runtime.call_function = self.functions.call
        self.runtime.consume = self._consume
        self._detail = deque()
        self._trace, self._calls = [], []
        self._record_detail = False
        self._operations = 0
        self._index_bindings = index_bindings(self.program)
        self._matrix_index_bindings = index_bindings(self.program, matrices=True)
        self._member_index_bindings = member_index_bindings(self.program)
        self.index_lanes = {}
        for array, _ in self._index_bindings:
            self.index_lanes[array] = self.index_lanes.get(array, 0) + 1
        for array, _, _ in self._matrix_index_bindings:
            self.index_lanes[array] = self.index_lanes.get(array, 0) + 1
        self.index_lanes['__pointer_slots__'] = pointer_slots(self.program)
        self.index_lanes['__indirect_index_slots__'] = indirect_index_slots(self.program, self._index_bindings) + len(self._matrix_index_bindings)
        self.index_lanes['__indirect_index_slots__'] += max((len(axes) for _, axes in self._member_index_bindings), default=0)
        self.max_steps, self.count = max_steps, 0
        self.last = None
        self._pending = None
        self.finished = False
        self._iterator = self._program()

    def index_markers(self):
        snapshot = self.runtime.snapshot()
        return {**index_markers(self._index_bindings, snapshot, self._matrix_index_bindings),
                **member_index_markers(self._member_index_bindings, snapshot)}

    def peek(self):
        if self._detail:
            event = self._detail[0][0]
            return Action(Location(event.line, event.column, event.text, event.kind), lambda: None)
        if self._pending is None and not self.finished:
            try:
                self._pending = next(self._iterator)
            except StopIteration:
                self.finished = True
        return self._pending

    @property
    def has_detail(self):
        return bool(self._detail)

    def display_snapshot(self):
        if self.last and self.last.function:
            return self.last.variables
        snapshot = self.runtime.snapshot()
        if self.last:
            metadata = {c["identity"]: c for c in self.last.variables.values() if c.get("linked_node")}
            for cell in snapshot.values():
                previous = metadata.get(cell["identity"])
                if previous:
                    cell.update({key: previous[key] for key in ("linked_head", "linked_hidden") if key in previous})
        return snapshot

    def _state(self):
        rt = self.runtime
        return deepcopy((rt.scopes, rt.callers, rt.output, rt.random_state, rt.next_identity, rt.input_position, rt.literals, rt.literal_pool, rt.heap, rt.freed))

    def _restore(self, state):
        rt = self.runtime
        rt.scopes, rt.callers, rt.output, rt.random_state, rt.next_identity, rt.input_position, rt.literals, rt.literal_pool, rt.heap, rt.freed = deepcopy(state)

    def _consume(self, location):
        if self._operations >= self.max_steps:
            raise CError(f'达到 {self.max_steps} 步数限制，请检查循环条件', location.line, location.column)
        self._operations += 1

    def _remember_linked_heads(self):
        if not self.program.linked_types:
            return
        self._linked_candidates.append({n: {"type": c.type, "identity": c.identity}
            for n, c in self.runtime.visible_cells().items()
            if c.type.endswith("*") and "." not in n})

    def _linked_context(self, event, live):
        event._linked_candidates = list(self._linked_candidates)
        event._linked_live = set(live).union(*self._live_stack)
        from .struct_runtime import snapshot, flattened
        event._linked_callers = []
        if not self.program.linked_types:
            return
        for scopes in [*self.runtime.callers, self.runtime.scopes]:
            for scope in scopes:
                # Keep identities hidden by a same-name inner declaration.
                event._linked_callers.extend(snapshot(self.runtime, flattened(scope)).items())

    def _linked_event(self, event):
        if not self.program.linked_types:
            return
        if self.last:
            previous = {c["identity"]: c for c in self.last.variables.values() if c.get("linked_node")}
            for cell in event.before.values():
                old = previous.get(cell["identity"], {})
                cell.update({key: old[key] for key in ("linked_head", "linked_hidden") if key in old})
        self.linked_state.discover(event.before)
        for candidate in getattr(event, "_linked_candidates", ()):
            self.linked_state.discover(candidate)
        self.linked_state.discover(dict(getattr(event, "_linked_callers", ())))
        live = set(getattr(event, "_linked_live", set()))
        for name, _ in event.reads + event.writes:
            live.add(name.split(".", 1)[0].split("[", 1)[0])
        for source, destination in event.transfers:
            for name, _, _ in (source, destination):
                live.add(name.split(".", 1)[0].split("[", 1)[0])
        self.linked_state.decorate(event.variables, live, event.number, getattr(event, "_linked_callers", ()))

    def capture_detail(self, event):
        if self._record_detail:
            if len(self._trace) >= 2000:
                raise CError('单次函数展开超过 2000 步，请缩小示例或使用快速演示', event.line, event.column)
            if not hasattr(event, "_linked_live"):
                self._linked_context(event, self._live_stack[-1] if self._live_stack else set())
            self._trace.append((event, self._state()))

    def step(self, expand_calls=False):
        if self._detail:
            if expand_calls:
                event, state = self._detail.popleft()
            else:
                event, state = self._detail[-1]
                self._detail.clear()
            self._restore(state)
            self.count += 1
            event.number = self.count
            self._linked_event(event)
            self.last = event
            return event
        action = self.peek()
        if action is None:
            return None
        loc = action.location
        operations_before = self._operations
        self._consume(loc)
        rt = self.runtime
        backup = self._state()
        before = rt.snapshot()
        self._trace, self._calls = [], []
        self._linked_candidates = []
        self._record_detail = expand_calls
        rt.reads, rt.writes = [], []
        rt.booleans = []
        rt.transfers = []
        rt.write_targets = []
        try:
            self._live_stack.append(action.live)
            try:
                description = action.run()
            finally:
                self._live_stack.pop()
        except CError:
            self._restore(backup)
            self._operations = operations_before
            self._trace.clear()
            raise
        except (MemoryError, OverflowError):
            self._restore(backup)
            self._operations = operations_before
            self._trace.clear()
            raise CError('可用内存或本机索引范围不足，请缩小数据规模', loc.line, loc.column) from None
        event = Event(loc.line, loc.column, loc.text, loc.kind, str(description),
                      rt.snapshot(), rt.output, list(rt.reads), list(rt.writes), 0, before,
                      list(rt.transfers), list(self._calls), expanded=bool(self._trace), booleans=deepcopy(rt.booleans))
        self._linked_context(event, action.live)
        self._pending = None
        if self._trace:
            self._detail.extend(self._trace)
            self._detail.append((event, self._state()))
            self._trace = []
            return self.step(expand_calls=True)
        self.count += 1
        event.number = self.count
        self._linked_event(event)
        self.last = event
        return self.last

    def _action(self, node, fn, kind='statement'):
        calls = []
        def visit(current):
            if isinstance(current, ast.FuncCall) and isinstance(current.name, ast.ID) and current.name.name in self.program.functions:
                calls.append(current.name.name)
            for _, child in current.children():
                visit(child)
        visit(node)
        return Action(self.program.location(node, kind), fn, tuple(dict.fromkeys(calls)), frozenset(self.linked_liveness.after.get(id(node), self.linked_liveness.reads(node))))

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
            return f'条件结果 = {display(value)} → ' + ('真' if result[0] else '假')
        action = self._action(expr or origin, check, 'condition')
        if expr is None:
            action.functions = ()
        return action

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
            returned = [None]
            def perform():
                if isinstance(node, ast.Return) and node.expr:
                    type_name = self.functions.return_type
                    const_target = qualifiers(self.functions.stack[-1].node.decl.type.type)[1] if self.functions.stack else False
                    value = rt.convert(rt.evaluate(node.expr), type_name, node, const_target)
                    returned[0] = value
                    return f'return {display(value)}：' + ('返回调用处' if self.functions.stack else '结束程序')
                return {'break': 'break：退出本层循环', 'continue': 'continue：进入下一轮',
                        'return': 'return：返回调用处' if self.functions.stack else 'return：结束程序'}[kind]
            yield self._action(node, perform)
            raise _Flow(kind, returned[0])
        elif isinstance(node, ast.EmptyStatement):
            yield self._action(node, lambda: '空语句')
        else:
            yield self._action(node, lambda: self._expression(node))

    def _expression(self, node):
        value = self.runtime.evaluate(node)
        if value is None:
            return f'{self.program.location(node).text}：执行完成'
        return f'{self.program.location(node).text} → {display(value)}'
