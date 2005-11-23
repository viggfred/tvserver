# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# setup.py - setup script for installing the freevo module
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Freevo - A Home Theater PC framework
# Copyright (C) 2002-2005 Krister Lagerstrom, Dirk Meyer, et al.
#
# First Edition: Dirk Meyer <dischi@freevo.org>
# Maintainer:    Dirk Meyer <dischi@freevo.org>
#
# Please see the file doc/CREDITS for a complete list of authors.
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

from freevo.distribution import setup

# now start the python magic
setup (name         = 'freevo-tvserver',
       module       = 'tvserver',
       version      = '2.0',
       description  = 'Freevo TV Server',
       author       = 'Dirk Meyer, et al.',
       author_email = 'freevo-devel@lists.sourceforge.net',
       url          = 'http://www.freevo.org',
       license      = 'GPL',
       )
