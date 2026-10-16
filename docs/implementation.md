# 第一版实现步骤

目标：用 Python 构建可运行、可测试、能上传 GitHub 的中文 C 语言可视化桌面程序。

技术：Python 3.10+、PySide6、pycparser、pytest。执行器不依赖 Qt。

## 1. 建立项目与执行器

- [x] 在 `tests/test_engine.py` 编写混合语法、循环、数组及错误行为测试，先运行确认功能尚未实现。
- [x] `cvisualizer/language.py`：清除注释但保留源坐标，解析完整 main 或语句片段，运行前检查语法范围。
- [x] `cvisualizer/runtime.py`：作用域、32 位整数转换、数组边界、变量读写、C 算术和 printf。
- [x] `cvisualizer/engine.py`：将语法树转换为可暂停的步骤迭代器；`peek()` 返回尚未执行的语句，`step()` 执行并生成快照。
- [x] 验证：`python -m pytest tests/test_engine.py -q`。

关键验收代码：

```c
int sum = 0;
int data[5] = {0};
for (int i = 0; i < 5; i++) {
    if (i == 2) continue;
    data[i] = i * 2;
    sum += data[i];
}
```

最终 `sum == 16`，`data == {0, 2, 0, 6, 8}`，循环局部变量离开作用域后不可读取。

## 2. 实现播放与定位控制

- [x] `tests/test_controller.py` 先覆盖暂停不推进、停止后重启、反复命中循环体、不可达语句及步数限制。
- [x] `cvisualizer/controller.py` 定义 ready/running/paused/seeking/stopped/finished/error 状态。
- [x] `tick()` 在播放时执行一步，定位时每次最多执行一批，保证 Qt 能接收暂停和停止。
- [x] 指定语句由源行列坐标标识；定位停在执行前，单步才执行目标。
- [x] 验证：`python -m pytest tests/test_controller.py -q`。

## 3. 实现数据结构与桌面窗口

- [x] `tests/test_structures.py` 先验证顺序表有效区、栈顶、循环队列物理位置与逻辑顺序。
- [x] `cvisualizer/structures.py` 根据数组和用户绑定返回视图模型；非法绑定提供提示，原始数组保持可见。
- [x] `cvisualizer/editor.py` 实现行号、语法高亮和执行位置标记。
- [x] `cvisualizer/views.py` 使用 Qt Graphics Scene 绘制变量、数组及栈；展示访问和写入颜色、下标及指示器。
- [x] `cvisualizer/window.py` 接入编辑器、工具栏、速度、目标语句选择、绑定编辑、输出和日志。
- [x] 用 Qt 定时器调用控制器，运行中锁定代码；打开/保存 UTF-8 文件，切换代码前检查未保存修改。
- [x] `tests/test_gui.py` 验证窗口、控制按钮、保存与 Qt 绘制路径。

## 4. 示例、文档与交付

- [x] 添加普通 C 示例：基础混合语法、顺序表、栈、循环队列、混合结构；JSON 保存可视化绑定。
- [x] README 提供虚拟环境安装、启动、测试与 GitHub 上传步骤；详细教程解释执行器与扩展入口。
- [x] 提供 `pyproject.toml`、MIT LICENSE、.gitignore、GitHub Actions。
- [x] 运行完整测试、检查窗口截图、构建 wheel 并验证安装入口。
- [x] 打包纯源码 ZIP，排除环境、缓存和个人路径，附验证记录。

执行采用当前会话内逐项实现与验证；用户已明确要求提供具体实现和代码，不再增加设计确认步骤。
