import os
import logging

import numpy as np
import pandas as pd


def load_plr_data(data_dir: str, test_id):
    """
    Load PLR data from a given recording ID
        * set rows with retcode != 'OK' to NaN values
        * raise IndexError if either onset or offset are missing
        * collate protocol and landmarks into a single dataframe - add a column for flash on/off
        * reset index to time since onset, in seconds
    """

    lm = pd.read_csv(
        os.path.join(data_dir, test_id, test_id + "_plr_landmarks.csv"),
        parse_dates=["timestamp"],
        date_format="%Y-%m-%d %H:%M:%S.%f",
    )

    lm.loc[lm["retcode"] != "OK", lm.columns.drop(["timestamp", "retcode"])] = np.nan

    pt = pd.read_csv(
        os.path.join(data_dir, test_id, test_id + "_plr_protocol.csv"),
        parse_dates=["time"],
        date_format="%Y-%m-%d %H:%M:%S.%f",
    )

    try:
        onset = pt.time[pt.event == "FlashOn"].values[0]
        offset = pt.time[pt.event == "FlashOff"].values[0]
    except Exception as e:
        logging.error(f"Missing onset or offset in {test_id}")
        raise IndexError(f"Either onset of offset missing in {test_id}").with_traceback(
            e.__traceback__
        )

    lm["is_flash_on"] = False
    lm.loc[(lm.timestamp >= onset) & (lm.timestamp <= offset), "is_flash_on"] = True

    lm.index = (lm.timestamp - onset).dt.total_seconds()
    lm.index.name = "time_from_flash_s"

    return lm, (offset - onset) / np.timedelta64(1, "s")


def calculate_pupil_size(lm, eye, nominal_iris_size_mm):
    """
    Calculate pupil size (diameter) for a given eye
    """
    ret = pd.DataFrame(index=lm.index)

    lm_pairs = [
        (7, 10, "horz"),  # Horizontal diameter (inner to outer edge)
        (9, 23, "vert"),  # Vertical diameter (bottom to top-outer)
        (22, 24, "diag1"),  # Diagonal diameter (bottom-outer to top-inner)
        (25, 23, "diag2"),  # Opposite diagonal (bottom-inner to top-outer)
        (6, 11, "iris"),  # Horizontal diameter of the iris (inner to outer edge)
    ]

    col_names = []
    for lm1, lm2, lm_name in lm_pairs:
        x1 = lm[f"{eye}_lm_{lm1}_x"]
        y1 = lm[f"{eye}_lm_{lm1}_y"]

        x2 = lm[f"{eye}_lm_{lm2}_x"]
        y2 = lm[f"{eye}_lm_{lm2}_y"]

        if lm_name == "iris":
            col_name = f"{eye}_iris_size_px"
        else:
            col_name = f"{eye}_{lm_name}_pupil_size_px"
            col_names.append(col_name)

        ret[col_name] = np.sqrt(((x2 - x1) ** 2 + (y2 - y1) ** 2))

    ret[f"{eye}_pupil_size_px"] = ret[col_names].mean(axis=1)
    ret[f"{eye}_pupil_size_mm"] = (
        ret[f"{eye}_pupil_size_px"] / ret[f"{eye}_iris_size_px"] * nominal_iris_size_mm
    )

    # ret.plot(subplots=True, sharex=True)

    return ret


def calculate_signal_quality(lm, t):
    def rms_s2s(s):
        return np.sqrt((s.diff() ** 2).mean())

    sq_raw = (
        rms_s2s(lm.loc[t[0] : t[1], "left_pupil_size_mm"])
        + rms_s2s(lm.loc[t[0] : t[1], "right_pupil_size_mm"])
    ) / 2

    sq_smooth = (
        rms_s2s(lm.loc[t[0] : t[1], "left_smooth_pupil_size_mm"])
        + rms_s2s(lm.loc[t[0] : t[1], "right_smooth_pupil_size_mm"])
    ) / 2

    return {"raw_signal_quality": sq_raw, "smooth_signal_quality": sq_smooth}
