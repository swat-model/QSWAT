# -*- coding: utf-8 -*-
'''
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
 *   This program is free software you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
'''
# Import the PyQt and QGIS libraries
try:
    from qgis.PyQt.QtCore import Qt  # @UnusedImport
    #from qgis.PyQt.QtGui import * # @UnusedWildImport
    #from qgis.core import * # @UnusedWildImport
except:
    from qgis.PyQt.QtCore import Qt  # @Reimport
# Import the code for the dialog
from .aboutdialog import aboutDialog
import webbrowser

class AboutQSWAT:
    
    """Provide basic information about QSWAT, including version, and link to SWAT website."""
    
    def __init__(self, gv):
        """Initialise."""
        self._gv = gv
        self._dlg = aboutDialog()
        try:
            self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        except AttributeError:
            pass
        if self._gv:
            self._dlg.move(self._gv.aboutPos)
        
    def run(self, version):
        """Run the form."""
        self._dlg.SWATHomeButton.clicked.connect(self.openSWATUrl)
        self._dlg.closeButton.clicked.connect(self._dlg.close)
        text = """
QSWAT version: {0}

QSWAT runs with QGIS 3 (from version 3.16.14) and QGIS 4

Python version: 3.9 or 3.12

Current restrictions:
- runs only in Windows
        """.format(version)
        self._dlg.textBrowser.setText(text)
        self._dlg.exec()
        if self._gv:
            self._gv.aboutPos = self._dlg.pos()
        
    def openSWATUrl(self):
        """Open SWAT website."""
        webbrowser.open('http://swat.tamu.edu/')
        
        
