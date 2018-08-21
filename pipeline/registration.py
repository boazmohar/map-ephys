import sys
sys.path.append('U:\\spark-test\\python')
sys.path.append('U:\\spark-test\\python\\lib\\py4j-0.10.4-src.zip')
from pyspark import SparkContext
import datajoint as dj
import platform
import os

schema = dj.schema('boazmohar_registration')

from . import lab
from . import experiment
from . import imaging


@schema
class RegistrationInput(dj.Manual):
    definition = """
    registration_id : smallint unsigned
    ---
    """
    
    class RegistrationRuns(dj.Part):
        definition = """
        -> RegistrationInput
        -> imaging.Run
        registrationrun_id : smallint unsigned
        """

class HasSparkContext:
    """ Mixin to add local_filenames_as_wildcard property to Scan and Stack. """
    @property
    def sc(self):
        """manages spark context"""
        # check env for spark master else:
        sc = SparkContext(master='local[4]')
        print(f'got sc with {sc.defaultParallelism} cores')
        return sc
        
@schema
class Registration(dj.Computed, HasSparkContext):
    definition = """
    -> RegistrationInput
    ---
    clean_binary_path : varchar(1024)
    reg_binary_path : varchar(1024)
    shifts          : blob
    
    """
    def _make_tuples(self, key):
        base_path, anm_id, date, run = base_path(key)
        session = VisSession(basePath=base_path, animalID=anm_id, date=date, run=run)
        print(f'Full path: {fullpath}')
        self.sc.stop()
      
    
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
        anm_id = f'ANM{session["subject_id"]}'
        run = f'Run{session["run_id"]}'
        return '/' + base_path, anm_id, date, run