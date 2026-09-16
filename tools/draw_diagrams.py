"""Draw aligned technical architecture diagrams for the two English manuscripts."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIRS = (ROOT / "papers" / "figures", ROOT / "MDPI_template_ACS")

plt.rcParams["font.family"] = ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

BLUE = "#2F5597"
TEXT = "#1A1A1A"
LABEL = "#3D3D3D"


def box(ax, x, y, w, h, text, *, fc="#EAF2FA", ec=BLUE, fs=9.2, bold=False):
    """Add a fixed-size block whose multiline text is geometrically centered."""
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.015,rounding_size=0.035",
        fc=fc, ec=ec, lw=1.45,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", multialignment="center",
        fontsize=fs, linespacing=1.12,
        fontweight="bold" if bold else "normal", color=TEXT,
    )


def group(ax, x, y, w, h, title, *, fc="#F5F8FC", ec=BLUE):
    """Draw a labelled container without letting its title shift child blocks."""
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.018,rounding_size=0.04",
        fc=fc, ec=ec, lw=1.5,
    )
    ax.add_patch(patch)
    ax.text(
        x + 0.16, y + h - 0.18, title,
        ha="left", va="top", fontsize=10.3, fontweight="bold", color=TEXT,
    )


def arrow(ax, start, end, *, label=None, label_xy=None, style="->", dashed=False,
          connectionstyle="arc3,rad=0.0"):
    """Draw a consistent signal arrow and, optionally, a non-overlapping label."""
    patch = FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=14,
        color=BLUE, lw=1.45, linestyle="--" if dashed else "-",
        connectionstyle=connectionstyle,
    )
    ax.add_patch(patch)
    if label:
        x, y = label_xy if label_xy is not None else (
            (start[0] + end[0]) / 2,
            (start[1] + end[1]) / 2,
        )
        ax.text(
            x, y, label, ha="center", va="center", fontsize=7.8, color=LABEL,
            bbox={"boxstyle": "round,pad=0.10", "fc": "white", "ec": "none", "alpha": 0.96},
        )


def new_ax():
    fig, ax = plt.subplots(figsize=(10.0, 5.8))
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.04, top=0.96)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    for output_dir in OUTPUT_DIRS:
        output_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_dir / name, dpi=300, facecolor="white")
        print("saved", output_dir / name)
    plt.close(fig)


def diagram_paper1():
    """Dual-mode hitch control and the model-level pressure-transition proxy."""
    fig, ax = new_ax()

    box(
        ax, 0.35, 5.05, 2.35, 0.62, "Position reference\nand trajectory",
        fc="#FDEBD0", ec="#C55A11", fs=9.4,
    )
    box(
        ax, 7.30, 5.05, 2.35, 0.62, "Implement load / temperature\n(external disturbances)",
        fc="#FDEBD0", ec="#C55A11", fs=8.35,
    )

    group(ax, 0.35, 3.18, 4.25, 1.30, "Dual-mode controller")
    box(
        ax, 0.58, 3.76, 3.80, 0.30, "Leakage-flow / pressure-deficit supervisor",
        fc="#FFF2CC", ec="#BF9000", fs=7.85,
    )
    box(
        ax, 0.58, 3.31, 1.68, 0.34, "Tracking mode\n(SMC / DI-SMAC)",
        fc="#E2EFDA", ec="#538135", fs=7.7,
    )
    box(
        ax, 2.70, 3.31, 1.68, 0.34, "Hold mode\n(trim / lock / accumulator)",
        fc="#E2EFDA", ec="#538135", fs=7.0,
    )

    group(ax, 5.40, 3.18, 4.25, 1.30, "Model-level leakage proxy")
    box(
        ax, 5.63, 3.38, 1.76, 0.38, "Pressure-transition\nresidual", fc="#DEEBF7", ec="#2E75B6", fs=7.35,
    )
    box(
        ax, 7.86, 3.38, 1.56, 0.38, "Leakage-coefficient\nproxy", fc="#DEEBF7", ec="#2E75B6", fs=7.15,
    )

    box(
        ax, 2.70, 1.93, 4.60, 0.50, "Virtual states: position and ideal chamber pressures",
        fc="#F2F2F2", ec="#555555", fs=8.25,
    )
    box(
        ax, 2.70, 0.67, 6.05, 0.72, "Electrohydraulic hitch plant\n(proportional valve / cylinder / linkage)",
        fc="#E7E7E7", ec="#404040", fs=8.15,
    )

    arrow(ax, (1.53, 5.05), (1.53, 4.48), label="reference", label_xy=(1.53, 4.75))
    arrow(ax, (8.48, 5.05), (8.48, 1.39), label="disturbance", label_xy=(8.48, 4.74))
    arrow(ax, (2.22, 3.18), (3.72, 1.39), label="control command", label_xy=(2.47, 2.30))
    arrow(ax, (5.00, 1.39), (5.00, 1.93), label="state / pressure", label_xy=(5.00, 1.65))
    arrow(ax, (6.30, 2.43), (6.30, 3.18), label="residual", label_xy=(6.75, 2.78))
    arrow(
        ax, (5.40, 4.10), (4.60, 4.10), label="supervisory signal", label_xy=(5.00, 4.72),
        dashed=True,
    )

    save(fig, "paper1_architecture.png")


def diagram_paper2():
    """Strict-causal virtual-prototype controller comparison architecture."""
    fig, ax = new_ax()

    box(
        ax, 0.35, 5.05, 2.55, 0.62, "Parameterized virtual maps\n(engine / motor / battery)",
        fc="#FCE4D6", ec="#C55A11", fs=8.05,
    )
    box(
        ax, 3.72, 5.05, 2.55, 0.62, "Causal information set\n(current demand / SOC / task phase)",
        fc="#E2EFDA", ec="#538135", fs=8.0,
    )
    box(
        ax, 7.10, 5.05, 2.55, 0.62, "Online policy set\n(ECMS / phase / MPC variants)",
        fc="#EAF2FA", ec=BLUE, fs=8.25, bold=True,
    )

    box(
        ax, 0.35, 3.66, 2.55, 0.56, "Common electrical and\nengine-ramp constraints",
        fc="#DDEBF7", ec="#2E75B6", fs=8.0,
    )
    box(
        ax, 3.72, 3.66, 2.55, 0.56, "Finite candidate search\nand scenario roll-outs", fc="#E2EFDA", ec="#538135", fs=8.25,
    )
    box(
        ax, 7.10, 3.66, 2.55, 0.56, "Terminal-set safety filter\n(terminal-energy envelope)",
        fc="#FFF2CC", ec="#BF9000", fs=8.1,
    )

    box(
        ax, 0.35, 0.72, 2.55, 0.68, "Synthetic agricultural cycle\n(idle / transport / tillage / turn)",
        fc="#E7E7E7", ec="#404040", fs=7.55,
    )
    box(
        ax, 3.72, 0.72, 2.55, 0.68, "OS-ECVT powertrain model\n(engine / machines / battery / driveline)",
        fc="#E7E7E7", ec="#404040", fs=7.55,
    )
    box(
        ax, 7.10, 0.72, 2.55, 0.68, "State measurements\n(SOC / power / speed)",
        fc="#F2F2F2", ec="#555555", fs=8.0,
    )

    arrow(ax, (1.63, 5.05), (1.63, 4.22), label="map limits", label_xy=(1.63, 4.63))
    arrow(ax, (4.99, 5.05), (4.99, 4.22), label="online data", label_xy=(4.99, 4.63))
    arrow(ax, (2.90, 3.94), (7.10, 5.26), label="constraints", label_xy=(3.25, 4.42),
          connectionstyle="arc3,rad=0.12")
    arrow(ax, (6.27, 3.94), (7.10, 5.26), label="candidate scores", label_xy=(6.62, 4.52),
          connectionstyle="arc3,rad=-0.12")
    arrow(ax, (8.38, 5.05), (8.38, 4.22), label="safe projection", label_xy=(8.38, 4.63))
    arrow(ax, (7.42, 3.66), (5.18, 1.40), label="engine command", label_xy=(6.12, 2.47))
    arrow(ax, (2.90, 1.06), (3.72, 1.06), label="traction demand", label_xy=(3.31, 1.53))
    arrow(ax, (6.27, 1.06), (7.10, 1.06), label="measured states", label_xy=(6.68, 1.53))
    arrow(ax, (8.38, 1.40), (8.38, 3.66), label="feedback", label_xy=(8.38, 2.47))

    save(fig, "paper2_architecture.png")


if __name__ == "__main__":
    diagram_paper1()
    diagram_paper2()
