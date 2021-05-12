# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Create SWAT inputs
                              -------------------
        begin                : 2014-07-18
        copyright            : (C) 2014 by Chris George
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
# Import the PyQt and QGIS libraries
from PyQt5.QtCore import QSettings, Qt  # @UnresolvedImport
from PyQt5.QtGui import QTextCursor  # @UnresolvedImport
from qgis.core import QgsProject  # @UnresolvedImport
import os.path
import subprocess

from .QSWATUtils import QSWATUtils  # @UnresolvedImport
from .parameters import Parameters  # @UnresolvedImport
    

class TauDEMUtils:
    
    """Methods for calling TauDEM executables."""
    
    @staticmethod
    def runPitFill(demFile, felFile, numProcesses, output):
        """Run PitFill."""
        return TauDEMUtils.run('PitRemove', [('-z', demFile)], [], [('-fel', felFile)], numProcesses, output, False)

    @staticmethod
    def runD8FlowDir(felFile, sd8File, pFile, numProcesses, output):
        """Run D8FlowDir."""
        return TauDEMUtils.run('D8FlowDir', [('-fel', felFile)], [], [('-sd8', sd8File), ('-p', pFile)], numProcesses, output, False)

    @staticmethod
    def runDinfFlowDir(felFile, slpFile, angFile, numProcesses, output):
        """Run DinfFlowDir."""
        return TauDEMUtils.run('DinfFlowDir', [('-fel', felFile)], [], [('-slp', slpFile), ('-ang', angFile)], numProcesses, output, False)

    @staticmethod
    def runAreaD8(pFile, ad8File, outletFile, weightFile, numProcesses, output, contCheck=False, mustRun=True):
        """Run AreaD8."""
        inFiles = [('-p', pFile)]
        if outletFile:
            inFiles.append(('-o', outletFile))
        if weightFile:
            inFiles.append(('-wg', weightFile))
        check = [] if contCheck else [('-nc', '')]
        return TauDEMUtils.run('AreaD8', inFiles, check, [('-ad8', ad8File) ], numProcesses, output, mustRun)

    @staticmethod
    def runAreaDinf(angFile, scaFile, outletFile, numProcesses, output, mustRun=True):
        """Run AreaDinf."""
        inFiles = [('-ang', angFile)]
        if outletFile:
            inFiles.append(('-o', outletFile))
        return TauDEMUtils.run('AreaDinf', inFiles, [('-nc', '')], [('-sca', scaFile)], numProcesses, output, mustRun)

    @staticmethod
    def runGridNet(pFile, plenFile, tlenFile, gordFile, outletFile, numProcesses, output, mustRun=True):
        """Run GridNet."""
        inFiles = [('-p', pFile)]
        if outletFile:
            inFiles.append(('-o', outletFile))
        return TauDEMUtils.run('GridNet', inFiles, [], [('-plen', plenFile), ('-tlen', tlenFile), ('-gord', gordFile)], numProcesses, output, mustRun)
    
    @staticmethod
    def runThreshold(ad8File, srcFile, threshold, numProcesses, output, mustRun=True):
        """Run Threshold."""
        return TauDEMUtils.run('Threshold', [('-ssa', ad8File)], [('-thresh', threshold)], [('-src', srcFile)], numProcesses, output, mustRun)
    
    @staticmethod
    def runStreamNet(felFile, pFile, ad8File, srcFile, outletFile, ordFile, treeFile, coordFile, streamFile, wFile, numProcesses, output, mustRun=True):
        """Run StreamNet."""
        inFiles = [('-fel', felFile), ('-p', pFile), ('-ad8', ad8File), ('-src', srcFile)]
        if outletFile:
            inFiles.append(('-o', outletFile))
        return TauDEMUtils.run('StreamNet', inFiles, [], 
                               [('-ord', ordFile), ('-tree', treeFile), ('-coord', coordFile), ('-net', streamFile), ('-w', wFile)], 
                               numProcesses, output, mustRun)
    @staticmethod
    def runMoveOutlets(pFile, srcFile, outletFile, movedOutletFile, numProcesses, output, mustRun=True):
        """Run MoveOutlets."""
        return TauDEMUtils.run('MoveOutletsToStreams', [('-p', pFile), ('-src', srcFile), ('-o', outletFile)], [], [('-om', movedOutletFile)], 
                               numProcesses, output, mustRun)
        
    @staticmethod
    def runDistanceToStreams(pFile, hd8File, distFile, threshold, numProcesses, output, mustRun=True):
        """Run D8HDistToStrm."""
        return TauDEMUtils.run('D8HDistToStrm', [('-p', pFile), ('-src', hd8File)], [('-thresh', threshold)], [('-dist', distFile)], 
                               numProcesses, output, mustRun)
    
    @staticmethod   
    def run(command, inFiles, inParms, outFiles, numProcesses, output, mustRun):
        """
        Run TauDEM command, using mpiexec if numProcesses is not zero.
        
        Parameters:
        inFiles: list of pairs of parameter id (string) and file path (string) 
        for input files.  May not be empty.
        inParms: list of pairs of parameter id (string) and parameter value 
        (string) for input parameters.
        For a parameter which is a flag with no value, parameter value 
        should be empty string.
        outFiles: list of pairs of parameter id (string) and file path 
        (string) for output files.
        numProcesses: number of processes to use (int).  
        Zero means do not use mpiexec.
        output: buffer for TauDEM output (QTextEdit).
        if output is None use as flag that running in batch, and errors are simply printed.
        Return: True if no error detected, else false.
        The command is not executed if 
        (1) mustRun is false (since it is set true for results that depend 
        on the threshold setting or an outlets file, which might have changed), and
        (2) all output files exist and were last modified no earlier 
        than the first input file.
        An error is detected if any input file does not exist or,
        after running the TauDEM command, 
        any output file does not exist or was last modified earlier 
        than the first input file.
        For successful output files the .prj file is copied 
        from the first input file.
        The Taudem executable directory and the mpiexec path are 
        read from QSettings.
        """
        hasQGIS = not output == None
        baseFile = inFiles[0][1]
        needToRun = mustRun
        if not needToRun:
            for (_, fileName) in outFiles:
                if not QSWATUtils.isUpToDate(baseFile, fileName):
                    needToRun = True
                    break
        if not needToRun:
            return True
        commands = []
        if hasQGIS:
            settings = QSettings()
            output.append('------------------- TauDEM command: -------------------\n')
            mpiexecDir = settings.value('/QSWAT/mpiexecDir', '')
            mpiexecPath = QSWATUtils.join(mpiexecDir, Parameters._MPIEXEC) if mpiexecDir != '' else ''
            if numProcesses != 0 and mpiexecDir != '' and os.path.exists(mpiexecDir):
                commands.append(mpiexecPath)
                commands.append('-n') 
                commands.append(str(numProcesses))
            swatEditorDir = settings.value('/QSWAT/SWATEditorDir')
        else:
            # batch mode
            swatEditorDir = r'C:/SWAT/SWATEditor'
        tauDEM539Dir = QSWATUtils.join(swatEditorDir, Parameters._TAUDEM539DIR)
        if os.path.isdir(tauDEM539Dir):
            tauDEMDir = tauDEM539Dir
            # pass StreamNet a directory rather than shapefile so shapefile created as a directory
            # this prevents problem that .shp cannot be deleted, but GDAL then complains that the .shp file is not a directory
            # also have to set -netlyr parameter to stop TauDEM failing to parse filename without .shp as a layer name
            # TauDEM version 5.1.2 does not support -netlyr parameter
            if command == 'StreamNet':
                # make copy so can rewrite
                outFilesCopy = outFiles[:]
                outFiles = []
                for (pid, outFile) in outFilesCopy:
                    if pid == '-net':
                        streamBase = os.path.splitext(outFile)[0]
                        # streamBase may have form P/X/X, in which case streamDir is P/X, else streamDir is streamBase
                        streamDir1, baseName = os.path.split(streamBase)
                        dirName = os.path.split(streamDir1)[1]
                        if dirName == baseName:
                            streamDir = streamDir1
                        else:
                            streamDir = streamBase
                            if not os.path.isdir(streamDir):
                                os.mkdir(streamDir)
                        outFiles.append((pid, streamDir))
                    else:
                        outFiles.append((pid, outFile))
                inParms.append(('-netlyr', os.path.split(streamDir)[1]))
        else:
            tauDEMDir = QSWATUtils.join(swatEditorDir, Parameters._TAUDEMDIR)
            if not os.path.isdir(tauDEMDir):
                TauDEMUtils.error('Cannot find TauDEM directory as {0} or {1}'.format(tauDEM539Dir, tauDEMDir), hasQGIS)
                return False
        commands.append(QSWATUtils.join(tauDEMDir, command))
        for (pid, fileName) in inFiles:
            if not os.path.exists(fileName):
                TauDEMUtils.error('File {0} does not exist'.format(fileName), hasQGIS)
                return False
            commands.append(pid)
            commands.append(fileName)
        for (pid, parm) in inParms:
            commands.append(pid)
            # allow for parameter which is flag with no value
            if not parm == '':
                commands.append(parm)
        # remove outFiles so any error will be reported
        root = QgsProject.instance().layerTreeRoot()
        for (_, fileName) in outFiles:
            if os.path.isdir(fileName):
                QSWATUtils.tryRemoveShapefileLayerAndDir(fileName, root)
            else:
                QSWATUtils.tryRemoveLayerAndFiles(fileName, root)
        for (pid, fileName) in outFiles:
            commands.append(pid)
            commands.append(fileName)
        if hasQGIS:
            output.append(' '.join(commands) + '\n\n')
            output.moveCursor(QTextCursor.End)
        proc = subprocess.run(commands, 
                              shell=True, 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.STDOUT, 
                              universal_newlines=True)
        if hasQGIS:
            assert output is not None
            output.append(proc.stdout)
            output.moveCursor(QTextCursor.End)
        else:
            print(proc.stdout)
        # proc.returncode always seems to be None
        # so check TauDEM run by checking output file exists and modified later than DEM
        # not ideal as may eg generate empty file
        # TODO: improve on this
        ok = proc.returncode == 0
        msg = command + ' created '
        for (pid, fileName) in outFiles:
            if QSWATUtils.isUpToDate(baseFile, fileName):
                msg += fileName
                msg += ' '
            else:
                ok = False
        if ok:
            TauDEMUtils.loginfo(msg, hasQGIS)
        else:
            if hasQGIS: 
                assert output is not None    
                origColour = output.textColor()
                output.setTextColor(Qt.red)
                output.append(QSWATUtils.trans('*** Problem with TauDEM {0}: please examine output above. ***'.format(command)))
                output.setTextColor(origColour)
            msg += 'and failed'
            TauDEMUtils.logerror(msg, hasQGIS)
        return ok

    @staticmethod
    def taudemHelp():
        """Display TauDEM help file."""
        settings = QSettings()
        taudemHelpFile = QSWATUtils.join(QSWATUtils.join(settings.value('/QSWAT/SWATEditorDir'), Parameters._TAUDEMDIR), Parameters._TAUDEMHELP)
        os.startfile(taudemHelpFile)
        
    @staticmethod
    def error(msg, hasQGIS):
        """Report error, just printing if no QGIS running."""
        if hasQGIS:
            QSWATUtils.error(msg, False)
        else:
            print(msg)
            
    @staticmethod
    def loginfo(msg, hasQGIS):
        """Log msg, just printing if no QGIS running."""
        if hasQGIS:
            QSWATUtils.loginfo(msg)
        else:
            print(msg)
            
    @staticmethod
    def logerror(msg, hasQGIS):
        """Log error msg, just printing if no QGIS running."""
        if hasQGIS:
            QSWATUtils.logerror(msg)
        else:
            print(msg)
        