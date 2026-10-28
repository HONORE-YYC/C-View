"""Small C++ teaching extensions lowered to C AST with mapped coordinates."""
import re
from .preprocessor import LITERALS_COMMENTS


def lower(preprocessed):
    text=preprocessed.text
    mask=LITERALS_COMMENTS.sub(lambda m: ''.join('\n' if c=='\n' else ' ' for c in m[0]),text)
    offsets=[]
    for row in preprocessed.rows:
        offsets.extend(row)
    # rows contain the newline itself; flattening preserves character offsets.
    positions=list(range(len(text)))
    starts=[0]
    starts.extend(i+1 for i,c in enumerate(text) if c=="\n")
    casts={starts[line-1]+column-1: kind for (line,column),kind in preprocessed.cast_kinds.items()}
    edits=[]
    deletions=set()
    allocations={}
    references=set()
    # Match declaration headers, never call expressions or bitwise arguments.
    headers=re.compile(r'\b(?:[A-Za-z_]\w*\s+)*[A-Za-z_]\w*'
                       r'(?:\s*\*\s*(?:(?:const|volatile|restrict)\s+)*|\s+)'
                       r'[A-Za-z_]\w*\s*\(([^{};]*)\)\s*(?=[{;])')
    for header in headers.finditer(mask):
        if header[0].split()[0] in {'return', 'new', 'delete'}:
            continue
        for ref in re.finditer(r'\b(?:const\s+)?(?:struct\s+)?\w+(?:\s*\*)?\s*&\s*(\w+)\s*(?=[,)]|$)',header[1]):
            start=header.start(1)+ref.start()
            amp=mask.index('&',start,header.start(1)+ref.end())
            references.update((*offsets[index],ref[1]) for index in range(start,header.start(1)+ref.end()))
            edits.append((amp,amp+1,' '))
    for match in re.finditer(r'\bnew\s+((?:struct\s+)?[A-Za-z_]\w*(?:\s+long|\s+int)*)\s*',mask):
        end=match.end()
        typename=match[1]
        if end<len(mask) and mask[end]=='[':
            start=end
            depth=1
            end+=1
            while end<len(mask) and depth:
                depth+=(mask[end]=='[')-(mask[end]==']')
                end+=1
            if depth:
                continue  # Let the parser report the unmatched bracket.
            typename+=text[start:end]
        initialized=re.match(r'\s*\(\s*\)',mask[end:])
        if initialized:
            end+=initialized.end()
        replacement='sizeof('+typename+')'
        allocations[offsets[match.start()]]=bool(initialized)
        edits.append((match.start(),end,replacement))
    for match in re.finditer(r'\bdelete\b\s*(\[\s*\])?\s*([^;]+)',mask):
        deletions.add(offsets[match.start()])
        function='__cv_delete_array' if match[1] else '__cv_delete'
        edits.append((match.start(),match.end(),function+'('+text[match.start(2):match.end(2)]+')'))
    for start,end,replacement in sorted(edits,reverse=True):
        origin=offsets[start]
        text=text[:start]+replacement+text[end:]
        offsets[start:end]=[origin]*len(replacement)
        positions[start:end]=[start]*len(replacement)
    rows=[[]]
    preprocessed.cast_kinds={}
    for char,origin,position in zip(text,offsets,positions):
        if position in casts:
            preprocessed.cast_kinds[(len(rows),len(rows[-1])+1)]=casts[position]
        rows[-1].append(origin)
        if char=='\n':rows.append([])
    preprocessed.text,preprocessed.rows=text,rows
    return allocations,references,deletions


def linked_types(program):
    from pycparser import c_ast as ast
    result={}
    for name,spec in program.structs.items():
        if not spec.fields or len(spec.fields)!=2:continue
        data=[];links=[]
        for field in spec.fields:
            node=field.type
            if isinstance(node,ast.PtrDecl) and isinstance(node.type,ast.TypeDecl) and isinstance(node.type.type,ast.Struct) and 'struct '+node.type.type.name==name:
                links.append(field.name)
            elif isinstance(node,ast.TypeDecl) and isinstance(node.type,ast.IdentifierType):
                data.append(field.name)
        if len(data)==len(links)==1:result[name]={'data':data[0],'next':links[0]}
    return result

from pycparser import c_generator


class SourceGenerator(c_generator.CGenerator):
    """Keep teaching extensions visible while the interpreter uses ordinary C ASTs."""
    def __init__(self, program):
        super().__init__()
        self.program = program

    def origin(self, node):
        if node.coord is None:
            return None
        return self.program.preprocessed.original(max(1,node.coord.line-self.program.offset),node.coord.column)

    def visit_UnaryOp(self, node):
        origin=self.origin(node)
        if node.op=='sizeof' and origin in self.program.allocations:
            return 'new '+self.visit(node.expr)+('()' if self.program.allocations[origin] else '')
        return super().visit_UnaryOp(node)

    def visit_BinaryOp(self, node):
        from .stream_io import chain
        stream = chain(node)
        if stream:
            name, args = stream
            operator = ' >> ' if name == 'cin' else ' << '
            return name + operator + operator.join(self._parenthesize_unless_simple(arg) for arg in args)
        return super().visit_BinaryOp(node)

    def visit_FuncCall(self, node):
        if getattr(node.name,'name',None) in ('__cv_delete','__cv_delete_array') and self.origin(node) in self.program.deletions:
            return ('delete[] ' if node.name.name=='__cv_delete_array' else 'delete ')+self.visit(node.args)
        return super().visit_FuncCall(node)

    def visit_Decl(self, node, no_type=False):
        text=super().visit_Decl(node,no_type)
        origin=self.origin(node)
        if origin and (*origin,node.name) in self.program.reference_parameters:
            matches=list(re.finditer(r'\b'+re.escape(node.name)+r'\b',text))
            if matches:
                index=matches[-1].start()
                text=text[:index]+'&'+text[index:]
        return text
