# based on https://github.com/cajal/pipeline/blob/master/python/pipeline/experiment.py
import datajoint as dj

schema = dj.schema('boazmohar_imaging')

from . import lab
from . import experiment

@schema
class Objective(dj.Manual):
    definition = """
    objective : varchar(24) 
    ----
    objective_descriotion : varchar(255)
    """
    contents = (('4x','Nikon 4x 0.3NA','16x','Olympus 16x 0.8NA',
                 '20x', 'Olympus 20x 1.05NA'))
    
@schema
class Fluorophore(dj.Lookup):
    definition = """  # calcium-sensitive indicators
    fluorophore     : char(10)   # fluorophore short name
    -----
    dye_description = ''  : varchar(2048)
    """
    contents = [
        ['GCaMP6s', ''],
        ['GCaMP6f', ''],
        ['JF525Halo', 'Janelia Flour 525 with halo tag'],
        ['JF585Halo', 'Janelia Flour 585 with halo tag']
    ]
    
@schema
class FOV(dj.Lookup):
    definition = """  # field-of-view sizes for all lenses and magnifications
    -> lab.Rig
    -> Objective
    mag         : decimal(5,2)  # ScanImage zoom factor
    fov_id      : smallint      # fov measurement date and time
    ---
    fov_date = CURRENT_TIMESTAMP    : datetime  # When the FOV was recorded
    pitch = null: decimal(5,2) # angle of the animal in AP axis
    roll = null : decimal(5,2) # angle of the animal in ML axis
    """

@schema
class Anesthesia(dj.Lookup):
    definition = """   #  anesthesia states
    anesthesia                     : char(20) # anesthesia short name
    ---
    anesthesia_description=''       : varchar(255) # longer description
    """
    contents = [
        ['awake', ''],
        ['fentanyl', ''],
        ['iso', 'isoflurane']
    ]
    
@schema
class Compartment(dj.Lookup):
    definition = """  # cell compartments that can be imaged
    compartment         : char(16)
    ---
    """
    contents = [['axon'], ['soma'], ['dendrtie']]
    

@schema
class PMTFilterSet(dj.Lookup):
    definition = """  # microscope filter sets: dichroic and PMT Filters
    pmt_filter_set          : varchar(16)       # short name of microscope filter set
    ----
    primary_dichroic        :  varchar(255)     #  passes the laser  (excitation/emission separation)
    secondary_dichroic      :  varchar(255)     #  splits emission spectrum
    filter_set_description  :  varchar(4096)    #  A detailed description of the filter set
    """
    contents = [
        ['2P3 red-green A', '680 nm long-pass?', '562 nm long-pass', 'purchased with Thorlabs microscope'],
        ['2P3 blue-green A', '680 nm long-pass?', '506 nm long-pass', 'purchased with Thorlabs microscope']]

    class Channel(dj.Part):
        definition = """  # PMT description including dichroic and filter
        -> PMTFilterSet
        pmt_channel : tinyint   #  pmt_channel
        ---
        color      : enum('green', 'red', 'blue')
        pmt_serial_number   :  varchar(40)   #
        spectrum_center     :  smallint  unsigned  #  (nm) overall pass spectrum of all upstream filters
        spectrum_bandwidth  :  smallint  unsigned  #  (nm) overall pass spectrum of all upstream filters
        pmt_filter_details  :  varchar(255)  #  more details, spectrum, pre-amp gain, pre-amp ADC filter
        """
        contents = [
            ['2P3 red-green A', 1, 'green', 'AC7438 Thor', 525, 50, ''],
            ['2P3 red-green A', 2, 'red', 'AC7753 Thor', 625, 90, ''],
            ['2P3 blue-green A', 1, 'blue', 'AC7438 Thor', 475, 50, ''],
            ['2P3 blue-green A', 2, 'green', 'AC7753 Thor', 540, 50, '']
        ]
