# 来源与许可

本目录只读复用项目内 `../mask_generator/common/io.py`、`../mask_generator/common/render.py` 与 `../mask_generator/world_orogen_gibbs/geometry.py`。几何模块继续使用既有World Orogen分区的数据结构与邻接计算，当前执行直接读取已生成的分区和台地数组。

被复用模块的上游固定版本、改造记录及GNU GPL version 3许可见：

- [World Orogen来源说明](../mask_generator/world_orogen/THIRD_PARTY.md)
- [Gibbs模块来源说明](../mask_generator/world_orogen_gibbs/THIRD_PARTY.md)

本目录沿用被复用模块的GNU GPL version 3许可，完整文本见 `LICENSE`。海域测宽、参考重算、四个函数拟合、完整地块类型分配、测试和导出为本轮实现。没有把上游形状方法当作深浅海统计规律的证据。

自然参考来自已有F会话的冻结站点剖面。逐文件SHA-256与参考总体文件保存于每批输出的 `reference/sources.json`；本轮使用的新观测距离和数据限制见 `README.md`。
