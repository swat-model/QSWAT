This repository holds the source code for the QGIS 3 plugin QSWAT3, which is an assistant for providing input data for [SWAT](http://swat.tamu.edu/).

## Build
The repository holds an Eclipse project.  It was created on Windows and probably only runs asis in a Windows Eclipse.

There is a Makefile that should provide enough information to build QSWAT3.  It is only intended for Windows since QSWAT3 uses MicrosoftAccess.

Note that the only interesting projects in the Makefile are QSWAT3, QSWAT3_64 and QSWAT3_9.  QSWATGrid was used to try out grids before QSWATPlus was developed.
QSWAT3 is 32-bit for use with 32-bit Microsoft Office.  QSWAT3_64 is for 64-bit Microsoft Office and QGIS before 3.16.14 using Python 3.7.  QSWAT3_9 is 64 bit, for current QGIS using Python 3.9.

### Environment variables
The following need to be set to run make:

HOME: 				User's home directory 

OSGEO4W\_ROOT:  	Path to QGIS e.g. C:\\Program Files (x86)\\QGIS 3.10 or C:\\Program Files\\QGIS 3.22.8

PATH: 				C:\\MinGW\\bin;C:\\MinGW\\msys\\1.0\\bin;%OSGEO4W\_ROOT%\\bin (assuming this is correct placement of MinGW, needed for mingw32-make, mkdir, etc)

PYTHONHOME: 		%OSGEO4W\_ROOT%\\apps\\Python37 or %OSGEO4W\_ROOT%\\apps\\Python39

QSWAT\_PROJECT: 	QSWAT3 or QSWAT3_64 or QSWAT3_9

