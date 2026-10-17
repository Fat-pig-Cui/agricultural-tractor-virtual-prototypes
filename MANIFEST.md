# v1.1.0 科学材料清单

| 论文 | 当前主证据 | 对应位置 |
| --- | --- | --- |
| 论文一 | 原20路径、观测接口、驻留匹配、步长、机械/噪声、配对RK4及联合角点 | `results/paper1_two_chamber_v2.json`；`revisions/machines_major_revision/results/` |
| 论文一 | 两腔对象、冻结控制器与参数追溯 | `code/lift_control/{hydraulic_v2,lift_v2_experiment}.py`；`manifests/paper1_v2_parameter_manifest.csv`；`papers/reproducibility/` |
| 论文二 | 独立开发/评估、组件消融、相同防护固定ECMS、冻结Kp=40审计 | `revisions/energies_major_revision/results/{development_selection,ablation_and_comparison,submitted_path_ablation,frozen_kp40_audits}.json` |
| 论文二 | 功率与电池守恒、执行约束、参数台账 | 同目录 `{model_consistency_checks,execution_constraint_checks}.json`、`parameter_ledger.csv`；`code/energy_management/viability_ecms_v2.py` |
| 两篇论文 | 英文正文、补充说明与引用元数据 | 两个 `revisions/*major_revision/` 目录，含对应 `Definitions/` 和 `figures/` |
| 历史对齐 | 原投稿源和原补充实验 | `historical/paper1/`、`historical/paper2/` |

`results/` 中既有MPC、oracle、V2原稿结果用于历史对齐和限制性诊断。论文二21.611%原始值及19.828%归一化值为完整未来信息下的理想诊断，不能混入当前因果在线统计。

`manifests/local_sync_sources.json` 逐文件记录本地科学源和SHA-256；`manifests/compressed_results.json` 记录无损压缩前后散列；`MANIFEST.sha256` 校验整个发布树。运行复现或编译会更新文件，此后清单不再代表原发布快照。

审稿意见与回复、投稿页面信息、专利及临时文件均不在本公开清单内。原始本地项目保留这些内容。
