# 论文二：当前ECMS与功率分流模型

`viability_ecms_v2.py` 提供功率分流虚拟对象、候选工作点、ECMS和软SOC防护，`os_ecvt_model.py` 提供所用效率地图。当前正文为 `manuscripts/paper2/` 的作者修正校样；名称中的viability不构成递归可行性证明。

公开检出不附实验结果。主比较、模块消融、相同防护固定ECMS、地图容量与执行检查由 `tools/` 中对应脚本从头生成。主协议终端SOC容差为1e-4。理想全信息诊断由 `tools/run_paper2_ideal_oracle_envelope.py` 单独生成，与当前在线结果分列。

依照根目录README在隔离工作区运行复现。模型与参数均有理论边界，不能解释为实车或组件地图标定。
