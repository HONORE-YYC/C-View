# C View 开发与维护说明

本文面向项目维护者。面向使用者的安装和操作说明位于 [README](../README.md)。

## 开发环境

在项目目录中，使用自己的 Python 虚拟环境执行：

```text
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

无桌面环境运行 Qt 测试时，将环境变量 `QT_QPA_PLATFORM` 设置为 `offscreen`。

实现步骤见 [开发教程](tutorial.md)，动画实现记录见 [0.3 更新说明](update-0.3.md)。这些文档用于解释实现与验证过程，不作为用户首页的使用说明。

## 提交后续修改

先检查改动，并根据修改范围完成测试，再提交指定文件：

```text
git status
git diff
git add README.md
git commit -m "Update user documentation"
git push origin main
```

将示例中的 `README.md` 替换为本次实际修改的文件。不要提交虚拟环境、缓存、构建产物或凭据。推送后在 GitHub 的 Actions 页面检查对应提交的运行结果。

CI 会在 Windows / Ubuntu、Python 3.11 / 3.13 上运行测试并构建安装包。Linux 的 Qt 运行依赖及版本兼容约束以工作流和依赖文件为准。

## 文档维护

- README 保留安装、启动、操作、功能范围和必要限制；不要写入维护者的私人路径、本机故障记录或内部验收结果。
- 修改安装方法时，同步检查首次安装和再次启动两种流程。
- Anaconda 启动说明使用独立的 `c-view` 环境；命令可查阅 [Conda 环境管理](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html)和 [conda run](https://docs.conda.io/projects/conda/en/stable/commands/run.html)。
- 修改截图、示例或文件位置后，检查 Markdown 的相对链接。
