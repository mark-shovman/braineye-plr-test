import os
import pandas as pd
import numpy as np
import logging
import matplotlib.pyplot as plt
import json

from matplotlib.pyplot import title

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


def load_plr_data(data_dir, rec_id):
    """
    Load PLR data from a given recording ID
        * set rows with retcode != 'OK' to NaN values and log data validity
        * raise IndexError if either onset or offset are missing
        * collate protocol and landmarks into a single dataframe - add column for flash on/off
        * reset index to time since onset, in seconds
    """

    lm = pd.read_csv(os.path.join(data_dir, rec_id, rec_id + '_plr_landmarks.csv'),
                     parse_dates=['timestamp'],
                     date_format='%Y-%m-%d %H:%M:%S.%f')

    ok_count = lm['retcode'].value_counts()['OK']
    logging.info(f'{rec_id} data validity: {ok_count/len(lm):.1%} ({ok_count}/{len(lm)})')

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

if __name__ == '__main__':

    with open('./landmark_definitions.json', 'r') as json_file:
        lm_defs = json.load(json_file)

    data_dir = './plr_data'
    for rec_id in os.listdir(data_dir):
        try:
            lm = load_plr_data(data_dir, rec_id)
        except Exception as e:
            logging.error(f'Error loading {rec_id}: {e}')
            continue

        for lm_id in range(1,28):
            plot_landmark(lm, lm_id)

        plt.show()
        break
