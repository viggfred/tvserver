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
import kaa.rpc, kaa.rpc2
import kaa.epg
from kaa.utils import utc2localtime, localtime2utc

# tvserver imports
from recording import Recordings
from favorite import Favorites

# get logging object
log = logging.getLogger('tvserver')

class TVServer(object):

    def __init__(self, address, password):
        self.signals = kaa.Signals('connected', 'disconnected', 'changed')
        self.recordings = Recordings(self)
        self.favorites = Favorites(self)
        self.channel = kaa.rpc2.connect(address, password, retry=1)
        self.channel.register(self)
        # connect kaa.epg database to port + 1
        address, port = address.split(':')
        kaa.epg.connect('%s:%s' % (address, int(port) + 1), password)

    @kaa.coroutine()
    def _connected(self, *args):
        log.info('connected to tvserver')
        self.recordings._update((yield self.channel.rpc('recording_list')))
        self.favorites._update((yield self.channel.rpc('favorite_list')))
        self.signals['connected'].emit()

    def _disconnected(self):
        self.signals['disconnected'].emit()
        log.info('disconnected from tvserver')
        kaa.OneShotTimer(self._connect).start(1)
        self.recordings._clear()
        self.favorites._clear()

    @property
    def connected(self):
        return self.channel.status == kaa.rpc2.CONNECTED

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
        return self.channel.rpc('recording_add', name, channel, priority, start, stop, **info)

    def recording_remove(self, id):
        """
        Remove a recording

        @param id: id the the recording to be removed
        @returns: InProgress object
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.channel.rpc('recording_remove', id)

    def favorite_update(self):
        """
        Check list of favorites against EPG and update
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.channel.rpc('favorite_update')

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
        return self.channel.rpc('favorite_add', title, channels, priority, days, times, once)

    def favorite_remove(self, id):
        """
        remove a favorite

        @param id: id of the favorite
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.channel.rpc('favorite_remove', id)

    def favorite_modify(self, id, **kwargs):
        """
        @param id: id of the favorite
        """
        if not self.connected:
            raise RuntimeError('not connected to tvserver')
        return self.channel.rpc('favorite_remove', id, **kwargs)

    @kaa.rpc.expose()
    def identify(self):
        return 'client'

    @kaa.rpc.expose('recording_update')
    def _recording_update(self, *recordings):
        self.recordings._update(recordings)
        self.signals['changed'].emit()

    @kaa.rpc.expose('favorite_update')
    def _favorite_update(self, *fav):
        self.recordings._update(fav)
        self.signals['changed'].emit()
