from pyspark import SparkContext
import datajoint as dj
import platform
import time
import os
from prep.VisSession import VisSession
from prep.IO import loadData, saveRegData
from prep.Utils import getTarget, registerByPlane
from prep.Vision import get_default_from_exp

schema = dj.schema('boazmohar_registration')

from . import lab
from . import experiment
from . import imaging


def base_path(key):
    """Returns the local filename for all parts of this scan (ends in *.tif)."""

    res = (RegistrationInput().RegistrationRuns() & key) * \
          imaging.Run() * experiment.Session()
    session = res.fetch(as_dict=True)[0]
    current = platform.system()
    path = (imaging.Path() & session).fetch1()
    if current == 'Windows':
        base_path = path['path_windows']
    elif current == 'Linux':
        base_path = path['path_linux']
    else:
        base_path = path['path_mac']
    date = session["session_date"].strftime("%y%m%d")
    anm_id = 'ANM{id}'.format(id=session['subject_id'])
    run = 'Run{run}'.format(run=session["run_id"])
    return base_path, anm_id, date, run


@schema
class RegistrationInput(dj.Manual):
    definition = """
    registration_id : smallint unsigned auto_increment
    ---
    """
    
    class RegistrationRuns(dj.Part):
        definition = """
        -> RegistrationInput
        -> imaging.Run
        registrationrun_id : smallint unsigned
        """


class HasSparkContext:
    """ Mixin to add spark context, local or from a env variable MASTER. """
    @property
    def sc(self):
        """manages spark context"""
        # check env for spark master else:
        if 'MASTER' in os.environ:
            sc = SparkContext(master=os.environ['MASTER'])
            time.sleep(5)
        else:
            sc = SparkContext(master='local')
        print('got sc with {c} cores'.format(c=sc.defaultParallelism))
        return sc


@schema
class Registration(dj.Computed, HasSparkContext):
    definition = """
    -> RegistrationInput
    ---
    clean_binary_path : varchar(1024)
    reg_binary_path : varchar(1024)
    shifts          : longblob
    
    """

    def _make_tuples(self, key):
        path, anm_id, date, run = base_path(key)
        session = VisSession(basePath=path, animalID=anm_id, date=date, run=run)
        sc = self.sc
        get_default_from_exp(session, sc)
        data, clean, clean_path = loadData(sc, session, cutoff=None, saveBinary=True, start=None, stop=None, xStart=0,
                                           xStop=session.xSize, overwrite=True, timepoints=200, repartition=True,
                                           cutoff_fallback=40, zoom=None, return_clean_path=True)

        def flyline(x):
            x[:2, :, :] = 0
            return x

        clean = clean.map(flyline)
        mean = clean.mean().toarray()
        session.writeTiff(mean, 'clean_mean')
        target_index = getTarget(clean, cutCC=90, midFactor=1, mode='index')
        target = clean[target_index, :, :, :].mean().toarray()
        shifts, regTarget = registerByPlane(sc, data=clean[target_index, :, :, :], target=target, upSample2=5,
                                            doShift=True)
        regTarget = regTarget.mean().toarray()
        session.writeTiff(regTarget, 'regTarget')
        shifts2, regData = registerByPlane(sc, data=clean, target=regTarget, upSample2=5, doShift=True)
        regData.cache()
        regData.count()
        regMean = regData.mean().toarray()
        session.writeTiff(regMean, 'regMean2')
        reg_data_path = saveRegData(session, regData, return_name=True, overwrite=True)
        key['clean_binary_path'] = clean_path  # compute mean
        key['reg_binary_path'] = reg_data_path  # compute standard deviation
        key['shifts'] = shifts2
        self.insert1(key)
        sc.stop()