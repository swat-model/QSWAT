from distutils.core import setup
    
from Cython.Build import cythonize
import os
import numpy
includePath = os.environ['OSGEO4W_ROOT'] + r'/apps/Python37/include'
if 'INCLUDE' in os.environ:
    os.environ['INCLUDE'] = os.environ['INCLUDE'] + ';' + includePath + ';' + numpy.get_include()
else:
    os.environ['INCLUDE'] = includePath + ';' + numpy.get_include()


# setup(
#     name = "pyxes",
#     package_dir = {'QSWAT3': ''}, 
#     ext_modules = cythonize('*.pyx', include_path = [os.environ['INCLUDE']]),
# )
setup(
    name = "pyxes",
    package_dir = {'QSWAT': ''}, 
    ext_modules = cythonize('*.pyx'),
    include_dirs = [numpy.get_include()],
)
