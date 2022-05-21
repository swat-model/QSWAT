# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Run TNC project
                              -------------------
        begin                : 2022-04-03
        copyright            : (C) 2022 by Chris George
        email                : cgeorge@mcmaster.ca
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Parameters to be set befure run

TNCDir = r'K:\TNC'  # r'E:\Chris\TNC'
Continent = 'CentralAmerica' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia
soilName = 'FAO_DSMW' # 'FAO_DSMW', 'hwsd3'
weatherSource = 'ERA5' # 'CHIRPS', 'ERA5'
gridSize = 100  # DEM cells per side.  100 gives 10kmx10km grid when using 100m DEM
maxHRUs = 5  # maximum number of HRUs per gid cell
demBase = '100albers' # name of non-burned-in DEM, when prefixed with contAbbrev
slopeLimits = [2, 8]  # bands will be 0-2, 2-8, 8+
SWATEditorCmd = TNCDir + '/SwatEditorCmd/SwatEditorCmd.exe'
SWATApp = TNCDir + '/SWAT/Rev_684_CG_rel.exe'  


contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
soilAbbrev = 'FAO' if soilName == 'FAO_DSMW' else 'HWSD'
              
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer # @UnresolvedImport
#from qgis.analysis import QgsNativeAlgorithms
#from PyQt5.QtCore import * # @UnusedWildImport
import atexit
import sys
import os
import glob
import subprocess
from osgeo import gdal, ogr  # type: ignore
import traceback
import sqlite3
import time

from multiprocessing import Pool
#import processing
#from processing.core.Processing import Processing
#Processing.initialize()
#if 'native' not in [p.id() for p in QgsApplication.processingRegistry().providers()]:
#    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
#for alg in QgsApplication.processingRegistry().algorithms():
#    print("{}:{} --> {}".format(alg.provider().name(), alg.name(), alg.displayName()))

from QSWAT import qswat  # @UnresolvedImport
from QSWAT.delineation import Delineation  # @UnresolvedImport
from QSWAT.hrus import HRUs  # @UnresolvedImport
from catchments import Partition  # @UnresolvedImport
#from QSWAT.parameters import Parameters  # @UnresolvedImport


osGeo4wRoot = os.getenv('OSGEO4W_ROOT')
QgsApplication.setPrefixPath(osGeo4wRoot + r'\apps\qgis-ltr', True)


# create a new application object
# without this importing processing causes the following error:
# QWidget: Must construct a QApplication before a QPaintDevice
# and initQgis crashes
app = QgsApplication([], True)


QgsApplication.initQgis()


atexit.register(QgsApplication.exitQgis)

class DummyInterface(object):
    """Dummy iface."""
    def __getattr__(self, *args, **kwargs):  # @UnusedVariable
        """Dummy function."""
        def dummy(*args, **kwargs):  # @UnusedVariable
            return self
        return dummy
    def __iter__(self):
        """Dummy function."""
        return self
    def next(self):
        """Dummy function."""
        raise StopIteration
    def layers(self):
        """Simulate iface.legendInterface().layers()."""
        return QgsProject.instance().mapLayers().values()
iface = DummyInterface()

#QCoreApplication.setOrganizationName('QGIS')
#QCoreApplication.setApplicationName('QGIS2')

class runTNC():
    
    """Run TNC project.  Assumes Source folder holds burned dem, flow directions, slope, accumulation, basins raster, 
    and crop holds land cover and soil holds soil raster.  Existing project file is overwritten."""
    
    def __init__(self):
        """Initialize"""
        ## project directory
        self.projName = contAbbrev + '_' + soilAbbrev + '_' + weatherSource + '_' + str(gridSize) + '_' + str(maxHRUs)
        self.projDir = TNCDir + '/' + Continent + '/Projects/' + self.projName
        self.projDb = self.projDir + '/' + self.projName + '.sqlite'
        logFile = self.projDir + '/runTNClog.txt'
        if os.path.isfile(logFile):
            os.remove(logFile)
        projFile = self.projDir + '.qgs'
        #print('replacing {0} with {1}'.format('continent', self.projName))
        with open(TNCDir + '/continent.qgs') as inFile, open(projFile, 'w') as outFile:
            for line in inFile.readlines():
                outFile.write(line.replace('continent', self.projName))
        ## QSWAT plugin
        self.plugin = qswat.QSwat(iface)
        ## QGIS project
        self.proj = QgsProject.instance()
        self.proj.read(projFile)
        self.plugin.setupProject(self.proj, True, logFile=logFile, fromGRASS=True, TNCDir=TNCDir)
        ## main dialogue
        self.dlg = self.plugin._odlg
        ## delineation object
        self.delin = None
        ## hrus object
        self.hrus = None
        ## connection to output database
        self.outConn = None
        # Prevent annoying "error 4 .shp not recognised" messages.
        # These should become exceptions but instead just disappear.
        # Safer in any case to raise exceptions if something goes wrong.
        gdal.UseExceptions()
        ogr.UseExceptions()
        
    def runProject(self):
        """Run QSWAT project."""
        gv = self.plugin._gv
        gv.gridSize = gridSize
        fileBase = contAbbrev + demBase
        self.hrus = HRUs(gv, self.dlg.reportsBox)
        basinFile = self.projDir + '/../../DEM/' + fileBase + '_burnedw.tif'
        if self.hrus.HRUsAreCreated(basinFile=basinFile):
            return
        self.delin = Delineation(gv, self.plugin._demIsProcessed)
        self.delin._dlg.tabWidget.setCurrentIndex(0)
        demFile = self.projDir + '/../../DEM/' + fileBase + '_burned.tif'
        print('DEM: ' + demFile)
        self.delin._dlg.selectDem.setText(demFile)
        self.delin._dlg.checkBurn.setChecked(False)
        self.delin._dlg.selectBurn.setText('')
        self.delin._dlg.useOutlets.setChecked(False)
        self.delin._dlg.selectOutlets.setText('')
        self.delin._dlg.GridBox.setChecked(True)
        self.delin._dlg.GridSize.setValue(gridSize)
        gv.useGridModel = True
        numProc = 0
        self.delin._dlg.numProcesses.setValue(numProc)
        self.delin.runTauDEM(None, True)
        self.delin.finishDelineation()
        self.delin._dlg.close()
        gv.writeMasterProgress(1, -1)
        self.hrus.init()
        hrudlg = self.hrus._dlg
        gv.landuseTable = 'landuse_lookup_TNC'
        gv.soilTable = 'FAO_soils_TNC' if soilName == 'FAO_DSMW' else 'HWSD_soils_TNC'
        self.hrus.landuseFile = self.projDir + '/../../Landuse/' + contAbbrev + 'cover.tif'
        self.hrus.landuseLayer = QgsRasterLayer(self.hrus.landuseFile, 'landuse')
        self.hrus.soilFile = self.projDir + '/../../Soil/' + contAbbrev + soilName + '.tif'
        if not os.path.isfile(self.hrus.soilFile):
            # try .img, but probably reports 65535 as unknown.  .tif should have this set
            self.hrus.soilFile = self.projDir + '/../../Soil/' + contAbbrev + soilName + '.img'
        self.hrus.soilLayer = QgsRasterLayer(self.hrus.soilFile, 'soil')
        self.hrus.weatherSource = weatherSource
        hrudlg.usersoilButton.setChecked(True)
        gv.db.slopeLimits = slopeLimits
        if not self.hrus.readFiles():
            hrudlg.close()
            return False  # gives True if project is empty
        hrudlg.close()
        return True
        
    def readCio(self, cioFile: str) -> int:
        """Read cio file to get period of run and print frequency."""
        with open(cioFile, 'r') as cio:
            # skip 7 lines
            for _ in range(7): next(cio)
            nbyrLine = cio.readline()
            cioNumYears = int(nbyrLine[:20])
            iyrLine = cio.readline()
            cioStartYear = int(iyrLine[:20])
            idafLine = cio.readline()
            self.julianStartDay = int(idafLine[:20])
            idalLine = cio.readline()
            self.julianFinishDay = int(idalLine[:20])
            # skip 47 lines
            for _ in range(47): next(cio)
            iprintLine = cio.readline()
            iprint = int(iprintLine[:20])
            # assume monthly for now 
            #self.isDaily = iprint == 1
            #self.isAnnual = iprint == 2
            nyskipLine = cio.readline()
            nyskip = int(nyskipLine[:20])
            startYear = cioStartYear + nyskip
            #self.numYears = cioNumYears - nyskip
            return startYear
# SQLITE versions 
    createHRU = """CREATE TABLE hru (
    LULC TEXT,
    HRU  INTEGER,
    HRUGIS  TEXT,
    SUB  INTEGER,
    YEAR  INTEGER,  
    MON   INTEGER,
     AREAkm2  REAL,
      PRECIPmm  REAL,
      SNOWFALLmm  REAL,
      SNOWMELTmm  REAL,
      IRRmm  REAL,
      PETmm  REAL,
      ETmm   REAL,
     SW_INITmm  REAL,
      SW_ENDmm  REAL,
      PERCmm   REAL,
     GW_RCHGmm REAL,
       DA_RCHGmm REAL,
       REVAPmm   REAL,
     SA_IRRmm  REAL,
      DA_IRRmm  REAL,
      SA_STmm  REAL,
      DA_STmm  REAL,
      SURQ_GENmm REAL,
       SURQ_CNTmm   REAL,
     TLOSS_mm  REAL,
      LATQ_mm  REAL,
      GW_Qmm  REAL,
      WYLD_Qmm REAL,
       DAILYCN   REAL,
     TMP_AVdgC   REAL,
     TMP_MXdgC   REAL,
     TMP_MNdgC   REAL,
     SOL_TMPdgC  REAL,
      SOLARmj_m2 REAL,
       SYLDt_ha  REAL,
      USLEt_ha  REAL,
      N_APPkg_ha REAL,
       P_APPkg_ha   REAL,
     N_AUTOkg_ha REAL,
       P_AUTOkg_ha  REAL,
      NGRZkg_ha  REAL,
      PGRZkg_ha REAL,
       NCFRTkg_ha REAL,
       PCFRTkg_ha REAL,
       NRAINkg_ha REAL,
       NFIXkg_ha  REAL,
      F_MNkg_ha  REAL,
      A_MNkg_ha  REAL,
      A_SNkg_ha  REAL,
      F_MPkg_aha  REAL,
      AO_LPkg_ha  REAL,
      L_APkg_ha  REAL,
      A_SPkg_ha   REAL,
     DNITkg_ha  REAL,
      NUP_kg_ha  REAL,
      PUPkg_ha  REAL,
      ORGNkg_ha  REAL,
      ORGPkg_ha  REAL,
      SEDPkg_h   REAL,
     NSURQkg_ha  REAL,
      NLATQkg_ha REAL,
       NO3Lkg_ha REAL,
       NO3GWkg_ha  REAL,
      SOLPkg_ha REAL,
       P_GWkg_ha  REAL,
      W_STRS  REAL,
      TMP_STRS  REAL,
      N_STRS  REAL,
      P_STRS REAL,
       BIOMt_ha REAL,
       LAI  REAL,
      YLDt_ha REAL,
       BACTPct  REAL,
      BACTLPct  REAL,
      WATB_CLI  REAL,
      WATB_SOL  REAL,
      SNOmm  REAL,
      CMUPkg_ha REAL,
       CMTOTkg_ha REAL,
       QTILEmm  REAL,
      TNO3kg_ha  REAL,
      LNO3kg_ha  REAL,
      GW_Q_Dmm REAL,
      LATQCNTmm REAL,
      TVAPkg_ha REAL
      );"""
      
    createSUB = """CREATE TABLE sub (
    SUB INTEGER,
       YEAR INTEGER,
       MON  INTEGER,
      AREAkm2 REAL,
       PRECIPmm  REAL,
      SNOWMELTmm REAL,
       PETmm REAL,
       ETmm REAL,
       SWmm  REAL,
      PERCmm  REAL,
      SURQmm  REAL,
      GW_Qmm  REAL,
      WYLDmm  REAL,
      SYLDt_ha REAL,
       ORGNkg_ha REAL,
       ORGPhg_ha REAL,
       NSURQkg_ha  REAL,
      SOLPkg_ha REAL,
       SEDPkg_ha REAL,
       LAT_Qmm REAL,
       LATNO3kg_ha REAL,
       GWNO3kg_ha REAL,
       CHOLAmic_L REAL,
       CBODUmg_L REAL,
       DOXQmg_L  REAL,
      TNO3kg_ha  REAL,
      QTILEmm REAL,
      TVAPkg_ha REAL
    );"""

    createRCH = """CREATE TABLE rch (
        SUB INTEGER,
         YEAR INTEGER,
         MON  INTEGER,
        AREAkm2 REAL,
         FLOW_INcms REAL,
         FLOW_OUTcms  REAL,
        EVAPcms REAL,
         TLOSScms REAL,
         SED_INtons REAL,
         SED_OUTtons REAL,
         SEDCONCmg_kg REAL,
         ORGN_INkg  REAL,
        ORGN_OUTkg  REAL,
        ORGP_INkg  REAL,
        ORGP_OUTkg REAL,
         NO3_INkg  REAL,
        NO3_OUTkg REAL,
         NH4_INkg REAL,
         NH4_OUTkg REAL,
         NO2_INkg  REAL,
        NO2_OUTkg  REAL,
        MINP_INkg REAL,
         MINP_OUTkg REAL,
         CHLA_INkg  REAL,
        CHLA_OUTkg  REAL,
        CBOD_INkg  REAL,
        CBOD_OUTkg REAL,
         DISOX_INkg  REAL,
        DISOX_OUTkg  REAL,
        SOLPST_INmg  REAL,
        SOLPST_OUTmg REAL,
         SORPST_INmg REAL,
         SORPST_OUTmg REAL,
         REACTPTmg  REAL,
        VOLPSTmg REAL,
         SETTLPST_mg  REAL,
        RESUSP_PSTmg  REAL,
        DIFUSEPSTmg REAL,
         REACHBEDPSTmg REAL,
         BURYPSTmg  REAL,
        BED_PSTmg REAL,
         BACTP_OUTct REAL,
         BACTLP_OUTct REAL,
         CMETAL1kg  REAL,
        CMETAL2kg REAL,
         CMETAL3kg REAL,
         TOT_Nkg  REAL,
        TOT_Pkg  REAL,
        NO3CONCmg_l REAL,
         WTMPdegc REAL
    );"""   
    
    createWQL = """CREATE TABLE wql (
    YEAR INTEGER,
    RCH INTEGER,
    DAY INTEGER,
    WTEMP REAL,
    ALGAE_IN REAL,
    ALGAE_O REAL,
    ORGN_IN REAL,
    ORGN_OUT REAL,
    NH4_IN REAL,
    NH4_OUT REAL,
    NO2_IN REAL,
    NO2_OUT REAL,
    NO3_IN REAL,
    NO3_OUT REAL,
    ORGP_IN REAL,
    ORGP_OUT REAL,
    SOLP_IN REAL,
    SOLP_OUT REAL,
    CBOD_IN REAL,
    CBOD_OUT REAL,
    SAT_OX REAL,
    DISOX_IN REAL,
    DISOX_O REAL,
    H20VOLUME REAL,
    TRVL_TIME REAL
    );"""
    
    createSED = """CREATE TABLE sed (
    RCH INTEGER,
    YEAR INTEGER,
    MON INTEGER,
    AREAkm2 REAL,
    SED_IN REAL,
    SED_OUT REAL,
    SAND_IN REAL,
    SAND_OUT REAL,
    SILT_IN REAL,
    SILT_OUT REAL,
    CLAY_IN REAL,
    CLAY_OUT REAL,
    SMAG_IN REAL,
    SMAG_OUT REAL,
    LAG_IN REAL,
    LAG_OUT REAL,
    GRA_IN REAL,
    GRA_OUT REAL,
    CH_BNK REAL,
    CH_BED REAL,
    CH_DEP REAL,
    FP_DEP REAL,
    TSS REAL
    );"""

    def makeOutputTables(self, outConn):
        outConn.execute('PRAGMA journal_mode = OFF')
        #sdatabase should be newly created, so just create tables
        outConn.execute(self.createHRU)
        outConn.execute(self.createSUB)
        outConn.execute(self.createRCH)
        outConn.execute(self.createSED)
        outConn.execute(self.createWQL)
        # try:
        #     outConn.execute("DELETE FROM hru")
        # except:
        #     outConn.execute(self.createHRU)
        # try:
        #     outConn.execute("DELETE FROM sub")
        # except:
        #     outConn.execute(self.createSUB)
        # try:
        #     outConn.execute("DELETE FROM rch")
        # except:
        #     outConn.execute(self.createRCH)
        # try:
        #     outConn.execute("DELETE FROM sed")
        # except:
        #     outConn.execute(self.createSED)
        # try:
        #     outConn.execute("DELETE FROM wql")
        # except:
        #     outConn.execute(self.createWQL)
        

    def collectOutput(self, direc, outConn):
        """Collect ouputs from catchment output into output database."""
        catchment = os.path.split(direc)[1]
        print('Collecting output from catchment ' + catchment)
        catchmentDb = direc + '/{0}.sqlite'.format(catchment)
        if not os.path.isfile(catchmentDb):
            print('Catchment database {0} not found'.format(catchmentDb))
            return
        txtInOut = direc + '/Scenarios/Default/TxtInOut/'
        catchmentOutputDb = direc + '/Scenarios/Default/TablesOut/SWATOutput.sqlite'
        if os.path.isfile(catchmentOutputDb):
            os.remove(catchmentOutputDb)
        with sqlite3.connect(catchmentOutputDb) as catchmentOutConn:
            self.makeOutputTables(catchmentOutConn)
            with sqlite3.connect(catchmentDb) as inConn:
                # map catchment subbasin to project subbasin
                subMap = dict()
                sql = 'SELECT Subbasin, CatchmentBasin FROM catchmentBasins'
                for row in inConn.execute(sql):
                    subMap[int(row[1])] = int(row[0])
                # map catchment HRU to project HRU
                hruMap = dict()
                sql = 'SELECT HRU, CatchmentHRU FROM catchmentHRUs'
                for row in inConn.execute(sql):
                    hruMap[int(row[1])] = int(row[0])
                sqlSub = 'INSERT INTO sub VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                sqlRch = 'INSERT INTO rch VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                sqlHru = 'INSERT INTO hru VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                sqlWql = 'INSERT INTO wql VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                sqlSed = 'INSERT INTO sed VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                startYear = self.readCio(txtInOut + 'file.cio')
                # collect output.sub
                with open(txtInOut + 'output.sub', 'r') as inFile:
                    for _ in range(9): next(inFile)
                    year = startYear
                    lastMon = 0
                    for line in inFile.readlines():
                        monStr = line[20:25]
                        if '.' in monStr:
                            continue  # omit summary lines
                        mon = int(monStr)
                        if mon == 1 and lastMon >= 12:
                            year += 1
                        lastMon = mon
                        if mon <= 12:  # omit summary lines
                            sub = subMap[int(line[6:11])]
                            data = [sub, year, mon] + line[25:].split()
                            try:
                                outConn.execute(sqlSub, data)
                                catchmentOutConn.execute(sqlSub, data)
                            except:
                                print('Problem with sub data: {0}'.format(data))
                # collect output.rch
                with open(txtInOut + 'output.rch', 'r') as inFile:
                    for _ in range(9): next(inFile)
                    year = startYear
                    lastMon = 0
                    for line in inFile.readlines():
                        monStr = line[20:26]
                        if '.' in monStr:
                            continue  # omit summary lines
                        mon = int(monStr)
                        if mon == 1 and lastMon >= 12:
                            year += 1
                        lastMon = mon
                        if mon <= 12:  # omit summary lines
                            sub = subMap[int(line[5:11])]
                            data = [sub, year, mon] + line[26:].split()
                            try:
                                outConn.execute(sqlRch, data)
                                catchmentOutConn.execute(sqlRch, data)
                            except:
                                print('Problem with rch data: {0}'.format(data))
                # collect output.hru
                with open(txtInOut + 'output.hru', 'r') as inFile:
                    for _ in range(9): next(inFile)
                    year = startYear
                    lastMon = 0
                    lastSub = 0
                    relHRU = 0
                    for line in inFile.readlines():
                        monStr = line[29:34]
                        if '.' in monStr:
                            continue  # omit summary lines
                        mon = int(monStr)
                        mon = int(line[29:34])
                        if mon == 1 and lastMon >= 12:
                            year += 1
                        lastMon = mon
                        if mon <= 12:  # omit summary lines
                            lulc = line[:4]
                            hru = hruMap[int(line[4:9])]
                            sub = subMap[int(line[19:24])]
                            if sub == lastSub:
                                relHRU += 1 
                            else:
                                relHRU = 1
                                lastSub = sub
                            gis = '{0:07d}{1:02d}'.format(sub, relHRU)
                            data = [lulc, hru, gis, sub, year, mon] + line[34:].split()
                            try:
                                outConn.execute(sqlHru, data)
                                catchmentOutConn.execute(sqlHru, data)
                            except:
                                print('Problem with hru data: {0}: {1}'.format(traceback.format_exc(), data))
                # collect output.wql
                with open(txtInOut + 'output.wql', 'r') as inFile:
                    next(inFile)
                    year = startYear
                    lastMon = 0
                    for line in inFile.readlines():
                        mon = int(line[11:16])
                        if mon == 1 and lastMon >= 365:
                            year += 1
                        lastMon = mon
                        if mon <= 12:  # omit summary lines
                            sub = subMap[int(line[6:11])]
                            data = [year, sub, mon] + line[16:].split()
                            try:
                                outConn.execute(sqlWql, data)
                                catchmentOutConn.execute(sqlWql, data)
                            except:
                                print('Problem with wql data: {0}'.format(data))
                # collect output.sed
                with open(txtInOut + 'output.sed', 'r') as inFile:
                    next(inFile)
                    year = startYear
                    lastMon = 0
                    for line in inFile.readlines():
                        monStr = line[21:27]
                        if '.' in monStr:
                            continue  # omit summary lines
                        mon = int(monStr)
                        if mon == 1 and lastMon >= 12:
                            year += 1
                        lastMon = mon
                        if mon <= 12:  # omit summary lines
                            sub = subMap[int(line[7:12])]
                            data = [sub, year, mon] + line[27:].split()
                            try:
                                outConn.execute(sqlSed, data)
                                catchmentOutConn.execute(sqlSed, data)
                            except:
                                print('Problem with sed data: {0}'.format(data))
                        
                    
    
    def collectOutputs(self, dirs):
        """Collect ouputs from catchment outputs into output database."""
        # outputDb = self.projDir + '/Scenarios/Default/TablesOut/SWATOutput.mdb'
        # if not os.path.isfile(outputDb):
        #     shutil.copyfile('C:/SWAT/SWATEditor/Databases/SWATOutput.mdb', outputDb)
        # refStr = Parameters._ACCESSSTRING + outputDb
        # with pyodbc.connect(refStr) as conn:
        outputDb = self.projDir + '/Scenarios/Default/TablesOut/SWATOutput.sqlite'
        # crashes can leave corrupt database, so best to remove
        if os.path.isfile(outputDb):
            os.remove(outputDb)
        with sqlite3.connect(outputDb) as conn:
            self.makeOutputTables(conn)
            for d in dirs:
                self.collectOutput(d, conn)
            
def runCatchment(direc):
    cmd = SWATEditorCmd
    _ = subprocess.run([cmd, direc, SWATApp], capture_output=True)
    #_ = subprocess.run([cmd, direc, SWATApp])
                
if __name__ == '__main__':
    try:
        tnc = runTNC()
        print('Running continental project {0}'.format(tnc.projName))
        tnc.runProject()
        print('Created continental project {0}'.format(tnc.projName))
        print('Partitioning project {0} into catchments'.format(tnc.projName))
        p = Partition(tnc.projDb, tnc.projDir)
        t1 = time.process_time()
        p.run()
        t2 = time.process_time()
        print('Partitioned project {0} into {1} catchments in {2} seconds'.format(tnc.projName, p.countCatchments, round(t2-t1)))
        pattern = tnc.projDir + '/Catchments/*'
        # restrict to directories only
        dirs = [d for d in glob.iglob(pattern) if os.path.isdir(d)]
        cpuCount = os.cpu_count()
        numProcesses = min(cpuCount, 24)
        chunk = 1
        args = [(d,) for d in dirs]
        with Pool(processes=numProcesses) as pool:
            res = pool.starmap_async(runCatchment, args, chunk)
            _ = res.get()
        sys.stdout.flush()
        time1 = time.process_time()
        tnc.collectOutputs(dirs)
        time2 = time.process_time()
        print('Collecting output data took {0} seconds'.format(int(time2 - time1)))
    except Exception:
        print('ERROR: exception: {0}'.format(traceback.format_exc()))
    app.exitQgis()
    app.exit()
    del app 
    
    
# Access versions of tables  
#===============================================================================
#     
#     createHRU = """CREATE TABLE hru (
#     LULC CHAR,
#     HRU  INTEGER,
#     HRUGIS  CHAR,
#     SUB  INTEGER,
#     YEAR  INTEGER,  
#     MON   INTEGER,
#      AREAkm2  FLOAT,
#       PRECIPmm  FLOAT,
#       SNOWFALLmm  FLOAT,
#       SNOWMELTmm  FLOAT,
#       IRRmm  FLOAT,
#       PETmm  FLOAT,
#       ETmm   FLOAT,
#      SW_INITmm  FLOAT,
#       SW_ENDmm  FLOAT,
#       PERCmm   FLOAT,
#      GW_RCHGmm FLOAT,
#        DA_RCHGmm FLOAT,
#        REVAPmm   FLOAT,
#      SA_IRRmm  FLOAT,
#       DA_IRRmm  FLOAT,
#       SA_STmm  FLOAT,
#       DA_STmm  FLOAT,
#       SURQ_GENmm FLOAT,
#        SURQ_CNTmm   FLOAT,
#      TLOSS_mm  FLOAT,
#       LATQ_mm  FLOAT,
#       GW_Qmm  FLOAT,
#       WYLD_Qmm FLOAT,
#        DAILYCN   FLOAT,
#      TMP_AVdgC   FLOAT,
#      TMP_MXdgC   FLOAT,
#      TMP_MNdgC   FLOAT,
#      SOL_TMPdgC  FLOAT,
#       SOLARmj_m2 FLOAT,
#        SYLDt_ha  FLOAT,
#       USLEt_ha  FLOAT,
#       N_APPkg_ha FLOAT,
#        P_APPkg_ha   FLOAT,
#      N_AUTOkg_ha FLOAT,
#        P_AUTOkg_ha  FLOAT,
#       NGRZkg_ha  FLOAT,
#       PGRZkg_ha FLOAT,
#        NCFRTkg_ha FLOAT,
#        PCFRTkg_ha FLOAT,
#        NRAINkg_ha FLOAT,
#        NFIXkg_ha  FLOAT,
#       F_MNkg_ha  FLOAT,
#       A_MNkg_ha  FLOAT,
#       A_SNkg_ha  FLOAT,
#       F_MPkg_aha  FLOAT,
#       AO_LPkg_ha  FLOAT,
#       L_APkg_ha  FLOAT,
#       A_SPkg_ha   FLOAT,
#      DNITkg_ha  FLOAT,
#       NUP_kg_ha  FLOAT,
#       PUPkg_ha  FLOAT,
#       ORGNkg_ha  FLOAT,
#       ORGPkg_ha  FLOAT,
#       SEDPkg_h   FLOAT,
#      NSURQkg_ha  FLOAT,
#       NLATQkg_ha FLOAT,
#        NO3Lkg_ha FLOAT,
#        NO3GWkg_ha  FLOAT,
#       SOLPkg_ha FLOAT,
#        P_GWkg_ha  FLOAT,
#       W_STRS  FLOAT,
#       TMP_STRS  FLOAT,
#       N_STRS  FLOAT,
#       P_STRS FLOAT,
#        BIOMt_ha FLOAT,
#        LAI  FLOAT,
#       YLDt_ha FLOAT,
#        BACTPct  FLOAT,
#       BACTLPct  FLOAT,
#       WATB_CLI  FLOAT,
#       WATB_SOL  FLOAT,
#       SNOmm  FLOAT,
#       [CMUPkg/ha] FLOAT,
#        [CMTOTkg/ha] FLOAT,
#        QTILEmm  FLOAT,
#       [TNO3kg/ha]  FLOAT,
#       [LNO3kg/ha]  FLOAT,
#       GW_Q_Dmm FLOAT,
#       LATQCNTmm FLOAT,
#       [TVAPkg/ha] FLOAT
#       );"""
#       
#     createSUB = """CREATE TABLE sub (
#     SUB INTEGER,
#        YEAR INTEGER,
#        MON  INTEGER,
#       AREAkm2 FLOAT,
#        PRECIPmm  FLOAT,
#       SNOWMELTmm FLOAT,
#        PETmm FLOAT,
#        ETmm FLOAT,
#        SWmm  FLOAT,
#       PERCmm  FLOAT,
#       SURQmm  FLOAT,
#       GW_Qmm  FLOAT,
#       WYLDmm  FLOAT,
#       SYLDt_ha FLOAT,
#        ORGNkg_ha FLOAT,
#        ORGPhg_ha FLOAT,
#        NSURQkg_ha  FLOAT,
#       SOLPkg_ha FLOAT,
#        SEDPkg_ha FLOAT,
#        LAT_Qmm FLOAT,
#        LATNO3kg_ha FLOAT,
#        GWNO3kg_ha FLOAT,
#        [CHOLAmic/L] FLOAT,
#        [CBODUmg/L] FLOAT,
#        [DOXQmg/L]  FLOAT,
#       [TNO3kg/ha]  FLOAT,
#       QTILEmm FLOAT,
#       [TVAPkg/ha] FLOAT
#     );"""
# 
#     createRCH = """CREATE TABLE rch (
#         SUB INTEGER,
#          YEAR INTEGER,
#          MON  INTEGER,
#         AREAkm2 FLOAT,
#          FLOW_INcms FLOAT,
#          FLOW_OUTcms  FLOAT,
#         EVAPcms FLOAT,
#          TLOSScms FLOAT,
#          SED_INtons FLOAT,
#          SED_OUTtons FLOAT,
#          SEDCONCmg_kg FLOAT,
#          ORGN_INkg  FLOAT,
#         ORGN_OUTkg  FLOAT,
#         ORGP_INkg  FLOAT,
#         ORGP_OUTkg FLOAT,
#          NO3_INkg  FLOAT,
#         NO3_OUTkg FLOAT,
#          NH4_INkg FLOAT,
#          NH4_OUTkg FLOAT,
#          NO2_INkg  FLOAT,
#         NO2_OUTkg  FLOAT,
#         MINP_INkg FLOAT,
#          MINP_OUTkg FLOAT,
#          CHLA_INkg  FLOAT,
#         CHLA_OUTkg  FLOAT,
#         CBOD_INkg  FLOAT,
#         CBOD_OUTkg FLOAT,
#          DISOX_INkg  FLOAT,
#         DISOX_OUTkg  FLOAT,
#         SOLPST_INmg  FLOAT,
#         SOLPST_OUTmg FLOAT,
#          SORPST_INmg FLOAT,
#          SORPST_OUTmg FLOAT,
#          REACTPTmg  FLOAT,
#         VOLPSTmg FLOAT,
#          SETTLPST_mg  FLOAT,
#         RESUSP_PSTmg  FLOAT,
#         DIFUSEPSTmg FLOAT,
#          REACHBEDPSTmg FLOAT,
#          BURYPSTmg  FLOAT,
#         BED_PSTmg FLOAT,
#          BACTP_OUTct FLOAT,
#          BACTLP_OUTct FLOAT,
#          CMETAL1kg  FLOAT,
#         CMETAL2kg FLOAT,
#          CMETAL3kg FLOAT,
#          TOT_Nkg  FLOAT,
#         TOT_Pkg  FLOAT,
#         [NO3CONCmg/l] FLOAT,
#          WTMPdegc FLOAT
#     );"""   
#     
#     createWQL = """CREATE TABLE wql (
#     YEAR INTEGER,
#     RCH INTEGER,
#     DAY INTEGER,
#     WTEMP FLOAT,
#     ALGAE_IN FLOAT,
#     ALGAE_O FLOAT,
#     ORGN_IN FLOAT,
#     ORGN_OUT FLOAT,
#     NH4_IN FLOAT,
#     NH4_OUT FLOAT,
#     NO2_IN FLOAT,
#     NO2_OUT FLOAT,
#     NO3_IN FLOAT,
#     NO3_OUT FLOAT,
#     ORGP_IN FLOAT,
#     ORGP_OUT FLOAT,
#     SOLP_IN FLOAT,
#     SOLP_OUT FLOAT,
#     CBOD_IN FLOAT,
#     CBOD_OUT FLOAT,
#     SAT_OX FLOAT,
#     DISOX_IN FLOAT,
#     DISOX_O FLOAT,
#     H20VOLUME FLOAT,
#     TRVL_TIME FLOAT
#     );"""
#     
#     createSED = """CREATE TABLE sed (
#     RCH INTEGER,
#     YEAR INTEGER,
#     MON INTEGER,
#     AREA FLOAT,
#     SED_IN FLOAT,
#     SED_OUT FLOAT,
#     SAND_IN FLOAT,
#     SAND_OUT FLOAT,
#     SILT_IN FLOAT,
#     SILT_OUT FLOAT,
#     CLAY_IN FLOAT,
#     CLAY_OUT FLOAT,
#     SMAG_IN FLOAT,
#     SMAG_OUT FLOAT,
#     LAG_IN FLOAT,
#     LAG_OUT FLOAT,
#     GRA_IN FLOAT,
#     GRA_OUT FLOAT,
#     CH_BNK FLOAT,
#     CH_BED FLOAT,
#     CH_DEP FLOAT,
#     FP_DEP FLOAT,
#     TSS FLOAT
#     );"""
# 
#     
#===============================================================================