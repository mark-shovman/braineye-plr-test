import os
import pandas as pd
import numpy as np
import logging
import matplotlib.pyplot as plt
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


def load_plr_data(data_dir:str, test_id):
    """
    Load PLR data from a given recording ID
        * set rows with retcode != 'OK' to NaN values
        * raise IndexError if either onset or offset are missing
        * collate protocol and landmarks into a single dataframe - add a column for flash on/off
        * reset index to time since onset, in seconds
    """

    lm = pd.read_csv(os.path.join(data_dir, test_id, test_id + '_plr_landmarks.csv'),
                     parse_dates=['timestamp'],
                     date_format='%Y-%m-%d %H:%M:%S.%f')

    lm.loc[lm['retcode'] != 'OK', lm.columns.drop(['timestamp', 'retcode'])] = np.nan

    pt = pd.read_csv(os.path.join(data_dir, test_id, test_id + '_plr_protocol.csv'),
                     parse_dates=['time'],
                     date_format='%Y-%m-%d %H:%M:%S.%f')

    try:
        onset = pt.time[pt.event == 'FlashOn'].values[0]
        offset = pt.time[pt.event == 'FlashOff'].values[0]
    except Exception as e:
        logging.error(f'Missing onset or offset in {test_id}')
        raise IndexError(f'Either onset of offset missing in {test_id}').with_traceback(e.__traceback__)

    lm['is_flash_on'] = False
    lm.loc[(lm.timestamp >= onset) & (lm.timestamp <= offset), 'is_flash_on'] = True

    lm.index = (lm.timestamp - onset).dt.total_seconds()
    lm.index.name = 'time_from_flash_s'

    return lm, (offset - onset)/ np.timedelta64(1, 's')


def plot_landmark(lm, lm_id):
    fields = [f'{eye}_lm_{lm_id}_{x}' for eye in ['left', 'right'] for x in ['x', 'y']]
    ax = lm[fields].plot(style='-', title=f'{lm_id}: {lm_defs[str(lm_id)]['short_name']}', subplots=True, sharex=True)
    ax[0].set_title(f'{lm_id}: {lm_defs[str(lm_id)]["short_name"]}')


def calculate_pupil_size(lm, eye, nominal_iris_size_mm):
    """
    Calculate pupil size (diameter) for a given eye
    """
    ret = pd.DataFrame(index=lm.index)

    lm_pairs = [
        (7, 10, 'horz'), # Horizontal diameter (inner to outer edge)
        (9, 23, 'vert'), # Vertical diameter (bottom to top-outer)
        (22, 24, 'diag1'), # Diagonal diameter (bottom-outer to top-inner)
        (25, 23, 'diag2'), # Opposite diagonal (bottom-inner to top-outer)
        (6, 11, 'iris') # Horizontal diameter of the iris (inner to outer edge)
    ]

    col_names = []
    for lm1, lm2, lm_name in lm_pairs:
        x1 = lm[f'{eye}_lm_{lm1}_x']
        y1 = lm[f'{eye}_lm_{lm1}_y']

        x2 = lm[f'{eye}_lm_{lm2}_x']
        y2 = lm[f'{eye}_lm_{lm2}_y']

        if lm_name == 'iris':
            col_name = f'{eye}_iris_size_px'
        else:
            col_name = f'{eye}_{lm_name}_pupil_size_px'
            col_names.append(col_name)

        ret[col_name] = np.sqrt(((x2 - x1) ** 2 + (y2 - y1) ** 2))

    ret[f'{eye}_pupil_size_px'] = ret[col_names].mean(axis=1)
    ret[f'{eye}_pupil_size_mm'] = ret[f'{eye}_pupil_size_px'] / ret[f'{eye}_iris_size_px'] * nominal_iris_size_mm

    # ret.plot(subplots=True, sharex=True)

    return ret

def calculate_signal_quality(lm):
    def rms_s2s(s):
        return np.sqrt((s.diff()**2).mean())

    t = (config['stable_interval_start'], config['stable_interval_end'])
    sq_raw = (rms_s2s(lm.loc[t[0]:t[1], 'left_pupil_size_mm'])
              + rms_s2s(lm.loc[t[0]:t[1], 'right_pupil_size_mm'])) / 2

    sq_smooth = (rms_s2s(lm.loc[t[0]:t[1], 'left_smooth_pupil_size_mm'])
                 + rms_s2s(lm.loc[t[0]:t[1], 'right_smooth_pupil_size_mm'])) / 2

    return {'raw_signal_quality': sq_raw, 'smooth_signal_quality': sq_smooth}


def plot_noise_reduction(lm, test_id, sq, flash_duration):
    _, ax = plt.subplots(1, 1, num=f'Noise Reduction {test_id}')
    lm.left_pupil_size_mm.plot(color='b', linestyle='', marker='.', markersize=1, label='left eye raw', ax=ax)
    lm.right_pupil_size_mm.plot(color='r', linestyle='', marker='.', markersize=1, label='right eye raw', ax=ax)
    lm.left_smooth_pupil_size_mm.plot(color='b', linestyle='-', label='left eye smooth', ax=ax)
    lm.right_smooth_pupil_size_mm.plot(color='r', linestyle='-', label='right eye smooth', ax=ax)
    # plt.axvline(0, color='k', linestyle='--', label='Flash onset')
    plt.axvspan(0, flash_duration, color='k', alpha=0.1, label='Flash')
    plt.legend()
    plt.xlabel('Time from flash onset (seconds)')
    plt.ylabel('Pupil size (mm)')
    plt.title(f'Signal quality: {sq["raw_signal_quality"]:.3f}mm raw, {sq["smooth_signal_quality"]:.3f}mm smooth\n({test_id})')


if __name__ == '__main__':

    with open('config.json', 'r') as config_file:
        config = json.load(config_file)

    data_dir = config['data_dir']

    with open('./landmark_definitions.json', 'r') as json_file:
        lm_defs = json.load(json_file)

    summary = {}

    for test_id in os.listdir(data_dir):
        logging.info(f'processing {test_id}')
        os.makedirs(os.path.join('figures', test_id), exist_ok=True)
        try:
            lm, flash_duration = load_plr_data(data_dir, test_id)

            # for lm_id in range(1,28):
            #     plot_landmark(lm, lm_id)

            # skipping if dataloss is too high
            ok_count = lm['retcode'].value_counts()['OK']
            dataloss = 1.0 - ok_count / len(lm)
            summary[test_id] = {'dataloss': dataloss}

            if dataloss > config['max_dataloss']:
                logging.error(f'{test_id} very high data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK); skipping')
                continue
            if dataloss > config['warn_dataloss']:
                logging.warning(f'{test_id} high data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK)')
            else:
                logging.info(f'{test_id} data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK)')

        except Exception as e:
            logging.error(f'failed loading recording {test_id} from {data_dir}', exc_info=True)
            continue

        try:
            for eye in ['left', 'right']:
                pupil_size = calculate_pupil_size(lm, eye, config['nominal_iris_size_mm'])
                col = f'{eye}_pupil_size_mm'
                lm[col] = pupil_size[col]

                plt.figure(num='pupil size')
                plt.plot(lm.index, lm[col], label=f'{test_id} {eye}', linewidth=1, alpha=0.5,
                         color=config['eye_color'][eye])

                # pupil_baseline = lm.loc[-1:0, col].median()
                # constriction = lm[col] - pupil_baseline

        except Exception as e:
            logging.error(f'failed calculating pupil size for {test_id}', exc_info=True)
            continue

        try:
            for eye in ['left', 'right']:
                lm[f'{eye}_smooth_pupil_size_mm'] = lm[f'{eye}_pupil_size_mm'].rolling(config['smoothing_window']).mean()

            summary[test_id].update(calculate_signal_quality(lm))
            logging.info(f'{test_id} signal quality: {summary[test_id]['raw_signal_quality']:.3f} mm raw, '
                         f'{summary[test_id]['smooth_signal_quality']:.3f} mm smooth')

            plot_noise_reduction(lm, test_id, summary[test_id], flash_duration)

        except Exception as e:
            logging.error(f'noise reduction failed for {test_id}', exc_info=True)
            continue

        plt.figure(num='pupil size')
        plt.xlabel('Time from flash onset (seconds)')
        plt.ylabel('Pupil size (mm)')

    summary = pd.DataFrame.from_dict(summary, orient='index')
    plt.show()
