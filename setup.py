# Python distutils stuff
import os
import sys
from distutils.core import setup, Extension

share_files = [( 'share/freevo/config/', ['share/config/tvserver.conf'])]

# now start the python magic
setup (name         = "freevo",
       version      = "2.0",
       description  = "Freevo",
       author       = "Krister Lagerstrom, et al.",
       author_email = "freevo-devel@lists.sourceforge.net",
       url          = "http://www.freevo.org",
       license      = "GPL",

       package_dir = { 'freevo.tvserver': 'src' },
       packages    = [ 'freevo.tvserver', 'freevo.tvserver' ],
       scripts     = [ 'bin/recordserver.py' ],
       data_files  = share_files
       )
