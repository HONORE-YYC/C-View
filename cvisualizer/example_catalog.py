"""Ordered, editable teaching programs shared by the UI and regression tests."""
from pathlib import Path

EXAMPLE_DIRECTORY = Path(__file__).parent / "examples"
EXAMPLE_CATALOG = (
    ("basics.c", "01 变量、赋值与宏"),
    ("types_casts.c", "02 类型、const 与转换"),
    ("bool_math.c", "03 布尔判断与数学函数"),
    ("input.c", "04 scanf 交互输入"),
    ("loops_arrays.c", "05 循环、数组与下标动画"),
    ("matrices.c", "06 二维数组与叠层动画"),
    ("functions.c", "07 函数与数组参数"),
    ("pointers.c", "08 指针与取地址"),
    ("strings_arrays.c", "09 字符串与只读参数"),
    ("large_arrays.c", "10 大数组与折叠查看"),
    ("list.c", "11 顺序表插入与删除"),
    ("stack.c", "12 栈的入栈与出栈"),
    ("queue.c", "13 循环队列与下标回绕"),
    ("mixed.c", "14 同一程序，多种结构"),
)
