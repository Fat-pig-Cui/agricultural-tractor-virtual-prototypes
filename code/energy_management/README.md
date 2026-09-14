# 混合农业车辆严格因果能量管理比较代码

本目录对应论文草案：

> `papers/paper2_energy_management_draft.md`
>
> 《预测不确定性下的终端SOC约束鲁棒DP-MPC能量管理方法》

本代码用于OS-ECVT混合动力系统的**虚拟样机理论仿真**。代码不连接真实车辆、发动机、电机或电池，所有工况和参数均用于算法结构研究。

## 0. 当前投稿主协议（2026-09-11）

当前英语投稿稿件使用 `tools/run_paper2_controller_framework_benchmark.py`，而不是下文历史 DP/MPC 筛选结果。该脚本比较工程 OOL、地图感知 ECMS、公开相位策略、确定性 MPC、场景 MPC 与终端集安全过滤场景 MPC。

- 共同平台：300 kW 发动机、200 kWh 电池、150 kW 电机/母线、60 kW 稳定功率下限、40 kW/s 实际输出爬升；
- 共同能量核算：所有直接燃油比较要求 `abs(soc_error) <= 1e-4`，所有在线方法使用同一个终端能量调节器；
- 共同测试：600 s 连续随机农业循环，ECMS 因子仅在种子 2200--2205 上选择，种子 2220--2239 为冻结测试集；
- MPC 认证：除硬约束外，必须 `fallback_count == 0` 且预测爬升包络不可行次数为零；终端集 MPC 还必须零终端集越界，其内部安全过滤步数单独报告；
- 地图角色：两张地图均为已声明的理论虚拟组件输入。`LiteratureBSFCMap` 为参考形状，陡峭低负载效率岛为机制敏感性；二者均不能写成实车性能。

复现现行主结果：

```bash
PYTHONPATH=code:code/energy_management python3 tools/run_paper2_controller_framework_benchmark.py
python3 tools/plot_paper2_controller_framework.py
```

输出为 `results/paper2_controller_framework_benchmark.json` 与 `papers/figures/paper2_controller_framework.png`。中文审查结论见 `papers/submission/paper2_controller_framework_iteration_2026-09-11.md`。下文 `±0.01`、20% 和离线 DP 内容均为历史协议或失败审计，不能替代当前投稿主结果。

## 1. 研究目标

比较以下能量管理策略：

- OOL发动机负载跟随；
- 功率跟随；
- ECMS；
- 确定性MPC；
- 概率场景鲁棒MPC；
- 离线DP参考。

历史地图敏感性参数（`main_protocol_config()`；不是当前投稿结论）：

- 仿真时长：`600 s`；
- 初始SOC：`0.55`；
- 终止SOC容差：`±0.01`；
- 工况：再生低负荷农业循环（含负坡度/减速回收）；
- 电池容量：`200 kWh`；
- 发动机额定功率：`260 kW`；
- 电池功率限制：`±150 kW`；
- 电机峰值功率：`150 kW`；
- 再生回收上限：`45 kW`；
- 发动机低负荷效率：`0.08`（20%目标可达的物理前提，需BSFC标定确认）。

`±0.01`是本项目针对理论电池容量设置的研究协议阈值，不是通用行业标准。它对应200kWh电池约2kWh的净SOC能量偏差，用于避免把额外消耗电池能量误判为节油。

参考配置（`literature_reference_config()`）：文献形态 BSFC 地图 + 300 kW 发动机 + 200 kWh 电池 + 150 kW 功率边界 + 45 kW 回收。旧的名义节油率在共同输出斜率、最小稳定功率和合并电池总线检查前生成，已撤回，等待严格复验。

## 2. 算法结构

代码的目标结构为：

```text
合成地形与牵引负载
        ↓
滑动窗口概率预测
        ↓
DP参考与终端SOC信息
        ↓
确定性/场景MPC滚动候选评价
        ↓
OS-ECVT功率分流模型
        ↓
发动机燃油、电池SOC、电机功率和牵引缺口
```

当前已实现或部分实现的约束包括：

- 发动机功率上下界；
- 电池充放电功率限制；
- 电机峰值功率限制；
- 发动机功率爬坡限制（MPC）；
- SOC上下界；
- 终端SOC有效性判定；
- 牵引功率缺口统计。

## 3. 文件说明

| 文件 | 内容 |
|---|---|
| `experiments.py` | 统一实验入口、工况生成、控制器调度和结果有效性判定 |
| `os_ecvt_model.py` | 需求功率、发动机/电机功率分流、电池SOC和等效油耗模型 |
| `dp_mpc_ecms.py` | OOL、功率跟随、ECMS、DP、确定性MPC和场景MPC |
| `load_terrain_predictor.py` | 滑动窗口均值、方差和概率场景生成 |
| `../common/profiles.py` | 高负载、坡度、速度和土壤系数合成工况 |
| `../config/parameters.py` | 发动机、电机、电池、车辆和传动参数 |

## 4. 运行方法

从项目根目录执行完整对比：

```bash
PYTHONPATH="$PWD/code/energy_management:$PWD/code" python3 -c \
'from experiments import run_definition; \
[print(name, {k:v for k,v in run_definition(name).items() \
if k not in ("demands_w", "commands_w", "dp_reference_w")}) \
for name in ("ool", "power_following", "ecms", "deterministic_mpc", "robust_mpc", "dp")]'
```

单独运行鲁棒MPC：

```bash
PYTHONPATH="$PWD/code/energy_management:$PWD/code" python3 -c \
'from experiments import run_definition; print(run_definition("robust_mpc"))'
```

可用控制器名称：

```text
ool
power_following
ecms
deterministic_mpc
robust_mpc
dp
```

实验模块只定义函数，不会在导入时自动运行。

## 5. 输出指标

`run_definition()`主要返回：

| 字段 | 含义 |
|---|---|
| `fuel_l` | 等效燃油消耗，单位L |
| `final_soc` | 终止SOC |
| `soc_error` | 终止SOC减初始SOC |
| `valid` | 是否同时满足终端SOC和功率缺口约束 |
| `max_shortage_w` | 最大牵引功率缺口，单位W |
| `mean_battery_current_a` | 平均电池电流绝对值，单位A |
| `fallback_count` | 有限候选集为空时使用显式保守回退的控制步数 |
| `demands_w` | 牵引需求功率序列 |
| `commands_w` | 发动机功率指令序列 |
| `dp_reference_w` | DP发动机功率参考序列 |

## 6. 节油率判定

相对OOL的节油率定义为：


a = \frac{fuel_{OOL}-fuel_{candidate}}{fuel_{OOL}}\times100\%

但是只有候选控制器满足以下条件时，节油率才有效：

```text
abs(soc_error) <= terminal_soc_tolerance
max_shortage_w <= 1 W
发动机、电池和电机功率边界满足
```

如果`valid=False`，即使油耗数值较低，也只能称为“名义油耗下降”，不能称为有效节油率。

例如，控制器可能通过大量放电获得较低发动机燃油消耗。如果终止SOC明显低于初始SOC，该结果违反能量公平性，不能用于论文结论。

## 7. 终止SOC阈值说明

当前默认配置为：

```python
terminal_soc_tolerance = 0.01
```

该值是理论研究协议参数，不是从特定电池实车标定得到的标准。建议正式研究时增加敏感性分析：

```text
±0.005、±0.01、±0.02、±0.03
```

并同时报告对应的等效SOC能量偏差：

```python
battery_capacity_wh * abs(soc_error)
```

## 8. 参数与工况

工况由`common/profiles.py`中的`terrain_profile()`生成，包含：

- 高负载牵引；
- 速度变化；
- 坡度；
- 土壤系数变化。

动力总成参数由`config/parameters.py`集中管理。当前参数包括工程估计值和理论假设，不能替代：

- 发动机二维效率地图；
- 电机效率地图；
- 电池OCV-SOC曲线；
- 电池内阻和温度模型；
- OS-ECVT行星排齿数与转速约束；
- MG1/MG2独立功率边界。

## 9. 当前已知限制

- DP使用SOC和发动机功率离散网格近似；
- MPC使用有限候选发动机功率集合，不是严格QP/NLP求解器；
- 场景MPC对每个需求场景维持独立的预测SOC轨迹，并以最坏场景目标选取候选；不能将各场景SOC变化先平均后再施加终端代价；
- 候选集为空时`run_definition()`会显式记录`fallback_count`，最终有效性仍由终端SOC、缺口和代理约束共同判定；
- DP为离散近似，部分协议下可能因严格终端约束而无可行轨迹；
- DP参考尚未完整转换为MPC终端价值函数；
- 场景MPC与确定性MPC的结果差异仍可能较小；
- OS-ECVT功率分流模型尚未包含完整行星排运动学；
- `run_definition()`是单次入口；主体协议和文献形态参考协议的 20 种子统计已分别由`tools/run_statistics.py`和`tools/run_literature_reference_statistics.py`生成。严格因果跨循环验证由`tools/run_energy_crosscycle_validation.py`生成：随机周期中的确定性MPC只能使用滑动窗口预测，场景MPC只能使用同一历史生成的可复现情景，均不得读取被评估seed的未来负荷或其离线SOC参考。其结果仍只能说明虚拟原型条件下的表现。

这些限制应在论文中明确说明，不得将理论仿真描述为实车性能。

## 10. 对应资料

- 论文草案：`../../papers/paper2_energy_management_draft.md`
- 结构优化报告：`../../optimization_report.md`
- 阻塞记录：`../../blockers.md`
- 文献阅读记录：`../../literature_read.md`
- 代码检索记录：`../../code_references.md`

## 11. 严格约束复验（2026-09-09更新）

此前 `main_protocol_config()` 的 20.46%/19.63% 和 `literature_reference_config()` 的 9.42%/7.61% 结果已撤回：它们早于共同 60 kW 最小稳定功率、40 kW/s 应用输出斜率和合并再生/电池总线检查。当前这些配置只能用于复验和失败审计，不能写入论文结论。

运行主体协议：

```bash
python -c "import sys; sys.path[:0]=['code','code/energy_management','code']; \
from experiments import run_definition, main_protocol_config; \
[print(n, {k: round(v,4) if isinstance(v,float) else v for k,v in run_definition(n, main_protocol_config()).items() \
  if k in ('fuel_l','final_soc','soc_error','valid','max_shortage_w')}) \
  for n in ('ool','realistic_ool','power_following','ecms','deterministic_mpc','robust_mpc')]"
```

严格跨循环验证：`python3 tools/run_energy_crosscycle_validation.py`（写入`energy_crosscycle_validation.json`）。它使用连续扰动、共同应用输出约束和电池总线检查。当前结果为：假设效率岛下两种 MPC 均无有效配对；文献形态下场景 MPC 为 19/20 硬有效配对、平均 `-0.324%`，确定性 MPC 无有效配对。它不支持在线节油结论。

开发/保留集屏幕由 `python3 tools/run_paper2_phase_preview_scan.py` 和 `python3 tools/run_paper2_strict_horizon_screen.py` 生成；两者均未找到全保留集认证的正节油设置。`python3 tools/run_paper2_dynamic_upper_bound.py` 和 `python3 tools/run_paper2_dynamic_dp_diagnostic.py` 是完整已知名义循环的离线诊断，绝不能冒充在线 MPC。后者在假设效率岛、4 kW 发动机/0.005 SOC 网格下连续复演为 `19.880%`，用于量化“完整未来信息”与严格因果在线控制之间的差距。详细淘汰理由和当前状态见 `../../papers/submission/paper2_controller_iteration_report.md`。

作为非 MPC 对照，`python3 tools/run_paper2_phase_policy_screen.py` 仅使用公开的重复作业阶段和当前 SOC，先在 6 个开发 seed 上选择 8 个固定发动机功率目标，再冻结至 14 个保留 seed。选择后的策略在开发集为 `+0.0225%`（95% CI `-0.0056%` 至 `+0.0506%`），在保留集为 `-0.0011%`（95% CI `-0.0391%` 至 `+0.0370%`）；全部 20 条轨迹硬有效，但收益不具统计支持。它是对简单阶段排程的否定性检验，不能作为节油结论。

`python3 tools/run_paper2_phase_policy_tracking_screen.py` 增加仅由当前实测负荷驱动的有界跟随项（不使用未来样本）。增益 0.75 的冻结策略在早期保留集为 `+0.0647%`，但该集合曾参与增益试探，故仅作探索记录。`python3 tools/run_paper2_phase_policy_tracking_confirmation.py` 在从未观察过的 2046--2059 种子上不改动目标或增益进行确认，得到 14/14 硬有效、`+0.0653%`（95% CI `+0.0579%` 至 `+0.0728%`）。这是极小的、未校准虚拟模型效应，既不是 MPC 结论，也不支持 20% 或工程节油主张。

假设效率岛的严格敏感性由 `python3 tools/run_paper2_assumed_phase_policy_tiered_screen.py` 和 `python3 tools/run_paper2_assumed_phase_policy_multistart.py` 生成。后者在新的 2094--2127 三层种子集上固定 0.35 当前负荷跟随系数、比较三个预声明起点，并在独立确认集得到 14/14 硬有效、`+7.149%`（95% CI `+6.512%` 至 `+7.786%`）。它保持同一 OOL、SOC、功率、转速、牵引与斜率约束，但使用低负荷效率为 0.08 的未校准参数化地图，因此只能作为模型敏感性。`python3 tools/run_paper2_assumed_adaptive_ecms_pilot.py` 的最高开发集结果为 `+6.463%`，未进入留出或投稿结论。

`python3 tools/run_paper2_assumed_phase_gain_screen.py` 允许八个公开作业段分别使用有界的当前负荷跟随系数，仍不读取未来扰动。两个预声明的相位变化系数在新开发集均弱于统一 `0.35`，该未改变的策略随后在两个新的 14-seed 集上均硬有效（留出 `+8.360%`；确认 `+7.999%`）。它只是既有冻结策略的重复验证，不能据此选择更大的均值；主稿继续报告多起点独立确认的保守 `+7.149%`。

`python3 tools/run_paper2_assumed_phase_soc_buffer_screen.py` 增加了仅按公开作业阶段和当前 SOC 的预声明缓冲参考，并以 60 s 时间常数转为功率校正；最终 SOC 闭合、功率、转速、牵引和斜率屏幕不变。三个“犁耕前充电、犁耕时助力”的候选在 6 个新开发 seed 为 `+3.009%`、`+3.771%` 和 `+3.327%`，均弱于无 SOC 参考的 `+6.813%`。无参考策略在新的 14-seed 留出/确认集仍硬有效（`+7.924%` / `+6.954%`），因此该自由度不进入主稿结论。

`python3 tools/run_paper2_assumed_phase_policy_cem_screen.py` 固定随机种子，以五代、每代 16 个候选的全局交叉熵搜索同时探索八个相位目标和八个相位负荷增益。80 个候选均只在 6 个新开发 seed 上评价，且均硬有效；没有一个优于冻结的统一 `0.35` 策略。该未改变策略在全新留出/确认集仍硬有效（`+8.562%` / `+7.849%`），这只证明局部调参并未漏掉更优目标/增益组合，不能选择更大的重复均值或改写主稿的 `+7.149%`。

`python3 tools/run_paper2_assumed_stochastic_dp_diagnostic.py` 在一个新的随机 assumed-map seed 上运行完整未来的 4 kW/0.001 SOC 网格诊断。离散网格表面上为 `24.087%`，但连续回放 SOC 偏差为 `-0.03972`，因此无效。将路径置于同一电池/电机/转速/牵引/60 kW/40 kW/s 包络内并闭合 SOC 后，严格有效的离线诊断为 `6.936%`。它仅用于剔除网格量化伪收益，绝不是在线控制或正式上界。

协议演变历史见`../../energy_management_20pct_feasibility.md`与`../../energy_management_20pct_execution_A.md`。
