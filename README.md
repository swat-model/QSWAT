This repository holds the source code for the QGIS 3 plugin QSWAT3, which is an assistant for providing input data for [SWAT](http://swat.tamu.edu/).

## Build
The repository holds an Eclipse project.  It was created on Windows and probably only runs asis in a Windows Eclipse.

There is a Makefile that should provide enough information to build QSWAT3.  It is only intended for Windows since QSWAT3 uses MicrosoftAccess.

Note that the only interesting project in the Makefile is QSWAT3.  QSWATGrid was used to try out grids before QSWATPlus was developed,
and the 64-bit setting was just to test 64-bit compilation: QSWAT3 needs to be 32-bit because it uses Microsoft Access.

### Environment variables
The following need to be set to run make:

HOME: 				User's home directory 

OSGEO4W\_ROOT:  	Path to QGIS e.g. C:\\Program Files (x86)\\QGIS 3.10

PATH: 				C:\\MinGW\\bin;C:\\MinGW\\msys\\1.0\\bin;%OSGEO4W\_ROOT%\\bin (assuming this is correct placement of MinGW, needed for mingw32-make, mkdir, etc)

PYTHONHOME: 		%OSGEO4W\_ROOT%\\apps\\Python37

QSWAT\_PROJECT: 	QSWAT3

