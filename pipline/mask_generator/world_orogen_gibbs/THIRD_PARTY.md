# 来源与许可

分区增长与噪声通过项目内只读依赖 `../world_orogen/partitions.py`、`../world_orogen/noise.py` 复用。其固定上游为 [World Orogen](https://github.com/raguilar011095/planet_heightmap_generation/tree/cc2662b4edd52231c4f65d8765f3ef12cd82d9b7)，版本 `cc2662b4edd52231c4f65d8765f3ef12cd82d9b7`，许可为 GNU GPL version 3。原始下载文件、来源哈希和完整说明见 `../world_orogen/THIRD_PARTY.md`。本模块使用同一许可，完整文本见 `LICENSE`。

本模块的整组评分、二值 Gibbs 与温度交换抽样内核、诊断、导出和查看页为本次项目实现。源代码中列明改造和数学依据；公式中的评分不表示地质物理能量。

- [Rasmussen 与 Williams：Covariance Functions](https://gaussianprocess.org/gpml/chapters/RW4.pdf)
- [Cosma Shalizi：Markov Random Fields，2020](https://stat.cmu.edu/~cshalizi/dst/20/lectures/22/lecture-22.html)
- [Stan Reference Manual：Posterior Analysis](https://mc-stan.org/docs/reference-manual/analysis.html)

这些资料提供数学与抽样依据，没有证明当前参数能够复现地台形态的真实地学分布。
