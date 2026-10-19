"""Token-aware normalization of the explicitly supported C++ cast spellings."""
from dataclasses import replace

def normalize(tokens, depth=0):
    if depth > 100 and tokens:
        from .errors import CError
        raise CError('类型转换嵌套过深（最多 100 层）', tokens[0].line, tokens[0].column)
    result=[]; i=0
    while i<len(tokens):
        token=tokens[i]
        if token.text in ('bool','true','false'):
            result.append(replace(token,text={'bool':'_Bool','true':'1','false':'0'}[token.text],expanded=True)); i+=1; continue
        if token.text in ('reinterpret_cast','dynamic_cast'):
            from .errors import CError
            raise CError('暂不支持此类型转换：'+token.text,token.line,token.column)
        if token.text not in ('static_cast','const_cast'):
            result.append(token); i+=1; continue
        def fail():
            from .errors import CError
            raise CError('不支持此类型转换语法或目标类型',token.line,token.column)
        j=i+1
        while j<len(tokens) and tokens[j].text.isspace(): j+=1
        if j>=len(tokens) or tokens[j].text!='<': fail()
        j+=1; target=[]
        while j<len(tokens) and tokens[j].text!='>':
            target.append(tokens[j]); j+=1
        if j>=len(tokens): fail()
        words=[t.text for t in target if not t.text.isspace()]
        permitted={'int','long','float','double','char','bool','_Bool','const','volatile','*'}
        if not words or any(w not in permitted for w in words): fail()
        if token.text=='static_cast' and '*' in words: fail()
        if token.text=='const_cast' and words.count('*')!=1: fail()
        j+=1
        while j<len(tokens) and tokens[j].text.isspace(): j+=1
        if j>=len(tokens) or tokens[j].text!='(': fail()
        # Lower the complete named cast as one parenthesized expression. This
        # retains its precedence and prevents postfix operators from binding to
        # the source operand (a cast result is never an lvalue in this subset).
        opening = j
        balance = 1
        j += 1
        while j < len(tokens) and balance:
            if tokens[j].text == '(':
                balance += 1
            elif tokens[j].text == ')':
                balance -= 1
            j += 1
        if balance:
            fail()
        result.append(replace(token,text='(',expanded=True))
        result.append(replace(token,text='(',expanded=True,cast_kind=token.text))
        result.extend(normalize(target, depth+1))
        result.append(replace(token,text=')',expanded=True))
        result.append(replace(token,text='(',expanded=True))
        result.extend(normalize(tokens[opening+1:j-1], depth+1))
        result.append(replace(token,text=')',expanded=True))
        result.append(replace(token,text=')',expanded=True))
        i=j
    return result
