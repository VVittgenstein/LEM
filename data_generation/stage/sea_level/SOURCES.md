# 海平面曲线来源

原数据获取于2026-09-08，本轮直接读取本地冻结文件；实际输入SHA-256及列名保存于 `output/sources.json`。本轮读取了各文件的数据说明，并核对发布方页面。

## Miller等2020年平滑数据

Miller, Kenneth G.; Browning, James V.; Schmelz, W. John; Kopp, Robert E.; Mountain, Gregory S.; Wright, James D. (2020). *Smoothed Cenozoic sea-level relative to modern from deep-sea geochemical and continental margin records*. PANGAEA. DOI: [10.1594/PANGAEA.923139](https://doi.pangaea.de/10.1594/PANGAEA.923139).

- 发布日期：2020-09-28。
- 许可：CC BY 4.0，见发布页。
- 原文件：`F:\LEM\references\data\2026-09-08-q1-data\A\miller2020-smoothed.tab`。
- 原文件含3193点，98万至6482万年BP，间距2万年；本模块使用至4800万年的部分。
- 作者已用49点高斯卷积处理，发布页说明去除短于490 ka的周期。本模块直接使用该平滑产品。

## Miller等2020年未平滑数据

Miller, Kenneth G.; Browning, James V.; Schmelz, W. John; Kopp, Robert E.; Mountain, Gregory S.; Wright, James D. (2020). *Cenozoic sea-level relative to modern from deep-sea geochemical and continental margin records*. PANGAEA. DOI: [10.1594/PANGAEA.923126](https://doi.pangaea.de/10.1594/PANGAEA.923126).

- 发布日期：2020-09-28。
- 许可：CC BY 4.0，见发布页。
- 原文件：`F:\LEM\references\data\2026-09-08-q1-data\A\miller2020-unsmoothed.tab`。
- 读取GTS2012年代列与相对现代海平面列。原文件延伸至0 BP，能够覆盖所需桥接和重叠区间。
- 海平面由地球化学记录及校准关系重建。本轮仅使用桥接与窗口比较附近的观测及插值所需相邻点。

两份Miller资料对应论文：Miller et al. (2020), *Cenozoic sea-level and cryospheric evolution from deep-sea geochemical and continental margin records*, Science Advances 6, eaaz1346. DOI: [10.1126/sciadv.aaz1346](https://doi.org/10.1126/sciadv.aaz1346)。

## Spratt与Lisiecki 2016年

Spratt, R. M.; Lisiecki, L. E. (2016). *A Late Pleistocene sea level stack*. Climate of the Past 12, 1079–1092. DOI: [10.5194/cp-12-1079-2016](https://cp.copernicus.org/articles/12/1079/2016/)。论文许可为CC BY 3.0。

NOAA存档：*Global Sea Level Reconstruction using Stacked Records from 0–800 ka*. Study 19982，DOI: [10.25921/rd66-5820](https://doi.org/10.25921/rd66-5820)，[数据入口](https://www.ncei.noaa.gov/access/paleo-search/study/19982)。

- 原文件：`F:\LEM\references\data\2026-09-08-q1-data\A\spratt2016-noaa.txt`。
- 本模块读取 `SeaLev_longPC1`，即五记录堆叠版本，0至798 ka，共799点、间距1 ka。
- 同文件的七记录版本覆盖0至430 ka，本模块未将它另加到五记录版本。
- 0 BP的原始重建值8.96 m和原始不确定度保留。NOAA元数据说明年代依据LR04等已发表年龄模型；本轮沿用其年代坐标。

## 数值插值

[SciPy PchipInterpolator文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html)：保持数据形状与局部单调性的分段三次Hermite插值，一阶导数连续。本文档支持数值方法的性质；局部衔接窗口与权重是本项目的工程选择。

原始历史讨论入口：[639e9e4e](../../../docs/sessions/2026-09-09-lem-pipeline-execution-marine-recovery-639e9e4e/conversation.md)。本轮单一年代曲线取代此前提出的长短期叠加与短期循环设计；具体实现及当前范围见 [README.md](README.md)。
