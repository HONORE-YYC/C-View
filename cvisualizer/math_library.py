"""Finite real-valued math.h/cmath teaching functions (C round ties away from zero)."""
import math
FUNCTIONS={name:getattr(math,name) for name in ('sqrt','pow','fabs','floor','ceil','trunc','sin','cos','tan','asin','acos','atan','atan2','exp','log','log10','log2','hypot','fmod')}
def c_round(x):
    fraction, integral = math.modf(x)
    return integral + (math.copysign(1.0, x) if abs(fraction) >= 0.5 else 0.0)
FUNCTIONS['round'] = c_round
BINARY={'pow','atan2','hypot','fmod'}
def execute(rt,node):
    name=node.name.name
    args=node.args.exprs if node.args else []
    expected=2 if name in BINARY else 1
    if len(args)!=expected: rt.fail(node,f'{name} 需要 {expected} 个参数')
    values=[rt.evaluate(arg) for arg in args]
    if any(not isinstance(v,(int,float)) for v in values): rt.fail(node,f'{name} 的参数必须为数值')
    try: value=FUNCTIONS[name](*values)
    except (ValueError,OverflowError,ZeroDivisionError): rt.fail(node,f'{name}：参数超出定义域或结果溢出')
    return rt.convert(value,'double',node)
