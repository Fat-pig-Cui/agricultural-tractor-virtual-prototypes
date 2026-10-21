# 农业拖拉机双论文：当前论文与最小复现源码

本仓库仅维护两篇论文的最新版、模型与算法代码、实验生成脚本、参数清单和文档。按作者要求，不附带冻结实验数据、轨迹、检查点、开发搜索输出或统计结果文件。旧稿和审稿通信不在工作树内；既有Git历史与标签保留。

| 论文 | 当前阶段 | 正文 | 补充说明 |
| :---: | :---: | :---: | :---: |
| 论文一 / Machines | 已接收稿 | [正文PDF](manuscripts/paper1/manuscript.pdf) | [S1–S13](manuscripts/paper1/supplementary.pdf) |
| 论文二 / Energies | 作者修正校样 | [正文PDF](manuscripts/paper2/manuscript.pdf) | [S1–S7](manuscripts/paper2/supplementary.pdf) |

论文一：Observer-Based Hybrid Position Holding for an Electrohydraulic Agricultural Hitch: A Two-Chamber Virtual-Prototype Stress Test。

论文二：Phase-Informed ECMS with Soft SOC Safeguarding for a Virtual Hybrid Agricultural Tractor。

正文及补充PDF与作者当前文件逐字节相同。论文二公开TeX仅去除编辑问询和作者回复等注释文字，保留有效内容与出版社校样标记。原始制作端文件在作者本地保留。校样不代表最终出版版，正式卷期和文章DOI以出版社为准。

## 目录

| 路径 | 内容 |
| :---: | :---: |
| `manuscripts/paper1/`、`manuscripts/paper2/` | 当前英文正文、补充说明、TeX、模板和插图 |
| `code/` | 液压、观测器、供油扩展、功率分流和ECMS等模型与算法 |
| `tools/` | 实验生成、检查及独立工作区运行脚本 |
| `parameters/` | 声明的理论模型参数清单；实验特定设置和种子见脚本及论文 |
| `manifests/` | 本地来源与文件散列记录 |

论文内用于展示结论的图表与补充说明继续保留。原始实验数据仍在作者科研工作区，此检出不提供直接读取冻结轨迹或复算其统计的功能。

## 安装和完整性检查

```sh
python3 -m pip install -r requirements.txt
python3 tools/verify_release.py
```

完整性检查使用Python标准库；仿真依赖NumPy、SciPy与Matplotlib。正文和补充说明可使用PDFLaTeX编译：`./build_manuscripts.sh`。该命令会覆盖克隆内的PDF，建议在独立克隆运行。

## 从源码复现

所有入口要求指定一个尚不存在、位于本检出之外的工作目录。入口复制源码并创建空输出目录，从头计算，不复制或下载已有实验结果。

先运行短程检查：

```sh
python3 tools/run_current_experiments.py smoke --workspace ../tractor-smoke
```

该检查生成论文一两组协议，运行12秒代表性液压算例，以及论文二种子5120的完整600秒控制与基线算例。它用于确认源码能够在空工作区执行，不等同于重算论文全部实验。

完整的主要实验入口：

```sh
./reproduce_paper1.sh --workspace ../tractor-paper1
./reproduce_paper2.sh --workspace ../tractor-paper2
```

论文一重算88路径供油对照、54路径资源目标开发以及后续8路径独立验证。论文二重算开发选参、20路径独立对照、消融、地图/容量审计及原投稿种子组归因，耗时可能较长。脚本会在独立工作区保存输出及续跑检查点；全部开发和失败路径应保留，不能仅保留最优结果。`--prepare-only` 仅准备目录。

额外入口：

```sh
python3 tools/run_current_experiments.py paper2-physics --workspace ../tractor-physics
python3 tools/run_current_experiments.py paper2-execution --workspace ../tractor-execution
python3 tools/run_current_experiments.py paper2-ideal --workspace ../tractor-ideal
```

约20%的情形由 `paper2-ideal` 单独生成：它使用完整未来信息、理想地图和较宽终端SOC带，必须与在线主协议分列；不能把未通过连续重放的24.087%网格值作为有效在线结果。具体生成方法和边界见论文与脚本。

代码中的历史计算路径用于兼容原科学脚本，只在独立工作区创建相应目录。缺少历史冻结参考时，论文二从代码重算原基线设置，并将历史逐字节一致性检查标为未执行。控制器、模型、种子与实验参数保持原样；不声称用最终实现逐位重建所有早期诊断，也不承诺自动重绘所有论文图表。计时结果随平台变化。

## 理论边界与引用

两篇论文均为理论虚拟样机研究，参数与地图按声明定义，没有实车、台架或目标组件标定数据。有限数值试验不构成全局稳定性、递归可行性或硬件验证。

作者：Chenyu Cui、Peng Wang、Yucheng Zhang。通讯作者：Yucheng Zhang，邮箱 `zhangyucheng@ict.ac.cn`。

研究材料的[Zenodo概念DOI](https://doi.org/10.5281/zenodo.22754509)对应版本集合，不替代文章DOI。引用信息见 `CITATION.cff`，许可见 `LICENSE.md`。本轮未创建新的GitHub release或操作Zenodo。
