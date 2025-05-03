import os
import logging

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

import matplotlib.pyplot as plt


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

    lm.index = (lm.timestamp - onset).dt.total_seconds() * 1000
    lm.index.name = "time_from_flash_ms"

    return lm, (offset - onset) / np.timedelta64(1, "ms")


def _calculate_landmark_distance(lm, eye, lm_pairs):
    ret = pd.DataFrame(index=lm.index)

    for lm1, lm2, name in lm_pairs:
        x1 = lm[f"{eye}_lm_{lm1}_x"]
        y1 = lm[f"{eye}_lm_{lm1}_y"]

        x2 = lm[f"{eye}_lm_{lm2}_x"]
        y2 = lm[f"{eye}_lm_{lm2}_y"]

        ret[f"{eye}_{name}_px"] = np.sqrt(((x2 - x1) ** 2 + (y2 - y1) ** 2))

    return ret


def calculate_pupil_size(lm, eye, nominal_iris_size_mm):
    """
    Calculate pupil size (diameter) for a given eye
    """
    lm_pairs = [
        (7, 10, "horz_pupil_size"),  # Horizontal diameter (inner to outer edge)
        (9, 23, "vert_pupil_size"),  # Vertical diameter (bottom to top-outer)
        (22, 24, "diag1_pupil_size"),  # Diagonal diameter (bottom-outer to top-inner)
        (25, 23, "diag2_pupil_size"),  # Opposite diagonal (bottom-inner to top-outer)
        (6, 11, "iris_size"),  # Horizontal diameter of the iris (inner to outer edge)
    ]

    ret = _calculate_landmark_distance(lm, eye, lm_pairs)

    col_names = [c for c in ret.columns if c.endswith("pupil_size_px")]

    ret[f"{eye}_pupil_size_px"] = ret[col_names].mean(axis=1)
    ret[f"{eye}_pupil_size_mm"] = (
        ret[f"{eye}_pupil_size_px"] / ret[f"{eye}_iris_size_px"] * nominal_iris_size_mm
    )

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


def calculate_eye_openness(lm, eye):
    lm_pairs = [
        (3, 19, "central_openness"),  # Central eye openness
        (4, 14, "inner_openness"),  # Inner eye openness
        (17, 15, "far_inner_openness"),  # Far inner eye openness
        (2, 12, "outer_openness"),  # Outer eye openness
        (26, 21, "far_outer_openness"),  # Far outer eye openness
    ]
    ret = _calculate_landmark_distance(lm, eye, lm_pairs)
    ret[f"{eye}_mean_eye_openness_nz"] = (ret / ret.max()).mean(axis=1)
    return ret


def detect_blinks(
    lm, eye, eo, sg_window, sg_poly_order, openness_th, speed_th, blink_interval_window
):
    """
    Blink is defined by either the eye being less open than `openness_th`,
    or the speed of the eyelid opening/closing being greater than `speed_th`
    """

    ret = pd.DataFrame(index=lm.index)
    ret[f"{eye}_speed"] = np.abs(
        savgol_filter(
            eo[f"{eye}_mean_eye_openness_nz"],
            window_length=sg_window,
            polyorder=sg_poly_order,
            deriv=1,
        )
    )

    ret[f"{eye}_is_blink"] = (
        (
            (ret[f"{eye}_speed"] > speed_th)
            | (eo[f"{eye}_mean_eye_openness_nz"] < openness_th)
        )
        .rolling(window=blink_interval_window, center=True, min_periods=1)
        .median()
        .astype(bool)
    )

    return ret


def calculate_biomarkers(ps, ctn_start_velocity_th_mms, sg_window, sg_poly_order):

    ctn_speed_mms = (
        savgol_filter(
            ps,
            window_length=sg_window,
            polyorder=sg_poly_order,
            deriv=1,
        )
        / ps.index.to_series().diff()
        * 1000
    )

    ctn_latency = (ctn_speed_mms < ctn_start_velocity_th_mms).idxmax()
    ctn_max = (ps == ps.min()).idxmax()
    total_ctn = ps[:ctn_latency].max() - ps.min()
    ctn_velocity = total_ctn / (ctn_max - ctn_latency)
    ctn_max_velocity = -ctn_speed_mms[ctn_latency].min()

    return {
        "total_ctn_mm": total_ctn,
        "ctn_latency_ms": ctn_latency,
        "ctn_velocity_mms": ctn_velocity,
        "ctn_max_velocity_mms": ctn_max_velocity,
        "ctn_max_time_ms": ctn_max,
    }
