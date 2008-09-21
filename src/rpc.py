# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# rpc.py - kaa.rpc interface to connect to a TVServer
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
import logging
import time

# kaa imports
import kaa
import kaa.rpc
import kaa.epg
from kaa.utils import utc2localtime, localtime2utc

# tvserver imports
from recording import Recordings
from favorite import Favorites

# get logging object
log = logging.getLogger('tvserver')

class TVServer(object):

    rpc = None

    def __init__(self, address, password):
        self.signals = kaa.Signals('connected', 'disconnected', 'changed')
        self.recordings = Recordings(self)
        self.favorites = Favorites(self)
        self.address = address
        self.password = password
        self._connect()

    def _connect(self):
        try:
            self._link = kaa.rpc.Client(self.address, self.password)
            self._link.connect(self)
            self._link.signals['closed'].connect(self._disconnected)
            self.rpc = self._link.rpc
            address, port = self.address.split(':')
            kaa.epg.connect('%s:%s' % (address, int(port) + 1), self.password)
            self.rpc('recording_list').connect(self.recordings._update)
            l = self.rpc('favorite_list')
            l.connect(self.favorites._update)
            l.connect(self._connected)
        except kaa.rpc.ConnectError:
            kaa.OneShotTimer(self._connect).start(1)

    def _connected(self, *args):
        log.info('connected to tvserver')
        self.signals['connected'].emit()

    def _disconnected(self):
        self.signals['disconnected'].emit()
        log.info('disconnected from tvserver')
        kaa.OneShotTimer(self._connect).start(1)
        self.recordings._clear()
        self.favorites._clear()
        self.rpc = None

    @property
    def connected(self):
        return self.rpc is not None

    def recording_add(self, name, channel, priority, start, stop, **info):
        """
        Schedule a recording

        @param name: name of the program
        @param channel: name of the channel
        @param start: start time in localtime
        @param stop: stop time in localtime
        @param info: additional information
        @returns: InProgress object
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        start = localtime2utc(start)
        stop = localtime2utc(stop)
        return self.rpc('recording_add', name, channel, priority, start, stop, **info)

    def recording_remove(self, id):
        """
        Remove a recording

        @param id: id the the recording to be removed
        @returns: InProgress object
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.rpc('recording_remove', id)

    def favorite_add(self, title, channels, days, times, priority, once):
        """
        add a favorite

        @param channels: list of channel names are 'ANY'
        @param days: list of days ( 0 = Sunday - 6 = Saturday ) or 'ANY'
        @param times: list of hh:mm-hh:mm or 'ANY'
        @param priority: priority for the recordings
        @param once: True if only one recodring should be made
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        if channels == 'ANY':
            channels = [ c.name for c in kaa.epg.get_channels() ]
        if days == 'ANY':
            days = [ 0, 1, 2, 3, 4, 5, 6 ]
        if times == 'ANY':
            times = [ '00:00-23:59' ]
        return self.rpc('favorite_add', title, channels, priority, days, times, once)

    def favorite_remove(self, id):
        """
        remove a favorite

        @param id: id of the favorite
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.rpc('favorite_remove', id)

    def favorite_modify(self, id, **kwargs):
        """
        @param id: id of the favorite
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.rpc('favorite_remove', id, **kwargs)

    @kaa.rpc.expose()
    def identify(self):
        return 'client'

    @kaa.rpc.expose()
    def recording_update(self, *recordings):
        self.recordings._update(recordings)
        self.signals['changed'].emit()

    @kaa.rpc.expose()
    def favorite_update(self, *fav):
        self.recordings._update(fav)
        self.signals['changed'].emit()
