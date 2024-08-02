This repository holds the source code for the QGIS plugin QSWAT, which is an assistant for providing input data for [SWAT](http://swat.tamu.edu/).

## Build
The repository holds an Eclipse project.  It was created on Windows and probably only runs asis in a Windows Eclipse.

There is a Makefile that should provide enough information to build QSWAT. 

Note that the only interesting projects in the Makefile is QSWAT.  It is for Windows only and can be used with long term release versions of QGIS that use Python 3.7, 3.9 or 3.12.
QSWAT3 is 32-bit for use with 32-bit Microsoft Office.  QSWAT3_64 is only for 64-bit Microsoft Office and QGIS before 3.16.14 using Python 3.7.  QSWAT3_9 is 64 bit, only for QGIS using Python 3.9, and QSWAT3_12 is only for QGIS using Python 3.12.  QSWATGrid was used to try out grids before QSWATPlus was developed.


### Environment variables
The following need to be set to run make:

HOME: 				User's home directory 

OSGEO4W\_ROOT:  	Path to QGIS e.g. C:\\OSGEO4W.  Must be a network insteller version of QGIS, with python-dev package added

PATH: 				C:\\MinGW\\bin;C:\\MinGW\\msys\\1.0\\bin;%OSGEO4W\_ROOT%\\bin (assuming this is correct placement of MinGW, needed for mingw32-make, mkdir, etc)

QSWAT\_PROJECT: 	QSWAT

INCLUDE				C:\Program Files (x86)\Windows Kits\10\Include\10.0.19041.0\ucrt;C:\Program Files (x86)\Windows Kits\10\Include\10.0.19041.0\shared
					(Paths of standard include files for Microsoft C compiler)

LIB					C:\Program Files (x86)\Windows Kits\10\Lib\10.0.19041.0\um\x64;C:\Program Files (x86)\Windows Kits\10\Lib\10.0.19041.0\ucrt\x64
					(Paths of standard libraries for Microsoft C linker)