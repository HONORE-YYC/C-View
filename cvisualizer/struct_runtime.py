"""Aggregate storage and member operations, separate from scalar execution."""
from copy import deepcopy
from dataclasses import dataclass
from pycparser import c_ast as ast
from .arrays import Array, Matrix
from .motion import declaration_key
from .qualifiers import qualifiers


@dataclass
class StructValue:
    type: str
    fields: dict

    def __repr__(self):
        return self.type + ' {' + ', '.join(self.fields) + '}'


class StructArray(Array):
    """Materialize aggregate elements only when accessed or initialized."""
    def __init__(self, size, declaration, initialized=False, readonly=False):
        super().__init__(size)
        self.declaration = declaration
        self.initialized = initialized
        self.readonly = readonly
        self.elements = {}

    def __deepcopy__(self, memo):
        result = type(self)(self.size, self.declaration, self.initialized, self.readonly)
        memo[id(self)] = result
        result.elements = deepcopy(self.elements, memo)
        return result

    def __repr__(self):
        return f'结构体数组（容量 {self.size}）'


def array_member(rt, name, cell, index, node):
    value = cell.value
    if index not in value.elements:
        declaration = deepcopy(value.declaration)
        declaration.type = declaration.type.type
        value.elements[index] = make_cell(rt, declaration, value.initialized, value.readonly)
    return f'{name}[{index}]', value.elements[index], None


def cells(name, cell):
    yield name, cell
    if isinstance(cell.value, StructValue):
        for field, member in cell.value.fields.items():
            yield from cells(name+'.'+field, member)
    elif isinstance(cell.value, StructArray):
        for index, member in cell.value.elements.items():
            yield from cells(f'{name}[{index}]', member)


def flattened(scope):
    return {path: member for name, cell in scope.items() for path, member in cells(name, cell)}


def snapshot(rt, visible):
    result={}
    for name, cell in visible.items():
        item={'type':cell.type,'value':deepcopy(cell.value),'identity':cell.identity,'declaration':cell.declaration}
        if isinstance(cell.value,(StructValue,StructArray)): item['is_struct']=True
        if isinstance(cell.value,StructValue) and cell.type in rt.program.linked_types:
            item['linked_node']=dict(rt.program.linked_types[cell.type])
        if '.' in name:
            owner=name.rsplit('.',1)[0]
            parent=visible.get(owner)
            if parent and isinstance(parent.value,StructValue):
                item['struct_owner']=rt.program.structs[parent.type].name
                item['struct_root']=name.split('.',1)[0].split('[',1)[0]
        result[name]=item
    return result


def make_cell(rt, declaration, initialized=False, inherited_const=False):
    from .runtime import Cell
    if rt.consume:
        rt.consume(rt.program.location(declaration))
    node=declaration.type
    array=isinstance(node,ast.ArrayDecl)
    base=node
    while isinstance(base,ast.ArrayDecl): base=base.type
    typename=rt.program._scalar_type(base)
    readonly,pointee_const=qualifiers(node)
    readonly=readonly or inherited_const
    cell=Cell(typename,None,rt.next_identity,declaration_key(declaration),False,pointee_const)
    rt.next_identity+=1
    if array:
        if typename.startswith('struct ') and not typename.endswith('*'):
            if isinstance(node.type, ast.ArrayDecl):
                rt.fail(declaration,'结构体数组暂只支持一维')
            size=rt.dimension(node.dim,declaration) if node.dim is not None else len(declaration.init.exprs or []) if isinstance(declaration.init,ast.InitList) else 0
            if not size:rt.fail(declaration,'结构体数组需要正整数容量或初始化列表')
            cell.value=StructArray(size,declaration,initialized,readonly)
            cell.readonly=readonly
            return cell
        dimensions=[]
        cursor=node
        while isinstance(cursor,ast.ArrayDecl):
            dimensions.append(rt.dimension(cursor.dim,declaration));cursor=cursor.type
        default=rt.convert(0,typename,declaration,pointee_const) if initialized else None
        cell.value=Matrix(*dimensions,default) if len(dimensions)==2 else Array(dimensions[0],default)
    elif typename.startswith('struct ') and not typename.endswith('*'):
        spec=rt.program.structs.get(typename)
        if spec is None: rt.fail(declaration,'结构体类型尚未完整定义')
        cell.value=StructValue(typename,{field.name:make_cell(rt,field,initialized,readonly) for field in spec.fields})
    elif initialized: cell.value=rt.convert(0,typename,declaration,pointee_const)
    cell.readonly=readonly
    return cell


def initialize(rt,name,cell,init,node):
    if isinstance(cell.value,StructArray):
        if not isinstance(init,ast.InitList):rt.fail(init,'结构体数组需要初始化列表')
        if len(init.exprs or [])>len(cell.value):rt.fail(init,'数组初始化元素多于容量')
        for index,expr in enumerate(init.exprs or []):
            path,member,_=array_member(rt,name,cell,index,node)
            initialize(rt,path,member,expr,node)
    elif isinstance(cell.value,StructValue):
        if not isinstance(init,ast.InitList):
            value,sources=rt.evaluate_sources(init)
            return copy_into(rt,(name,cell,None),value,node,sources,initial=True)
        exprs=init.exprs or []
        if len(exprs)>len(cell.value.fields):rt.fail(init,'结构体初始化元素多于成员数量')
        for (field,member),expr in zip(cell.value.fields.items(),exprs):
            initialize(rt,name+'.'+field,member,expr,node)
    elif isinstance(cell.value,Matrix):
        if not isinstance(init,ast.InitList):rt.fail(init,'二维数组成员需要初始化列表')
        cursor=0
        columns=cell.value.columns
        for expr in init.exprs or []:
            nested=isinstance(expr,ast.InitList)
            string=cell.type=='char' and isinstance(expr,ast.Constant) and expr.type=='string'
            if nested or string:
                if cursor % columns:rt.fail(expr,'嵌套初始化列表必须从数组行首开始')
                items=[ord(c) for c in rt.string_literal(expr)] if string else expr.exprs or []
                if len(items)>columns:rt.fail(expr,'数组初始化元素多于列容量')
            else:items=[expr]
            for offset,item in enumerate(items):
                if cursor+offset>=len(cell.value)*columns:rt.fail(expr,'数组初始化元素多于容量')
                value,sources=(item,()) if isinstance(item,int) else rt.evaluate_sources(item)
                old=cell.readonly;cell.readonly=False
                try:rt.write((name,cell,divmod(cursor+offset,columns)),value,node,sources)
                finally:cell.readonly=old
            cursor+=columns if nested or string else 1
    elif isinstance(cell.value,list):
        if isinstance(init,ast.Constant) and init.type=='string' and cell.type=='char':
            exprs=[ord(c) for c in rt.string_literal(init)]
        elif isinstance(init,ast.InitList):exprs=init.exprs or []
        else:rt.fail(init,'数组成员需要初始化列表或字符字符串')
        if len(exprs)>len(cell.value):rt.fail(init,'数组初始化元素多于容量')
        for i,expr in enumerate(exprs):
            value,sources=(expr,()) if isinstance(expr,int) else rt.evaluate_sources(expr)
            old=cell.readonly;cell.readonly=False
            try:rt.write((name,cell,i),value,node,sources)
            finally:cell.readonly=old
    else:
        if isinstance(init,ast.InitList):
            if len(init.exprs or [])!=1:rt.fail(init,'标量成员需要单个初始化值')
            init=init.exprs[0]
        value,sources=rt.evaluate_sources(init)
        old=cell.readonly;cell.readonly=False
        try:rt.write((name,cell,None),value,node,sources)
        finally:cell.readonly=old


def declare(rt,node,global_scope):
    cell=make_cell(rt,node,node.init is not None or global_scope)
    rt.scopes[-1][node.name]=cell
    if node.init is not None:initialize(rt,node.name,cell,node.init,node)
    rt.writes.append((node.name,None))
    return '定义结构体 '+node.name


def copy_into(rt,ref,value,node,sources=(),initial=False):
    name,cell,index=ref
    if not isinstance(value,StructValue) or value.type!=cell.type:rt.fail(node,'结构体赋值类型不匹配')
    if not initial:rt.check_writable(ref,node)
    def assign(path,dest,source):
        if rt.consume:
            rt.consume(rt.program.location(node))
        if not initial:rt.check_writable((path,dest,None),node)
        if isinstance(dest.value,StructValue):
            for field,target in dest.value.fields.items():assign(path+'.'+field,target,source.value.fields[field])
        elif isinstance(dest.value,StructArray):
            indices=set(dest.value.elements)|set(source.value.elements)
            dest.value.initialized=source.value.initialized
            for index in indices:
                member_path,target,_=array_member(rt,path,dest,index,node)
                _,origin,_=array_member(rt,path,source,index,node)
                assign(member_path,target,origin)
        else:
            dest.value=deepcopy(source.value)
            rt.writes.append((path,None));rt.write_targets.append((dest.identity,None))
            suffix=path[len(name):]
            rt.transfers.extend((s,(path,None,dest.identity)) for s in sources
                                if suffix and s[0].endswith(suffix))
    # Snapshot first: overlapping assignments never mutate their source midway.
    source=deepcopy(cell);source.value=deepcopy(value)
    assign(name,cell,source)
    return deepcopy(cell.value)


def member_ref(rt,node,address=False):
    from .runtime import Reference
    if node.type=='->':
        pointer,_=rt.evaluate_sources(node.name)
        parent=rt.pointer_ref(pointer,node)
    else:parent=rt.reference(node.name)
    name,cell,index=parent
    if not isinstance(cell.value,StructValue):rt.fail(node,'成员访问需要结构体对象')
    field=node.field.name
    if field not in cell.value.fields:rt.fail(node,'结构体没有成员 '+field)
    member=cell.value.fields[field]
    return Reference(name+'.'+field,member,None,cell.readonly or getattr(parent,'readonly',False))


def is_member_lvalue(node):
    if isinstance(node,ast.StructRef):
        return node.type=='->' or is_member_lvalue(node.name)
    return isinstance(node,(ast.ID,ast.ArrayRef)) or isinstance(node,ast.UnaryOp) and node.op=='*'


def temporary_member(rt,node):
    """Select a value member without inventing an addressable temporary object."""
    value=rt.evaluate(node.name)
    if not isinstance(value,StructValue):rt.fail(node,'成员访问需要结构体对象')
    field=node.field.name
    if field not in value.fields:rt.fail(node,'结构体没有成员 '+field)
    member=value.fields[field]
    if isinstance(member.value,list):
        rt.fail(node,'暂不支持读取临时结构体的数组成员；请先将函数返回值保存到结构体变量')
    if member.value is None:rt.fail(node,'临时结构体成员 '+field+' 未初始化')
    return deepcopy(member.value)
