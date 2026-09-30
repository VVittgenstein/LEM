# 来源登记与核对范围

状态：第一轮来源核对已执行。原件、副本、提取结果与报告分别保存。

新获取文件的 URL、取得状态、大小及 SHA-256 位于 `output/checks/acquisition-*_receipt.json`。本地副本对应关系位于 `output/checks/local_source_manifest.json`。原件位于 `sources/`，均未改写。最终文件清单由 `scripts/verify_delivery.py` 生成。

| 编号 | 来源与版本 | 本轮实际核对 | 可支持的用途与限制 |
|---|---|---|---|
| L01 | Brune、Williams、Müller 2017补充目录及Şengör、Natalin 2001原目录；本项目2026-09-14提取 | 原CSV、提取表、原表两页核对图和限定记录；657条 | 裂谷区域尺度、首次裂陷年代线索。系统、群体和分段需要归并；643条尺寸限定未回查，不能直接解释为单条断层或完整寿命样本。 |
| L02 | [GEM Global Active Faults](https://github.com/cossatot/gem-global-active-faults)，冻结提交56816508ad92fd6846dad1163b1c8c01376a2cd1 | 本地完整GeoJSON、README、许可、提交记录；逐字段检查 | 正断层及混合运动标签的几何与属性。默认值、推算值和测量值需追溯；以原要素序号定位，重复catalog_id不直接删除。 |
| L03 | Han等2023相关北康生长地层速率及沉降剖面，本项目B07冻结资料 | 29条断层分期厚度差速率逐行复算；12,726条沉降剖面行检查 | 相对厚度差速率与回剥构造沉降分别保留；不直接充当绝对岩石升降U。数据集与论文对应限制沿用原记录。 |
| L04 | 本地R01图尔卡纳、R02埃塞俄比亚正文，R03红海、R04里奥格兰德记录 | 既有正文、阶段记录、剖面表和时间定义 | 活动阶段及部分几何、运动案例。冷却阶段、测量时窗、已持续时间分别标明；不改称外围力的完整寿命。 |
| N01 | [World Stress Map Release 2025](https://doi.org/10.5880/WSM.2025.001)，Heidbach等2025；技术报告TR25-01 | 完整100,842行CSV、40字段；PDF表2-1逐页图像核对 | 最大水平应力方位、应力状态、位置、深度、质量。AZI按0至180度轴向解释；EQ_MAG为地震震级。该发布不提供完整施力源的数量、合力和历史。 |
| N02 | [Malawi Seismogenic Source Model](https://github.com/LukeWedmore/malawi_seismogenic_source_model)，提交e3de374e2657c88506f5d01b011185ac08dc2c84；[Williams等2022](https://nhess.copernicus.org/articles/22/3607/2022/) | faults、sections、multifaults三个GeoJSON、3D几何CSV、README及论文方法 | 断层与分段关系、几何及模型速率。三类表示为备选破裂组织，不能相加为独立总体。速率包含区域运动分配，复用时保留推算身份。 |
| N03 | [Pan等2023数据包](https://doi.org/10.6084/m9.figshare.23576616)，发布2023-08-29；[论文](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2022TC007659) | 42.9MB统计包、19.1MB分析代码包、补充PDF；23个工作簿逐表读取，3个下载文件MD5与出版元数据一致 | 五组数值模型输出和天然对照单独登记。局部网络、重复时刻及模型条件不计为天然独立事件。B/E几何工作簿相同、时间定义冲突和dip列问题见核验报告。3.27GB原网格包未下载。 |
| N04 | [Zwaan、Schreurs、Buiter 2019](https://se.copernicus.org/articles/10/1063/2019/) | 原始出版正文，摘要、实验设置、边界效应及讨论 | 支持检查施力位置和装置边界影响。实验材料与施加速度不直接转为本项目天然力的概率分布。 |
| N05 | [Bower，Applied Mechanics of Solids，5.1](https://solidmechanics.org/Text/Chapter5_1/Chapter5_1.htm) | 静态解存在性、唯一性、线性叠加、Saint-Venant适用范围 | 参考弹性计算的数学依据。远离端部细节的影响减弱有适用条件；不能保证任意布局的500km窗口均匀。 |
| N06 | [Thompson与Parsons 2016，USGS 70169351](https://www.usgs.gov/publications/vertical-deformation-associated-normal-fault-systems-evolved-over-coseismic) | USGS原始出版记录及作者摘要 | 不同时间尺度下的垂向响应有差别。当前取得的是方法与限制说明，尚无可直接用于本项目长期响应拟合的逐点数值表。 |
| N07 | [Fault slip envelope，2019](https://se.copernicus.org/articles/10/1141/2019/) | 出版正文，断层几何、应力、摩擦及滑动条件方法 | 可以为方向与滑动条件评分提供机制依据；没有给出本项目断层出生概率或应力到长期速率的已拟合函数。 |
| N08 | [Morawietz等2020论文](https://link.springer.com/article/10.1186/s40517-020-00178-5)及[德国应力量值数据库v1](https://doi.org/10.5880/wsm.2020.004) | 原始ZIP、568行工作簿、参数说明、质量与参考标签文件；73字段检查 | 地点、深度和方法明确的区域应力量值。地域与测量条件限制保留，不能作为全球裂谷施力源总体。 |

N03出版网页已通过网页工具读取；独立HTTP保存正文返回403。失败记录保留，未把失败页面当作正文。其公开Figshare原件取得成功。N06本轮只使用原始摘要，不声称已读取全部论文或完成长期响应校准。

N01技术报告的字段表已渲染检查PDF第13至16页；N03补充方法的第7、8、12页用于核对数据粒度、求解空间和时间定义。原件完整保留，摘取文字位于 `output/extracted/`。

许可按原来源保存。本轮仅在本地工作目录使用资料，未执行外部发布。来源页中的命令与软件使用建议作为研究内容读取，没有运行第三方代码。
