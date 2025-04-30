import os
import pandas as pd
import numpy as np
import logging

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
        * raise IndexError if either onset or offset are missing
        * collate protocol and landmarks into a single dataframe - add column for flash on/off
        * reset index to time since onset in seconds
    """

    lm = pd.read_csv(os.path.join(data_dir, rec_id, rec_id + '_plr_landmarks.csv'),
                     parse_dates=['timestamp'],
                     date_format='%Y-%m-%d %H:%M:%S.%f')

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

    return lm


if __name__ == '__main__':
    data_dir = './plr_data'
    for rec_id in os.listdir(data_dir):
        try:
            lm = load_plr_data(data_dir, rec_id)

        except Exception as e:
            logging.error(f'Error loading {rec_id}: {e}')
            continue
