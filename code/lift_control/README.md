# 论文一：当前虚拟模型

`hydraulic_v2.py` 与 `lift_v2_experiment.py` 实现两腔液压、机械对象、观测器及保持监督；`lift_reserve_supply.py` 实现主供油可用性扩展与边界资源计量。当前正文及适用边界见 `manuscripts/paper1/`。

公开检出不附实验结果。`tools/run_paper1_supply_retuning.py` 从头执行资源目标等预算选参与独立验证，`tools/run_paper1_supply_validation.py` 生成供油与储能启停对照。主阀资源量与储能出口功受所定义边界限制，不代表整机实测能耗。

通过根目录README中的隔离复现入口使用科学脚本；勿直接在公开快照中运行旧路径的研究脚本。参数为声明的理论输入，无实机标定数据。
