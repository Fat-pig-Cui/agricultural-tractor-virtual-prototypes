# 泄漏可观测性驱动的双模式电液后提升鲁棒控制代码

本目录对应论文草案：

> `papers/paper1_lift_control_draft.md`
>
> 《泄漏可观测性驱动的双模式电液后提升鲁棒控制方法》

本代码用于**虚拟样机理论仿真**，不依赖真实拖拉机、液压站或传感器。代码结果只能用于算法结构验证，不能表述为实车实测结果。

## 1. 研究目标

验证电液后提升系统在以下条件下的控制性能：

- 初始位置：`0.15 m`；
- 目标位置：`0.35 m`；
- 负载：前10秒约`9000 N`，随后约`7000 N`；
- 油温：从`25 °C`线性变化到约`40 °C`；
- 仿真时长：默认`1800 s`；
- 位置稳态误差目标：`±10 mm`；
- 保压下沉目标：`1800 s`内不超过`10 mm`。

初始位置与目标位置相差`200 mm`，因此应将初始过渡误差、稳态定位误差和保压下沉量分开评价，不能用单一全时段最大误差代替全部指标。

## 2. 算法结构

当前实验采用以下结构：

```text
平滑位置轨迹
    ↓
位置控制器（PID / DI-SMAC / SMC）
    ↓
压力平衡前馈 + 位置反馈修正
    ↓
饱和比例阀指令
    ↓
降阶压差液压缸代理模型
    ↓
位置、速度、压力和泄漏观测
```

到位后进入保压逻辑：

```text
TRACK → HOLD_FINE → LOCK / ACCUMULATOR
```

其中：

- `TRACK`：执行平滑位置轨迹和压力平衡前馈；
- `HOLD_FINE`：满足位置误差和速度门限后，进行低幅度压力微调；
- `LOCK`：使用低泄漏保持模型进行长时间保压仿真；
- `ACCUMULATOR`：蓄能器补压闭环（放油阀由压差缺口+位置误差驱动，充电回路维持油量）。

保压期同时启用负载前馈：机具负载作为可测扰动直接进入保压压力目标，使负载阶跃时压差目标立即更新。蓄能器模式由泄漏流阈值或压力缺口阈值触发；补压阀仅在`ACCUMULATOR`模式下按压差缺口和位置误差开启，避免把被动锁止误写为蓄能器补偿。

当前代码中的`hold_mode`是理论锁止/低泄漏模型，不等价于真实先导式液压锁、平衡阀或蓄能器回路。

## 3. 文件说明

| 文件 | 内容 |
|---|---|
| `experiments.py` | 统一实验入口、轨迹生成、控制器选择、保压判定和指标计算 |
| `controllers.py` | 抗积分饱和PID、模型级压力状态转移泄漏代理、边界层滑模和DI-SMAC接口 |
| `hydraulic_model.py` | 降阶压差、理想压力输出重建、命令饱和、压力限制、虚拟泄漏、摩擦和机械运动模型 |
| `leakage_compensation.py` | 泄漏保持监督器和保持模式接口 |
| `../config/parameters.py` | 液压缸、阀、负载、传感器和泄漏参数 |

## 4. 运行方法

从项目根目录执行：

```bash
PYTHONPATH="code/lift_control:code" python3 -c \
'from experiments import run_definition; \
[print(name, run_definition(name)) for name in ("pid", "dismac", "smc", "hybrid")]'
```

也可以只运行单个控制器：

```bash
PYTHONPATH="code/lift_control:code" python3 -c \
'from experiments import run_definition; print(run_definition("hybrid"))'
```

Windows PowerShell 下等价写法（路径分隔符为分号）：

```powershell
$env:PYTHONPATH="code;code/lift_control"; python -c "import sys; sys.path[:0]=['code','code/lift_control']; from experiments import run_definition; print(run_definition('hybrid'))"
```

论文结果复现脚本（均在项目根目录执行，输出写入`results/`）：

```bash
python3 tools/run_statistics.py --lift-only       # 表1：20种子统计（仅更新lift部分）
python3 tools/run_lift_hold_validation.py         # 保压口径 + 锁止阀微泄漏
python3 tools/run_leakage_sensitivity.py          # 缸内泄漏敏感性
python3 tools/run_lift_ablation.py                # 消融（含结构对照）
python3 tools/run_lift_dual_gate_20seeds.py       # 速度门控三口径
python3 tools/run_lift_theoretical_stress.py      # 假设范围与时变泄漏虚拟压力测试
python3 tools/run_lift_submission_robustness.py   # 温度-负载包络与原始门限筛查
python3 tools/export_paper1_traceability.py --check # 参数清单与代码一致性
```

可用控制器名称：

```text
pid

dismac

smc

hybrid
```

实验函数本身不会在模块导入时自动运行，需要显式调用`run_definition()`。

## 5. 主要输出指标

`run_definition()`返回字典，主要字段如下：

| 字段 | 含义 |
|---|---|
| `rmse_m` | 全时段位置RMSE，单位m |
| `dynamic_max_error_m` | 轨迹阶段最大位置误差，单位m |
| `settling_error_m` | 仿真结束时位置误差，单位m |
| `hold_started` | 是否进入保压 |
| `hold_start_time_s` | 保压开始时间，单位s |
| `hold_state` | 最终状态，如`TRACK`、`HOLD_FINE`或`LOCK` |
| `hold_drop_m` | 从保压起点到仿真结束的最大下沉量，单位m |
| `max_velocity_mps` | 全程最大速度，单位m/s |
| `final_position_m` | 最终位置，单位m |
| `final_velocity_mps` | 最终速度，单位m/s |
| `command_energy` | 阀指令平方积分 |

毫米换算：

```python
result["settling_error_m"] * 1000
result["hold_drop_m"] * 1000
```

## 6. 结果判定

只有同时满足以下条件，才能声称后提升目标在当前虚拟样机中通过：

1. 进入保压状态；
2. 稳态定位误差不超过`10 mm`；
3. `hold_drop_m <= 0.010 m`；
4. 明确说明采用了哪些锁止泄漏和参数假设。

初始过渡阶段的约`200 mm`位置变化是实验设定造成的，不应被伪装成稳态精度。正式论文中应同时报告动态最大误差、稳态误差、进入保压时间和长时间下沉量。

## 7. 参数与可复现性

液压参数集中在`code/config/parameters.py`的`LiftParameters`中。`papers/submission/paper1_parameter_manifest.csv`逐项记录其值、单位、来源类别、代码标识和压力测试覆盖，并由`tools/export_paper1_traceability.py --check`核对。当前版本的参数是研究者定义的虚拟部件输入、降阶模型系数和数值设置；不宣称为特定样机的文献、数据表或标定参数。位置量测含随机噪声；腔压在当前虚拟原型中按理想状态可得，这不是压力传感器性能假设。

`run_definition()`支持`seed`参数：

```bash
PYTHONPATH="code/lift_control:code" python -c \
'from experiments import run_definition; print(run_definition("dismac", seed=2027))'
```

不同随机种子会改变位置传感器噪声序列。

## 8. 当前局限

- 压力模型是简化差压模型，不是完整两腔连续性方程；
- 压力、位置和泄漏观测器仍是理论简化实现；
- `LOCK`是虚拟低泄漏保持，不是硬件液压锁实物模型；
- 蓄能器预充压力、气体容积、放油阀流量系数和充电速率为工程估计，未做实物标定；
- 负载前馈依赖"负载可测/可估计"假设，负载估计误差与蓄能器压降需标定与余量设计；
- `run_definition()`仍是单次试验入口；统一 20 种子统计已通过`tools/run_statistics.py --lift-only`、`tools/run_lift_hold_validation.py`、`tools/run_lift_ablation.py`和`tools/run_lift_dual_gate_20seeds.py`提供，结果写入`results/`；
- 阀流量特性、泄漏系数、摩擦参数和负载参数需要真实样机标定；
- 论文中的实验数据必须以代码实际输出为准，不能使用预期值替代；
- 关闭负载前馈时14kN负载阶跃下沉约98mm，关闭蓄能器补压闭环时约21mm，均超过指标；完整方案（前馈+闭环）约1.8mm，这些消融结论不能外推到未标定的实物系统。

## 9. 对应资料

- 论文草案：`../../papers/paper1_lift_control_draft.md`
- 结构优化报告：`../../optimization_report.md`
- 阻塞记录：`../../blockers.md`
- 文献阅读记录：`../../literature_read.md`
