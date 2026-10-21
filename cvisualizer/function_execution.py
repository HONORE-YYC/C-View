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
from . import struct_runtime
from .struct_runtime import StructValue


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
                     if (name in local or name in used or name.split('.',1)[0].split('[',1)[0] in local | used)
                     and isinstance(cell['value'], Pointer)}
        target_names = {name for name, cell in visible.items() if cell['identity'] in addresses}
        return {name: cell for name, cell in visible.items()
                if name.split('.',1)[0] in rt.heap or name in local or name in used or name.split('.',1)[0].split('[',1)[0] in local | used
                or cell['identity'] in addresses or any(name.startswith(target+'.') or name.startswith(target+'[') for target in target_names)}

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
            if engine.program.is_reference(param):
                ref = rt.reference(arg)
                parameter_type = rt.program._scalar_type(param.type)
                if ref[2] is not None or ref[1].type != parameter_type:
                    rt.fail(arg, '引用参数需要同类型可寻址变量')
                rt.check_writable(ref, arg)
                params[param.name] = ref[1]
                inputs.append({'name': param.name, 'expression': engine.program.location(arg).text,
                               'value': deepcopy(ref[1].value), 'sources': []})
                continue
            array = isinstance(param.type, ast.ArrayDecl)
            pointer = isinstance(param.type, ast.PtrDecl)
            base = param.type.type if array or pointer else param.type
            matrix = array and isinstance(base, ast.ArrayDecl)
            columns_node = base.dim if matrix else None
            if matrix:
                base = base.type
            parameter_type = rt.program._scalar_type(base)
            if matrix:
                saved_scopes = rt.scopes
                rt.scopes = [saved_scopes[0], params]
                try:
                    columns = rt.dimension(columns_node, param)
                finally:
                    rt.scopes = saved_scopes
                parameter_type += f'[{columns}]'
            # An array parameter is adjusted to a pointer in C, including local p++.
            parameter_type += '*' if pointer or array else ''
            value, sources = rt.evaluate_sources(arg)
            readonly, pointee_const = qualifiers(param.type)
            value = rt.convert(value, parameter_type, arg, pointee_const)
            cell = Cell(parameter_type, value, rt.next_identity, declaration_key(param), readonly, pointee_const)
            rt.next_identity += 1
            if isinstance(value, StructValue):
                cell = struct_runtime.make_cell(rt, param)
                struct_runtime.copy_into(rt, (param.name, cell, None), value, arg, sources, initial=True)
            params[param.name] = cell
            inputs.append({'name': param.name, 'expression': engine.program.location(arg).text,
                           'value': deepcopy(value), 'sources': sources})
        caller = rt.scopes
        caller_visible = rt.snapshot()
        saved_activity = rt.reads, rt.writes, rt.transfers, rt._source_frames, rt.write_targets, rt.booleans
        rt.reads, rt.writes, rt.transfers, rt._source_frames = [], [], [], []
        rt.write_targets = []
        rt.booleans = []
        # Only globals and the callee's parameters are in lexical scope.
        rt.callers.append(caller)
        rt.scopes = [caller[0], params]
        self.stack.append(spec)
        engine._remember_linked_heads()
        record = {'name': spec.name, 'inputs': inputs, 'return': None}
        if len(self.stack) == 1:
            engine._calls.append(record)
        changed = set()
        read_targets, transfers = {}, []
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
            entry_event = Event(loc.line, loc.column, loc.text, loc.kind,
                f'进入函数 {spec.name}', self.visible(), rt.output, function=spec.name)
            engine._linked_context(entry_event, engine.linked_liveness.entries[spec.name])
            engine.capture_detail(entry_event)
            try:
                # Parameters and outermost declarations share a scope in C.
                for statement in spec.node.body.block_items or []:
                    for action in engine._walk(statement):
                        engine._consume(action.location)
                        before = self.visible() if engine._record_detail else {}
                        rt.reads, rt.writes, rt.transfers = [], [], []
                        rt.write_targets = []
                        rt.booleans = []
                        try:
                            engine._live_stack.append(action.live)
                            try:
                                description = action.run()
                            finally:
                                engine._live_stack.pop()
                        finally:
                            changed.update(rt.write_targets)
                            visible_cells = rt.visible_cells()
                            read_targets.update(((visible_cells[name].identity, index), None)
                                                for name, index in rt.reads if name in visible_cells)
                            transfers.extend(rt.transfers)
                        engine._remember_linked_heads()
                        loc = action.location
                        if engine._record_detail:
                            detail_event = Event(loc.line, loc.column, loc.text, loc.kind, str(description),
                                self.visible(), rt.output, list(rt.reads), list(rt.writes), before=before,
                                transfers=list(rt.transfers), function=spec.name, booleans=deepcopy(rt.booleans))
                            engine._linked_context(detail_event, action.live)
                            engine.capture_detail(detail_event)
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
            rt.reads, rt.writes, rt.transfers, rt._source_frames, rt.write_targets, rt.booleans = saved_activity
            rt.write_targets.extend(changed)
            aliases = {cell['identity']: name for name, cell in caller_visible.items()}
            for identity, index in read_targets:
                if identity in aliases:
                    rt.reads.append((aliases[identity], index))
            for source, target in transfers:
                if source[2] in aliases and target[2] in aliases:
                    rt.transfers.append(((aliases[source[2]], source[1], source[2]),
                                         (aliases[target[2]], target[1], target[2])))
            for name, cell in caller_visible.items():
                for identity, index in changed:
                    if cell['identity'] == identity:
                        rt.writes.append((name, index))
