"""Plot manuscript diagnostics for the agri-workcycle energy experiment."""
from __future__ import annotations
from pathlib import Path
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(ROOT / "code/energy_management"))
from experiments import run_definition, main_protocol_config

# Keep the manuscript diagnostic figure on the same protocol as Table 1
# (regenerative low-load cycle, low-load efficiency 0.08, 260 kW engine,
# 200 kWh/150 kW battery and 45 kW recovery limit).
cfg = main_protocol_config()
results = {name: run_definition(name, cfg)
           for name in ("realistic_ool", "deterministic_mpc", "robust_mpc")}
t = [i * 0.1 for i in range(len(results["realistic_ool"]["demands_w"]))]
fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
axes[0].plot(t, [x / 1000 for x in results["realistic_ool"]["demands_w"]],
             color="0.35", linewidth=0.7)
for name, label in (("realistic_ool", "Actual OOL"),
                    ("deterministic_mpc", "Deterministic MPC"),
                    ("robust_mpc", "Scenario MPC")):
    axes[1].plot(t, [x / 1000 for x in results[name]["commands_w"]],
                 label=label, linewidth=1.0)
    soc_ref = results[name]["dp_soc_reference"]
    t_ref = [i * 0.1 for i in range(len(soc_ref))]
    axes[2].plot(t_ref, soc_ref,
                 label=label, linewidth=1.0)
axes[0].set_ylabel("Demand (kW)")
axes[0].set_title("Main-protocol energy-management diagnostics")
axes[1].set_ylabel("Engine command (kW)")
axes[1].legend(loc="upper right", ncol=3, fontsize=8)
axes[2].set_ylabel("SOC reference")
axes[2].set_xlabel("Time (s)")
axes[2].set_ylim(0.48, 0.62)
fig.tight_layout()
out = ROOT / "papers/figures/paper2_energy_results.png"
fig.savefig(out, dpi=300)
print(out)
