from matplotlib import pyplot as plt


def plot_landmark(lm, lm_id, lm_name):
    fields = [f"{eye}_lm_{lm_id}_{x}" for eye in ["left", "right"] for x in ["x", "y"]]
    ax = lm[fields].plot(
        style="-", title=f"{lm_id}: {lm_name}", subplots=True, sharex=True
    )
    ax[0].set_title(f"{lm_id}: {lm_name}")


def plot_noise_reduction(lm, test_id, sq, flash_duration, path=None, eye_color=None):
    if eye_color is None:
        eye_color = {"left": "b", "right": "r"}

    fig, ax = plt.subplots(1, 1, num=f"Noise Reduction {test_id}")
    lm.left_pupil_size_mm.plot(
        color=eye_color["left"],
        linestyle="-",
        linewidth=0.3,
        marker=".",
        markersize=1,
        label="left eye raw",
        ax=ax,
    )
    lm.right_pupil_size_mm.plot(
        color=eye_color["right"],
        linestyle="-",
        linewidth=0.3,
        marker=".",
        markersize=1,
        label="right eye raw",
        ax=ax,
    )

    lm.left_smooth_pupil_size_mm.plot(
        color=eye_color["left"], linestyle="-", label="left eye smooth", ax=ax
    )
    lm.right_smooth_pupil_size_mm.plot(
        color=eye_color["right"], linestyle="-", label="right eye smooth", ax=ax
    )

    plt.axvspan(0, flash_duration, color="k", alpha=0.1, label="Flash")

    plt.legend()
    plt.grid()

    plt.xlabel("Time from flash onset (milliseconds)")
    plt.ylabel("Pupil size (mm)")
    plt.title(
        f'Signal quality: {sq["raw_signal_quality"]:.3f}mm raw, {sq["smooth_signal_quality"]:.3f}mm smooth\n({test_id})'
    )

    if path is not None:
        plt.savefig(path)
        plt.close(fig)


def plot_constriction(ps, bm, label, flash_duration, path=None):
    fig, ax = plt.subplots(1, 1, num=f"Pupil Constriction {label}")

    plt.plot(ps.index, ps, label="Pupil size (smooth)")
    plt.axvline(bm["ctn_latency_ms"], color="red", label="Constriction start")
    plt.axvline(bm["ctn_max_time_ms"], color="black", label="Constriction max")
    plt.axvspan(0, flash_duration, color="k", alpha=0.1, label="Flash")

    plt.legend()
    plt.grid()

    plt.xlabel("Time from flash onset (milliseconds)")
    plt.ylabel("Pupil size (mm)")
    plt.title(f"Pupil Constriction\n{label}")

    if path is not None:
        plt.savefig(path)
        plt.close(fig)
