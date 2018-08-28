import datajoint as dj
import os
import glob
import tqdm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from prep.VisSession import VisSession
from prep.IO import loadRegData
from prep.Vision import get_default_from_exp, getBehaviorVision, agg_tc, check_sig, get_sig_direction
from prep.Timecourses import getBaseline, getNoise
from pySparkUtils.SVD import getSVD
from . import registration
from .registration import HasSparkContext, base_path
from . import imaging

schema = dj.schema('boazmohar_timecourses')

print(3)

@schema
class CellTuning(dj.Computed, HasSparkContext):
    definition = """
    -> registration.Registration
    cell_id         : smallint unsigned
    ---
    df              : longblob      # (dff) time aligned dff
    trial_df        : longblob      # (dff (direction, time, repeat)) trial aligned dff
    pop_corr        : float         # pearson corr of the cell to the mean of the other cells
    direction=null  : float         # (deg) direction 
    interval=null   : float         # (deg) confidence interval
    sig             : tinyint       # (bool) if p < 0.05 for one-way ANOVA
    mask            : longblob      # (bool (x, y)) binary mask
    mean            : longblob      # (float (x, y))mean image od the cell
    noise           : float         # (dff) median noise of the cell
    """

    def make(self, key):
        path, anm_id, date, run = base_path(key)
        session = VisSession(basePath=path, animalID=anm_id, date=date, run=run)
        sc = self.sc
        get_default_from_exp(session, sc)
        session.start = 0
        session.stop = len(glob.glob(os.path.join(session.path, '') + '*.tif'))
        _, reg_data = loadRegData(sc, session, None, check=False)
        reg_data.cache()
        reg_data.count()
        reg_mean = reg_data.mean().toarray()
        if os.path.isfile(session.path + 'tc.p'):
            session = session.load('tc')
            timeDict = session.timeDict
            TC = timeDict['TC']
            df = timeDict['TCdiv']
            mask_all = timeDict['masks']
        else:
            spatial_all, temporal_all, mask_all, f_all = get_masks(reg_data, reg_mean, plot=False)
            TC = np.array(f_all)
            TCMotion = np.zeros_like(TC)
            TCPixels = np.zeros_like(TC)
            TCMotion = TCMotion + np.mean(TC, axis=1)[:, np.newaxis]
            px = np.sum(np.array(mask_all), axis=(1, 2))
            TCPixels = TCPixels + px[:, np.newaxis]
            timeDict = dict()
            timeDict['masks'] = mask_all
            timeDict['TC'] = TC
            timeDict['TCMotion'] = TCMotion
            timeDict['TCPixels'] = TCPixels
            getBaseline(sc, timeDict, step=16)
            getNoise(sc, timeDict)
            session.behaveDict = getBehaviorVision(session, sc)
            session.timeDict = timeDict
            df = timeDict['TCdiv']
        tc_agg = agg_tc(session, 'TCdiv', valid_spines=np.arange(TC.shape[0]))
        sig, _ = check_sig(session, tc_agg, sig_th=0.05)
        dir_dict = get_sig_direction(session, tc_name='TCdiv', valid_masks=None, angle_cutoff=45, log=False)
        pop_corr = np.zeros(df.shape[0])
        for cell_index in range(df.shape[0]):
            df_mean = np.nanmean(np.delete(df, cell_index, axis=0), axis=0)
            pop_corr[cell_index] = np.corrcoef(df[cell_index, :], df_mean)[0, 1]
        reg_id = np.zeros(len(mask_all), dtype=int) + key['registration_id']
        cell_id = np.arange(len(mask_all))
        trial_df = tc_agg
        direction = dir_dict['direction']
        intervals = dir_dict['intervals']
        sig_all = np.zeros(len(mask_all), dtype=int)
        sig_all[sig] = 1
        masks = mask_all
        means = reg_mean.transpose(2, 0, 1)
        noise = np.nanmedian(timeDict['TCNoise'], axis=1)
        all_keys = zip(reg_id, cell_id, df, trial_df, pop_corr, direction, intervals, sig_all, masks, means, noise)
        session.save('tc', False)
        self.insert(all_keys, )
        sc.stop()


@schema
class CellStability(dj.Computed, HasSparkContext):
    definition = """
    (subject_id, session_1) -> imaging.Run(subject_id, session)
    (session_2) -> imaging.Run(session)
    (cell_id_1) -> CellTuning(cell_id)
    (cell_id_2) -> CellTuning(cell_id)
    ---
    delta_ori   : float
    delta_p     : float
    """

    @property
    def key_source(self):
        tune_reg = CellTuning() * registration.RegistrationInput().RegistrationRuns()
        list_ = tune_reg.fetch('subject_id', 'fov_id')
        df = pd.DataFrame({'subject_id': list_[0], 'fov_id': list_[1]})
        keys = df.drop_duplicates().to_dict(orient='records')
        return imaging.FOV() & keys

    def make(self, key):
        print(key)




def get_masks(reg_data, reg_mean=None, n_comp=4, px_thershold=80, plot=True):
    if reg_mean is None:
        reg_mean = reg_data.mean().toarray()
    spatial_all = []
    temporal_all = []
    mask_all = []
    f_all = []
    for i in tqdm.tqdm(range(reg_data.shape[3])):
        plane = reg_data[:, :, :, i]
        plane.cache()
        temporal, spatial, _ = getSVD(plane, n_comp, getComponents=True, getS=False, normalization=None)
        spatial = np.abs(np.squeeze(spatial))
        temporal_all.append(temporal)
        spatial_all.append(spatial)
        mask = spatial[0, :, :] > np.percentile(spatial[0, :, :], px_thershold)
        mask_all.append(mask)
        if plot:
            plt.figure()
            plt.subplot(1, 2, 1)
            plt.imshow(reg_mean[:, :, i])
            plt.subplot(1, 2, 2)
            plt.imshow(mask)
            plt.show()
        f_all.append(plane.map(lambda x: x[mask].mean()).toarray())
        plane.uncache()
    return spatial_all, temporal_all, mask_all, f_all
