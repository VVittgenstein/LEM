# 来源与许可

## 动态地形数据

Müller, R. D., Hassan, R., Gurnis, M., Flament, N., Williams, S. E. (2018). Dynamic topography of passive continental margins and their hinterlands since the Cretaceous. Gondwana Research. DOI: [10.1016/j.gr.2017.04.028](https://doi.org/10.1016/j.gr.2017.04.028)。

- [EarthByte 数据介绍](https://www.earthbyte.org/dynamic-topography-of-passive-continental-margins-and-their-hinterlands-since-the-cretaceous/)
- [原始数据集](https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2018_GR/)
- [M2 PlateFrame 网格目录](https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2018_GR/DynamicTopoData/M2/PlateFrame/)
- [来源 README](https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2018_GR/README.txt)
- [数据许可](https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2018_GR/License.txt)：Creative Commons Attribution 4.0 International。

本模块下载六个未经修改的原始 NetCDF。来源副本、说明、许可和来源哈希保存在 `output/source/`。本项目的改动包括指定窗口提取、48 Ma 插值、逐段差分、统计拟合和新随机场生成。模型名称与 PlateFrame 参照系保留；生成场属于本项目派生结果。原论文未给出本项目圈层权重、随机生成规则或与 LEM 组合后的验证结论。

## 项目内代码依赖

只读复用 `data_generation/stage/mask_generator/common/io.py`、`world_orogen_gibbs/geometry.py` 和项目查看器的 FEM 颜色实现。本目录沿用所复用几何模块的 GNU GPL version 3 许可，完整文本见 [LICENSE](LICENSE)。World Orogen 的固定上游和已有改造范围见 [分区来源](../mask_generator/world_orogen/THIRD_PARTY.md) 与 [Gibbs 来源](../mask_generator/world_orogen_gibbs/THIRD_PARTY.md)。

本次新增 M2 来源冻结、差分统计、空间相关参数拟合、新速率场、外轮廓圈层衰减、时间接口和矢量图核对代码。Python 与依赖库沿用当前项目环境；实际版本和只读项目代码依赖哈希保存在 `output/runtime.json`。
