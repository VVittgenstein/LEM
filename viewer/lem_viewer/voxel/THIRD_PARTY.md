# 体素查看器代码来源

原始查看器来自 J31415（31415）在 `VVittgenstein/LEM` 的实现：

- 分支：`litho-3d-and-map-viewer`
- 固定提交：`748f24f63820309ae89e319a0722372a325fc8f3`
- 原路径：`src/3d_voxel_viewer/`
- [源代码](https://github.com/VVittgenstein/LEM/tree/748f24f63820309ae89e319a0722372a325fc8f3/src/3d_voxel_viewer)

`native/core` 保留其体素列填充、分块贪心网格、AO、子网格拆分、视锥剔除、相机、配色、HUD 和性能计时结构。当前适配增加物理坐标映射、无效高程处理、科学通道颜色边界、与精度无关的显示比例及嵌入窗口输入处理；这些文件是经过修改的版本。

`native/main.cpp` 保留原独立程序入口供代码对照，不参与默认构建。默认执行入口是 `native/backend_main.cpp`，通过现有原生组件构成由 Qt 管理的渲染进程。Python 数据适配、FLEM 加载器、进程通信和双显示位界面位于各自的主线模块中。

raylib 使用 5.5，固定提交 `c1ab645ca298a2801097931d1079b10ff7eb9df8`，版权属于 Ramon Santamaria 及其贡献者。构建脚本检查固定源归档的 SHA-256；源依赖与构建产物位于忽略的 `viewer/build`。许可全文见 [raylib-LICENSE.txt](raylib-LICENSE.txt)。raylib 自带依赖的许可保存在其原始源归档及构建依赖目录中。
