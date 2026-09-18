# 集中测试入口

所有软件测试、数值验证实验和性能测试程序集中在本目录。生成过程使用的样本校验函数仍位于对应功能模块，测试调用这些函数。

从项目根目录运行：

```powershell
.\lem-env-win\Scripts\python.exe tests\run.py --list
.\lem-env-win\Scripts\python.exe tests\run.py
.\lem-env-win\Scripts\python.exe tests\run.py --group viewer
.\lem-env-win\Scripts\python.exe tests\run.py --group time_api
```

无 `--group` 时运行 13 组默认软件测试。`time_api` 使用已保存的汇聚事件数据；概率模型研究核查、数值步长实验和性能矩阵需显式选择。性能矩阵需提供运行参数，例如 `--group benchmarks -- --steps 5 --rounds 1`。以上命令示例不代表已经执行这些数值实验。

解释器与各组搜索路径保存在 `suites.json`：查看器使用 `lem-env-win`，已有生成实现使用 `lem-env`，独立阶段使用 D 会话的既有环境。测试运行器会在计算环境缺少 pytest 时，从查看器环境中读取已安装的 pytest 及纯 Python 辅助依赖，追加位置位于计算环境自身库之后。各阶段在独立进程中执行，避免同名模块相互影响。

日志和汇总默认写入 `output/tests`，可用 `--output` 指定。Gibbs 测试和接口回归的临时结果也写入该测试输出目录。

根目录 `python -m pytest` 默认只收集查看器测试；完整跨环境核查使用 `tests/run.py`。数值实验需要对应数据和计算环境，完整矩阵的运行范围由具体任务确定。

体素合并的真实窗口检查通过 `--group viewer_native` 显式运行，需要已构建的 C++ 后端和可用的 Windows 桌面/OpenGL。它覆盖左右视图组合、尺度、输入、窗口恢复和原生进程回收；默认软件测试仍可离屏运行。构建与操作说明见 [viewer/README.md](../viewer/README.md)。

| 位置 | 内容 |
|---|---|
| viewer | 查看器回归 |
| data_generation/stage | 当前六个生成阶段的测试 |
| experiments/lem_pipeline | 旧流程测试、步长收敛、海洋求解器诊断和结果判定 |
| benchmarks | 环境检查、性能测试和报告生成；原结果仍位于根目录 bench/results |

背景垂向运动的测试随本地源码保存；其目录迁移没有扩大该阶段的公开范围。
