# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# setup.py - setup script for installing the freevo module
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Freevo - A Home Theater PC framework
# Copyright (C) 2005-2006,2008 Dirk Meyer, et al.
#
# First Edition: Dirk Meyer <dischi@freevo.org>
# Maintainer:    Dirk Meyer <dischi@freevo.org>
#
# Please see the file AUTHORS for a complete list of authors.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MER-
# CHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# -----------------------------------------------------------------------------

import sys

try:
    # kaa base imports
    from kaa.distribution.core import Extension, setup
except ImportError:
    print 'kaa.base not installed'
    sys.exit(1)

# We require python 2.5 or later, so complain if that isn't satisfied.
if sys.version.split()[0] < '2.5':
    print "Python 2.5 or later required."
    sys.exit(1)

setup(project='freevo',
      module       = 'tvserver',
      version      = '2.0.0',
      license      = 'GPL',
      summary      = 'Freevo TV Server',
      author       = 'Dirk Meyer, et al.',
      author_email = 'freevo-devel@lists.sourceforge.net',
      url          = 'http://www.freevo.org',
      scripts      = [ 'bin/freevo-tvserver' ]
)
