# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# mplayer.py - Mplayer based Plugin
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
# Copyright (C) 2008 Dirk Meyer, et al.
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

# python imports
import os

# kaa imports
import kaa

# tvdev imports
from template import PluginTemplate

class Plugin(PluginTemplate):
    def __init__(self, config):
        super(Plugin, self).__init__(config)
        channels = []
        for c in open(os.path.expanduser('~/.mplayer/channels.conf')).readlines():
            c = c.split(':')[0]
            if not c in channels:
                channels.append(c)
        self.multiplexes = [ [ c ] for c in channels ]
        self.initialized = True

    def start(self, channel, url):
        self._mplayer = kaa.Process('mplayer')
        self._mplayer.start(('dvb://%s' % channel, '-dumpstream', '-dumpfile', url[5:]))
        return 0

    def stop(self, id):
        self._mplayer.stop()
