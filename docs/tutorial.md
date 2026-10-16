# 从代码到画面：具体实现教程

这份教程对应已经实现的源码。它把教学 C 子集解释器、播放控制和桌面界面分开，因此以后扩展链表或函数调用时，不必重写整个项目。

## 第一步：把 C 代码解析为语法树

文件：`cvisualizer/language.py`。

`Program(source)` 接收用户输入，调用 `preprocessor.py` 中的预处理器：替换注释为空格，识别兼容的头文件，按定义顺序展开对象宏和函数式表达式宏，并建立展开字符到原文件行列的映射。替换不会作用于字符串，也不会把相邻 token 合并为新运算符。随后屏蔽字符串判断是否已经有 main。如果是普通语句片段，就临时包在 main 中，并记录行号偏移。

核心调用是：

```python
from pycparser import c_parser

tree = c_parser.CParser().parse('int main(void) { int x = 1 + 2; }')
```

`int x = 1 + 2` 会变成声明节点，初始化部分是二元运算节点。解析之后还要检查节点是否处于实现范围。pycparser 能解析指针，不意味着我们的解释器已经能执行指针，因此 `_check()` 在执行前拒绝它。

源码位置使用 `Location(line, column, text, kind)`。行号之外保留列号，是为了区分同一行上的 `x++; y++;`。原始文件不会因自动包装而改变。

## 第二步：建立变量和数组的运行状态

文件：`cvisualizer/runtime.py`。

`Runtime.scopes` 是一个由外到内的作用域列表，每层用字典保存变量。进入代码块时压入新字典，离开时弹出；读取时从最内层往外找。这使内层 `int x` 可以暂时遮蔽外层 `x`。

```python
@dataclass
class Cell:
    type: str
    value: object
```

标量的 value 是 int、float 或表示未初始化的 None；数组的 value 是列表。`reference()` 找到变量或数组元素，`read()` 检查未初始化，`write()` 做类型转换并记录写入位置。`snapshot()` 深复制可见变量，使历史步骤不会被后续修改覆盖。

整数除法不能直接使用 Python 的 `//`：Python 对负数向负无穷取整，而 C 对整数除法向零截断。实现中先除绝对值，再恢复商的符号；余数使用 `left - quotient * right`。

逻辑短路也必须显式处理。若 `left` 为零，`left && right` 不求值 right；因此 `0 && (1 / 0)` 不产生除零错误。

`abs`、`rand`、`srand` 由 Runtime 内置实现。随机状态属于本次执行，不依赖 Python 全局随机数；重置恢复默认种子，相同种子可重放。`srand` 的无返回值不能用于赋值或条件。

## 第三步：用生成器把程序拆成可以暂停的步骤

文件：`cvisualizer/engine.py`。

`Engine._walk()` 递归访问语法树，但不是一次运行到底，而是在每个可展示操作前 yield 一个 `Action`。Action 包含源码位置与尚未调用的函数。

```python
engine = Engine('int x = 1; x = x + 2;')
pending = engine.peek()   # 当前语句尚未执行
first = engine.step()    # 执行声明，x = 1
second = engine.step()   # 执行赋值，x = 3
```

`peek()` 只准备下一步，`step()` 才执行动作并返回 Event。Event 包含执行前后的变量快照、源码位置、结果说明、输出、读取位置和写入位置。单步执行前备份状态；如果出现受控运行错误，恢复变量、输出及随机数状态。

循环的生成器顺序是：初始化 → 条件 → 循环体 → 更新 → 条件。每次条件判断都会 yield，因此即便 `while(1){}` 没有循环体，仍然可以暂停、停止，也能触发步数上限。

`break`、`continue`、`return` 使用内部控制流异常，不是运行错误。循环捕获 break/continue；main 捕获 return；作用域清理由 finally 保证。for 的 continue 仍然执行更新部分。

## 第四步：把播放控制做成独立状态机

文件：`cvisualizer/controller.py`。

状态包括 `ready`、`running`、`paused`、`seeking`、`stopped`、`finished` 和 `error`。这些状态决定按钮是否可用、编辑器是否锁定和计时器是否继续。

Qt 定时器调用 `Controller.tick()`：普通播放每次执行一个步骤；定位时每次最多推进 40 步，并有约 12 毫秒的批次时间限制。这样定位较远语句时，界面仍能响应暂停和停止。

定位通过比较待执行 Action 的行、列和种类完成。命中后暂停，而不是先执行再停，因此用户可以单独观察目标语句的效果。目标在循环中时，执行目标后再次定位，就能找到后续迭代；若程序结束仍未命中，给出“未到达”提示。

## 第五步：从变量推导数据结构视图

文件：`cvisualizer/structures.py`。

普通 C 数组不自带“这是栈”的信息，因此使用显式 Binding：

```python
Binding('stack', 'stack', top='top')
Binding('data', 'list', length='length')
Binding('queue', 'queue', front='front', rear='rear')
```

`describe(binding, variables)` 返回 Structure，包括物理数组、有效元素下标、逻辑顺序、指示器和错误信息。

循环队列的逻辑长度与下标分别为：

```python
count = (rear - front + capacity) % capacity
indices = [(front + i) % capacity for i in range(count)]
```

绑定只影响绘制，不能影响执行。哪怕用户写错 top，解释器也不会偷偷纠正；视图显示错误并保留原数组。

## 第六步：实现 Qt 桌面界面

文件：`editor.py`、`views.py`、`bindings.py`、`window.py`。

- `CodeEditor` 基于 QPlainTextEdit，添加行号栏、语法高亮与执行行颜色。
- `MemoryView` 基于 QGraphicsView，同时绘制标量和数组。None 对应灰框和名字，已有值对应绿框和「名字 = 值」；读写只改变边框颜色。执行前后快照用于显示本步的值变化，并通过变量身份避免同名变量跨作用域误高亮。结构有效范围通过文字标记，栈按垂直方向展示，循环队列附逻辑顺序。
- `BindingDialog` 编辑结构映射，保存为同名 `.cview.json`。
- `MainWindow` 组织三个区域、文件操作与按钮。每次执行后从 `runtime.snapshot()` 读取当前作用域状态，防止已经离开作用域的局部变量一直显示。

UI 不执行 C 运算，也不重新推断变量的值。它只展示执行器给出的结果。`main.py` 创建 QApplication、窗口并进入 Qt 事件循环。

0.3 版在 `Runtime.evaluate_sources()` 中收集赋值值的来源，在 `Event.transfers` 中记录「源单元 → 目标单元」及变量身份。数组下标的读取与逗号表达式的被丢弃结果使用独立来源帧，避免产生错误的复制箭头。`motion.py` 遍历 AST 的声明与作用域，把数组和直接下标变量绑定；运行时只展示仍然可见的对应声明。

`animations.py` 使用 `QVariantAnimation` 在连续时间上插值。绿色箭头按曲线路径逐渐增长、淡出，下标指针在旧位置和新位置之间移动。每一帧只修改覆盖层图元，方框与文字不重建；`MemoryView.render()` 对相同状态去重，保证刷新不会重启动画。窗口定时器在动画期间等待；暂停、恢复、停止、完成和重布局通过动画状态与结束信号同步按钮。

## 第七步：验证和发布源码

首先验证执行器的数值、作用域和循环，再验证控制器的暂停和定位，最后用 Qt offscreen 模式验证窗口。

```powershell
python -m pytest -q
```

示例测试还检查最终结构内容，而不只是“运行没报错”。例如队列示例必须得到 `[30, 40, 50, 60]` 的逻辑顺序，否则回绕实现可能有问题。

`pyproject.toml` 定义依赖、命令入口和示例包数据；`.github/workflows/tests.yml` 在 push 和 pull request 时运行测试。后续提交与发布步骤见[开发与维护说明](development.md)。

## 下一步怎么扩展

新增语法时，先在测试里写出具体 C 代码及预期状态，再扩充 language 的允许节点、Runtime 的值模型或 Engine 的控制流。新增数据结构时，优先增加 Binding/Structure 类型及绘图，不把结构操作硬编码成按钮。

链表需要先实现指针和分配的内存对象；自定义函数需要调用栈、参数绑定和返回值传播。逐步回退需要完整执行状态记录或从头重放，不能只改画面上的数字。
