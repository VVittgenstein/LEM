# 来源与许可

本目录只读复用项目内的mask与海域分配模块，包括通用IO、已选mask读取及几何检查。其World Orogen上游版本和改造记录分别见：

- [mask分区来源](../mask_generator/world_orogen/THIRD_PARTY.md)
- [Gibbs模块来源](../mask_generator/world_orogen_gibbs/THIRD_PARTY.md)
- [海域分类来源](../seafloor_generator/THIRD_PARTY.md)

本目录沿用所复用模块的GNU GPL version 3许可，完整文本见 `LICENSE`。本轮新增固定剖面统计、连续高程、起伏拟合、等高线导出和核查代码；没有复制原始真实水深栅格作为生成高程。

坡折和坡度参考来自F会话冻结剖面，局部起伏参考来自A会话统计，原始数据的来源、版本与适用范围见对应记录。每批产物保存实际输入的SHA-256和使用的Python库版本。
