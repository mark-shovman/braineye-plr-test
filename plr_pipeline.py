import os

import numpy as np
import pandas as pd
import logging
import matplotlib.pyplot as plt
import json

from plr_plot import plot_noise_reduction, plot_landmark, plot_constriction

from plr import (
    load_plr_data,
    calculate_pupil_size,
    calculate_signal_quality,
    calculate_eye_openness,
    detect_blinks,
    calculate_biomarkers,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


if __name__ == "__main__":

    with open("config.json", "r") as config_file:
        config = json.load(config_file)

    data_dir = config["data_dir"]

    with open("./landmark_definitions.json", "r") as json_file:
        lm_defs = json.load(json_file)

    summary = {}
    biomarkers = {}

    for i, test_id in enumerate(os.listdir(data_dir)):
        logging.info(f"processing {test_id}")
        os.makedirs(os.path.join("figures", test_id), exist_ok=True)
        try:
            lm, flash_duration = load_plr_data(data_dir, test_id)

            # for lm_id in range(1,28):
            #     plot_landmark(lm, lm_id, lm_defs[str(lm_id)]['short_name'])

            ok_count = lm["retcode"].value_counts()["OK"]
            dataloss = 1.0 - ok_count / len(lm)
            summary[test_id] = {"dataloss": dataloss}

            if dataloss > config["dataloss"]["error"]:
                logging.error(
                    f"{test_id} very high data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK); skipping"
                )
                continue
            if dataloss > config["dataloss"]["warning"]:
                logging.warning(
                    f"{test_id} high data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK)"
                )
            else:
                logging.info(
                    f"{test_id} data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK)"
                )

        except Exception as e:
            logging.error(
                f"failed loading recording {test_id} from {data_dir}", exc_info=True
            )
            continue

        try:
            for eye in ["left", "right"]:
                eo = calculate_eye_openness(lm, eye)
                blink = detect_blinks(lm, eye, eo, **config["blink"])

                lm.loc[
                    blink[f"{eye}_is_blink"],
                    [c for c in lm.columns if c.startswith(eye)],
                ] = np.nan

                lm[f"{eye}_is_blink"] = blink[f"{eye}_is_blink"]

        except Exception as e:
            logging.error(f"blink removal failed for {test_id}", exc_info=True)
            continue

        try:
            for eye in ["left", "right"]:
                pupil_size = calculate_pupil_size(
                    lm, eye, config["nominal_iris_size_mm"]
                )
                col = f"{eye}_pupil_size_mm"
                lm[col] = pupil_size[col]

                # _, ax = plt.subplots(
                #     7, 1, sharex=True, num=f"{eye} pupil size\n{test_id}"
                # )
                # pupil_size.plot(subplots=True, ax=ax)

                plt.figure(num="pupil size")
                plt.plot(
                    lm.index,
                    lm[col],
                    label=f"{test_id} {eye}",
                    linewidth=1,
                    alpha=0.5,
                    color=config["eye_color"][eye],
                )
                plt.xlabel("Time from flash onset (milliseconds)")
                plt.ylabel("Pupil size (mm)")
                plt.grid(True)

        except Exception as e:
            logging.error(f"failed calculating pupil size for {test_id}", exc_info=True)
            continue

        try:
            for eye in ["left", "right"]:
                lm[f"{eye}_smooth_pupil_size_mm"] = (
                    lm[f"{eye}_pupil_size_mm"]
                    .rolling(
                        config["noise_reduction"]["smoothing_window"],
                        center=True,
                        win_type=config["noise_reduction"]["smoothing_window_type"],
                    )
                    .mean()
                )

            summary[test_id].update(
                calculate_signal_quality(
                    lm,
                    t=(
                        config["noise_reduction"]["stable_interval_start"],
                        config["noise_reduction"]["stable_interval_end"],
                    ),
                )
            )
            logging.info(
                f"{test_id} signal quality: {summary[test_id]['raw_signal_quality']:.3f} mm raw, "
                f"{summary[test_id]['smooth_signal_quality']:.3f} mm smooth"
            )

            plot_noise_reduction(
                lm,
                test_id,
                summary[test_id],
                flash_duration,
                eye_color=config["eye_color"],
                path=os.path.join(".", "figures", test_id, f"noise_reduction.pdf"),
            )

        except Exception as e:
            logging.error(f"noise reduction failed for {test_id}", exc_info=True)
            continue

        try:
            for eye in ["left", "right"]:
                ps = lm.loc[0:flash_duration, f"{eye}_smooth_pupil_size_mm"]
                biomarkers[(test_id, eye)] = calculate_biomarkers(
                    lm.loc[0:flash_duration, f"{eye}_smooth_pupil_size_mm"],
                    **config["constriction"],
                )

                plot_constriction(
                    lm[f"{eye}_smooth_pupil_size_mm"],
                    biomarkers[(test_id, eye)],
                    f"{test_id} - {eye}",
                    flash_duration,
                    path=os.path.join(
                        ".", "figures", test_id, f"pupil_constriction_{eye}.pdf"
                    ),
                )
        except Exception as e:
            logging.error(f"biomarker calculations failed for {test_id}", exc_info=True)
            continue

    fig = plt.figure(num="pupil size")
    plt.savefig("figures/pupil_size_mm.png")
    plt.close(fig)

    summary = pd.DataFrame.from_dict(summary, orient="index")
    summary.index.name = "test_id"
    summary.to_csv("reports/pipeline_summary.csv")

    biomarkers = pd.DataFrame.from_dict(biomarkers, orient="index")
    biomarkers.index.set_names(["test_id", "eye"], inplace=True)
    biomarkers.to_csv("reports/biomarkers.csv")

    if plt.get_fignums():
        plt.show()
