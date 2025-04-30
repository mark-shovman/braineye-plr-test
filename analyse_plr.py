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


def load_plr_data(data_dir:str, rec_id):
    """
    Load PLR data from a given recording ID
        * set rows with retcode != 'OK' to NaN values
        * raise IndexError if either onset or offset are missing
        * collate protocol and landmarks into a single dataframe - add a column for flash on/off
        * reset index to time since onset, in seconds
    """

    lm = pd.read_csv(os.path.join(data_dir, rec_id, rec_id + '_plr_landmarks.csv'),
                     parse_dates=['timestamp'],
                     date_format='%Y-%m-%d %H:%M:%S.%f')

    lm.loc[lm['retcode'] != 'OK', lm.columns.drop(['timestamp', 'retcode'])] = np.nan

    pt = pd.read_csv(os.path.join(data_dir, rec_id, rec_id + '_plr_protocol.csv'),
                     parse_dates=['time'],
                     date_format='%Y-%m-%d %H:%M:%S.%f')

    try:
        onset = pt.time[pt.event == 'FlashOn'].values[0]
        offset = pt.time[pt.event == 'FlashOff'].values[0]
    except Exception as e:
        logging.error(f'Missing onset or offset in {rec_id}')
        raise IndexError(f'Either onset of offset missing in {rec_id}').with_traceback(e.__traceback__)

    lm['is_flash_on'] = False
    lm.loc[(lm.timestamp >= onset) & (lm.timestamp <= offset), 'is_flash_on'] = True

    lm.index = (lm.timestamp - onset).dt.total_seconds()
    lm.index.name = 'time_from_flash_s'

    return lm


def plot_landmark(lm, lm_id):
    fields = [f'{eye}_lm_{lm_id}_{x}' for eye in ['left', 'right'] for x in ['x', 'y']]
    ax = lm[fields].plot(style='-', title=f'{lm_id}: {lm_defs[str(lm_id)]['short_name']}', subplots=True, sharex=True)
    ax[0].set_title(f'{lm_id}: {lm_defs[str(lm_id)]["short_name"]}')


def calculate_pupil_size(lm, eye='left', nominal_iris_size_mm=11.7):
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

    ret[f'{eye}_mean_pupil_size_px'] = ret[col_names].mean(axis=1)
    ret[f'{eye}_mean_pupil_size_mm'] = ret[f'{eye}_mean_pupil_size_px'] / ret[f'{eye}_iris_size_px'] * nominal_iris_size_mm

    # ret.plot(subplots=True, sharex=True)

    return ret


if __name__ == '__main__':

    with open('config.json', 'r') as config_file:
        config = json.load(config_file)

    data_dir = config['data_dir']

    with open('./landmark_definitions.json', 'r') as json_file:
        lm_defs = json.load(json_file)


    plt.figure(num='pupil size')

    for rec_id in os.listdir(data_dir):
        logging.info(f'processing {rec_id}')
        try:
            lm = load_plr_data(data_dir, rec_id)

            # skipping if dataloss is too high
            ok_count = lm['retcode'].value_counts()['OK']
            dataloss = 1.0 - ok_count / len(lm)
            if dataloss > config['max_dataloss']:
                logging.error(f'{rec_id} very high data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK); skipping')
                continue
            if dataloss > config['warn_dataloss']:
                logging.warning(f'{rec_id} high data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK)')
            else:
                logging.info(f'{rec_id} data loss: {dataloss:.1%} ({ok_count}/{len(lm)} OK)')

        except Exception as e:
            logging.error(f'failed loading recording {rec_id} from {data_dir}', exc_info=True)
            continue

        try:
            plt.figure(num='pupil size')
            for eye in ['left', 'right']:
                pupil_size = calculate_pupil_size(lm, eye)
                col = f'{eye}_mean_pupil_size_mm'
                lm[col] = pupil_size[col]
                plt.plot(lm.index, lm[col], label=f'{rec_id} {eye}', linewidth=1, alpha=0.5,
                         color=config['eye_color'][eye])

        except Exception as e:
            logging.error(f'failed calculating pupil size for {rec_id}', exc_info=True)
            continue

        # for lm_id in range(1,28):
        #     plot_landmark(lm, lm_id)
        #
    plt.show()
        # break
