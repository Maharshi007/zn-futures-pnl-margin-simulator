"""3-panel chart: price, cumulative P&L, margin balance."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e8e7e3"
SERIES = "#2a78d6"
CALL_STYLE = {   # marker shape carries identity; colour is a second cue
    "price_move": {"marker": "o", "color": "#d03b3b", "label": "Call: price move"},
    "margin_hike": {"marker": "^", "color": "#eb6834", "label": "Call: CME margin hike"},
}


def _style(ax):
    ax.grid(axis="y", color=GRID, lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)


def plot_ledger(ledger, title, hike_dates, out_path) -> None:
    """Price (roll days dotted, Fed hikes shaded), cum P&L, balance vs maintenance.

    Calls are drawn at the balance BEFORE the top-up, so you see exactly
    where the account crossed the maintenance line.
    """
    has_margin = "balance" in ledger.columns     # P&L-only runs have 2 panels
    n = 3 if has_margin else 2
    fig, ax = plt.subplots(n, 1, figsize=(11, 3 * n), sharex=True)

    ax[0].plot(ledger.index, ledger["close"], color=SERIES, lw=1.5)
    for d in hike_dates:
        ax[0].axvline(d, color=MUTED, alpha=0.35, lw=4)
    for d in ledger.index[ledger["is_roll_day"]]:
        ax[0].axvline(d, color=MUTED, ls=":", lw=1.2)
    ax[0].plot([], [], color=MUTED, ls=":", label="Contract roll (P&L set to 0)")
    ax[0].plot([], [], color=MUTED, alpha=0.35, lw=4, label="Fed hike (DFEDTARU)")
    ax[0].set_ylabel("ZN price (points)")
    ax[0].legend(frameon=False, fontsize=8, loc="upper right")

    ax[1].plot(ledger.index, ledger["cum_pnl"], color=SERIES, lw=1.5)
    ax[1].axhline(0, color=MUTED, lw=0.8)
    ax[1].set_ylabel("Cumulative P&L ($)")

    if not has_margin:
        for a in ax:
            _style(a)
        fig.suptitle(title + " | P&L only (margins pending verification)", color=INK)
        fig.tight_layout(); fig.savefig(out_path, dpi=120); plt.close(fig)
        return

    ax[2].plot(ledger.index, ledger["balance"], color=SERIES, lw=1.5,
               label="Margin balance")
    ax[2].step(ledger.index, ledger["maint_total"], where="post", color=MUTED,
               ls="--", lw=1.2, label="Maintenance requirement")
    for reason, st in CALL_STYLE.items():
        c = ledger[ledger["call_reason"] == reason]
        if len(c):
            ax[2].scatter(c.index, c["balance_before_call"], s=36, zorder=3,
                          marker=st["marker"], color=st["color"],
                          edgecolor="white", linewidth=1.5, label=st["label"])
    ax[2].set_ylabel("Balance ($)")
    ax[2].legend(frameon=False, fontsize=8, loc="upper left")

    for a in ax:
        _style(a)
    fig.suptitle(title, color=INK)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
