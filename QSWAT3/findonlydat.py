'''
Created on Apr 21, 2023

@author: Chris
'''
''' find TxtInOut folders that hve only a dat file in them - indicates corrupt .sqlite'''

# Parameters to be set befure run

TNCDir = 'K:/TNC'  # 'E:/Chris/TNC'
Continent = 'CentralAmerica' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia
ContDir = 'CentralAmerica' # can be same as Continent or Continent plus underscore plus anything for a part project
                                # DEM, landuse and soil will be sought in TNCDir/ContDir
maxSubCatchment = 100000 # maximum size of subcatchment in sq km, i.e. point at which inlet is inserted to form subcatchment.  Default 10000 equivalent to 100 grid cells.
soilName = 'FAO_DSMW' # 'FAO_DSMW', 'hwsd3'
weatherSource = 'CHIRPS' # 'CHIRPS', 'ERA5'
gridSize = 100  # DEM cells per side.  100 gives 10kmx10km grid when using 100m DEM
catchmentThreshold = 150  # minimum catchment area in sq km.  With gridSize 100 and 100m DEM, this default of 1000 gives a minimum catchment of 10 grid cells
maxHRUs = 5  # maximum number of HRUs per grid cell
demBase = '100albers' # name of non-burned-in DEM, when prefixed with contAbbrev
maxCPUSWATCount = 40 # maximum number of CPUs used to run SWAT
maxCPUCollectCount = 10 # maximum number of CPUs to collect outputs (may be lower than maxCPUSWATCount because of memory requirement)
slopeLimits = [2, 8]  # bands will be 0-2, 2-8, 8+
SWATEditorTNC = TNCDir + '/SwatEditorTNC/SwatEditorTNC.exe'
SWATApp = TNCDir + '/SWAT/Rev_688_CG_64rel.exe'

# abbreviations for continents.  Assumed in several places these are precisely 2 characters long
contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
soilAbbrev = 'FAO' if soilName == 'FAO_DSMW' else 'HWSD'

import glob
import os



class FindOnlyDat():

    def __init__(self):
        self.prefix = contAbbrev
        self.projName = contAbbrev + '_' + soilAbbrev + '_' + weatherSource + '_' + str(gridSize) + '_' + str(maxHRUs)
        self.projDir = TNCDir + '/' + ContDir + '/Projects/' + self.projName
        self.projDb = self.projDir + '/' + self.projName + '.sqlite'
        self.catchmentsDir = self.projDir + '/' + 'Catchments'
        self.dbTemplate =  TNCDir + '/QSWATProj2012_TNC.sqlite'
        
    def find(self):
        """Print numbers of catchments with TxtInOut folders that hve only one file in them."""
        
        for d in glob.iglob(self.catchmentsDir + '/*'):
            if os.path.isdir(d):
                f = os.path.basename(d)
                catchmentStr = f[2:]
                txtinout = d + '/Scenarios/Default/TxtInOut'
                if len(os.listdir(txtinout)) == 1:
                    print(catchmentStr)
                
if __name__ == '__main__': 
    f = FindOnlyDat()
    f.find()

    
                