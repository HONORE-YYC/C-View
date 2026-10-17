"""Execute real calls once; bounded detail snapshots support reversible presentation.

The caller's pending action is not advanced until its detail queue is exhausted.
Arguments, randomness, output and array mutations are never evaluated twice.
"""
from copy import deepcopy

from pycparser import c_ast as ast

from .runtime import Cell
from .motion import declaration_key
from .pointers import Pointer
from .numeric import type_name
from .qualifiers import qualifiers


class FunctionExecution:
    def __init__(self, engine):
        self.engine = engine
        self.stack = []
        self._used = {}
        for name, function in engine.program.functions.items():
            used = set()
            def visit(node):
                if isinstance(node, ast.ID):
                    used.add(node.name)
                for _, child in node.children():
                    visit(child)
            visit(function.node.body)
            self._used[name] = used

    @property
    def return_type(self):
        return self.stack[-1].return_type if self.stack else 'int'

    def visible(self):
        rt = self.engine.runtime
        visible = rt.snapshot()
        if not self.stack:
            return visible
        used = self._used[self.stack[-1].name]
        local = set().union(*(set(scope) for scope in rt.scopes[1:]))
        addresses = {cell['value'].identity for name, cell in visible.items()
                     if (name in local or name in used) and isinstance(cell['value'], Pointer)}
        return {name: cell for name, cell in visible.items()
                if name in local or name in used or cell['identity'] in addresses}

    def call(self, node):
        from .engine import Event, _Flow
        engine, rt = self.engine, self.engine.runtime
        spec = engine.program.functions[node.name.name]
        if len(self.stack) >= 32 or spec in self.stack:
            rt.fail(node, '暂不支持递归或超过 32 层的函数调用')
        args = node.args.exprs if node.args else []
        if len(args) != len(spec.params):
            rt.fail(node, f'{spec.name} 参数数量不匹配')
        inputs, params = [], {}
        for param, arg in zip(spec.params, args):
            array = isinstance(param.type, ast.ArrayDecl)
            pointer = isinstance(param.type, ast.PtrDecl)
            base = param.type.type if array or pointer else param.type
            parameter_type = type_name(base.type.names)
            # An array parameter is adjusted to a pointer in C, including local p++.
            parameter_type += '*' if pointer or array else ''
            value, sources = rt.evaluate_sources(arg)
            readonly, pointee_const = qualifiers(param.type)
            value = rt.convert(value, parameter_type, arg, pointee_const)
            cell = Cell(parameter_type, value, rt.next_identity, declaration_key(param), readonly, pointee_const)
            rt.next_identity += 1
            params[param.name] = cell
            inputs.append({'name': param.name, 'expression': engine.program.location(arg).text,
                           'value': deepcopy(value), 'sources': sources})
        caller = rt.scopes
        caller_visible = rt.snapshot()
        saved_activity = rt.reads, rt.writes, rt.transfers, rt._source_frames, rt.write_targets
        rt.reads, rt.writes, rt.transfers, rt._source_frames = [], [], [], []
        rt.write_targets = []
        # Only globals and the callee's parameters are in lexical scope.
        rt.callers.append(caller)
        rt.scopes = [caller[0], params]
        self.stack.append(spec)
        record = {'name': spec.name, 'inputs': inputs, 'return': None}
        if len(self.stack) == 1:
            engine._calls.append(record)
        changed = set()
        result = None
        returned = False
        try:
            for param in spec.params:
                if isinstance(param.type, ast.ArrayDecl) and param.type.dim is not None:
                    size = rt.evaluate(param.type.dim)
                    if not isinstance(size, int) or size <= 0:
                        rt.fail(param, '数组参数容量必须为正整数')
                    changed.update(rt.write_targets)
            loc = engine.program.location(spec.node.decl, 'function')
            engine.capture_detail(Event(loc.line, loc.column, loc.text, loc.kind,
                f'进入函数 {spec.name}', self.visible(), rt.output, function=spec.name))
            try:
                # Parameters and outermost declarations share a scope in C.
                for statement in spec.node.body.block_items or []:
                    for action in engine._walk(statement):
                        engine._consume(action.location)
                        before = self.visible() if engine._record_detail else {}
                        rt.reads, rt.writes, rt.transfers = [], [], []
                        rt.write_targets = []
                        description = action.run()
                        changed.update(rt.write_targets)
                        loc = action.location
                        if engine._record_detail:
                            engine.capture_detail(Event(loc.line, loc.column, loc.text, loc.kind, str(description),
                                self.visible(), rt.output, list(rt.reads), list(rt.writes), before=before,
                                transfers=list(rt.transfers), function=spec.name))
            except _Flow as flow:
                if flow.kind != 'return':
                    raise
                returned, result = True, flow.value
            if spec.return_type != 'void' and not returned:
                rt.fail(spec.node.decl, f'函数 {spec.name} 未返回数值')
            record['return'] = result
            return result
        finally:
            self.stack.pop()
            rt.scopes = caller
            rt.callers.pop()
            rt.reads, rt.writes, rt.transfers, rt._source_frames, rt.write_targets = saved_activity
            rt.write_targets.extend(changed)
            for name, cell in caller_visible.items():
                for identity, index in changed:
                    if cell['identity'] == identity:
                        rt.writes.append((name, index))
