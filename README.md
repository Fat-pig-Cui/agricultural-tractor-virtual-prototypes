# 农业拖拉机双论文理论仿真复现仓库

当前发布版本为 **v1.1.0**，对应两篇论文的大修实验和英文稿件：

| 论文 | 期刊 | 当前英文题目 | 可编辑主目录 |
| --- | --- | --- | --- |
| 论文一 | Machines | Observer-Based Hybrid Position Holding for an Electrohydraulic Agricultural Hitch: A Two-Chamber Virtual-Prototype Stress Test | `revisions/machines_major_revision/` |
| 论文二 | Energies | Phase-Informed ECMS with Soft SOC Safeguarding for a Virtual Hybrid Agricultural Tractor | `revisions/energies_major_revision/` |

两篇论文均为纯理论虚拟样机研究，参数、效率地图和噪声是声明的模型输入。仓库不包含实车、台架或组件标定数据，数值守恒检查和仿真通过不能作为实物验证。

## 当前稿件与结果

- 论文一正文为 `revisions/machines_major_revision/manuscript.pdf`，补充说明为同目录 `supplementary.pdf`。原20条冻结路径保持不变；新增观测接口移除、驻留匹配、积分细化、机械失配和噪声审计。累计293次数值重放跨组复用种子。统一1.0/0.5毫秒RK4的三控制器对照30/30通过，联合质量/阻尼/刚度±30%角点40/40通过；不代表全参数盒或全局稳定性保证。
- 论文二正文为 `revisions/energies_major_revision/manuscript.pdf`，补充说明为同目录 `supplement.pdf`。独立20路径中，自适应ECMS＋软SOC防护的平均归一化节油为5.950644%，相同防护固定ECMS为7.090609%；自适应方法干预更少，不能称其更节油。原投稿5.675991%采用原基线，不能将新旧分母差异解释为算法改进。
- 论文二约20%的结果保留为旧平台、完整未来信息、理想地图和±0.01终端SOC条件下的诊断：21.611%原始值、19.828%终端能量归一化值。它与当前在线算法使用不同实验协议。

`MDPI_template_ACS/` 的两个PDF是当前正文的镜像；其TeX入口保留本地路径关系。编译请使用下方脚本，它在各论文主目录内调用对应模板。

## 环境与复现

使用 Python 3.9 或更新版本，依赖安装命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

优先核对现成证据，无须重跑全部实验：

```bash
python3 tools/verify_release.py
python3 tools/check_paper2_revision_physics.py
python3 tools/check_paper2_revision_execution.py
```

大轨迹以 `.json.gz` 无损存储，SHA-256及原始字节数见 `manifests/compressed_results.json`。还原后可直接使用原仿真和绘图脚本：

```bash
python3 tools/materialize_release_data.py
./reproduce_paper1.sh
./reproduce_paper2.sh
```

完整运行会重新生成结果，耗时取决于计算机性能；应在另一个克隆中复现，保留原发布快照用于比较。论文一补强脚本默认复用70个已保存检查点；如需重新计算，将该克隆中的 `revisions/machines_major_revision/results/strengthening_checkpoints/` 移到其他目录，再运行脚本。原始10条混合控制器RK4结果仍按协议复用，新增计算60条。计时字段可能随设备变化，不能要求其逐位一致。

论文二实验协议保留计算时的源散列；最终代码仅将全采样轨迹的输出键名由 `trajectory_30s` 改为 `trajectory_full`，已在原 `revision_provenance.json` 记录。发布核验通过逐字还原这一处命名变化验证原散列，并重放两个独立比较臂的第一条路径，核对全部非计时字段。

安装PDFLaTeX后编译两篇正文和补充说明：

```bash
./build_manuscripts.sh
```

两篇论文使用不同版本的MDPI类文件，分别保存在其主目录 `Definitions/` 内。脚本从对应目录编译，避免套用另一篇的模板。

## 目录与版本边界

| 路径 | 内容 |
| --- | --- |
| `revisions/machines_major_revision/` | 当前论文一英文正文、补充说明、图表、协议和冻结结果 |
| `revisions/energies_major_revision/` | 当前论文二英文正文、补充说明、图表、参数台账和冻结结果 |
| `code/`、`tools/` | 当前虚拟模型、控制器、复现实验和核验入口 |
| `results/`、`papers/` | 既有论文结果、参数追溯和历史机制诊断；具体用途以清单为准 |
| `historical/` | 原投稿科学源文件与补充材料，供口径对齐；不作为当前主结论 |
| `manifests/` | 参数、来源同步清单和压缩数据校验记录 |

本文档和 `MANIFEST.md` 指向当前主协议。旧结果、旧代码说明及历史标签中的物理量解释，以两篇大修论文的纠正说明为准；例如旧论文一的虚拟损失系数不具有物理流量泄漏系数含义。各历史版本由Git标签保留。

审稿意见、评分截图、逐条回复、封面信、投稿包和专利材料保存在本地工作项目，不进入本公开科学归档。公开稿件保持生成时的内容，包括当时数据归档状态的表述；本次release已提供相应大修证据。GitHub发布成功不等于Zenodo已完成收录。

## 引用与作者

仓库地址：https://github.com/Fat-pig-Cui/agricultural-tractor-virtual-prototypes

概念DOI： https://doi.org/10.5281/zenodo.22754509 。本次软件版本的引用信息见 `CITATION.cff`；既有版本的独立DOI继续对应各自历史记录，不提前指定尚未返回的新版本DOI。

作者：Chenyu Cui、Peng Wang、Yucheng Zhang。通信邮箱：zhangyucheng@ict.ac.cn。
