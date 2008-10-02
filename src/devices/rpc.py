# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# rpc.py - kaa.rpc interface
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
import socket
import logging
import time

# kaa imports
import kaa
import kaa.rpc
from kaa.utils import utc2localtime

# tvdev imports
from system import config, get_devices

# get logging object
log = logging.getLogger()

class RPCDevice(object):
    """
    Controller for kaa.rpc.
    """
    def __init__(self, device):
        self.device = device
        self.device.signals['started'].connect(self.started)
        self.device.signals['stopped'].connect(self.stopped)
        self.device.signals['epg-update'].connect(self.epg_update)
        self._link = None

    def connect(self, address, password):
        try:
            self._link = kaa.rpc.Client(address, password)
            self._link.connect(self)
            self._link.signals['closed'].connect(self.disconnected, address, password)
            self.rpc = self._link.rpc
            log.info('connected to tvserver')
        except kaa.rpc.ConnectError:
            kaa.OneShotTimer(self.connect, address, password).start(1)

    def disconnected(self, address, password):
        log.info('disconnected from tvserver')
        self._link = None
        # FIXME: should be stop all recordings? Maybe on reconnect. We need to
        # to make sure the tvserver has a none state.
        kaa.OneShotTimer(self.connect, address, password).start(1)

    @kaa.rpc.expose()
    def identify(self):
        name = '%s:%s' % (socket.gethostname(), self.device.name)
        return name, self.device.priority, self.device.multiplexes, \
               self.device.capabilities

    @kaa.rpc.expose()
    def schedule(self, channel, start, stop, url):
        return self.device.schedule(
            channel, utc2localtime(start), utc2localtime(stop), url)

    @kaa.rpc.expose()
    def create_fxd(self, filename, content):
        if filename.startswith('file:'):
            filename = filename[5:]
        if filename.find('://') > 0:
            return
        open(os.path.join(config.directory, filename), 'w').write(content)

    @kaa.rpc.expose()
    def remove(self, id):
        return self.device.remove(id)

    def started(self, id):
        if not self._link:
            log.warning('device not connected')
            return
        self.rpc('started', id)

    def stopped(self, id):
        if not self._link:
            log.warning('device not connected')
            return
        self.rpc('stopped', id)

    @kaa.coroutine()
    def epg_update(self):
        if not self._link:
            log.warning('device not connected')
            yield None
        epg = self.device.epg()
        if isinstance(epg, kaa.InProgress):
            epg = yield epg
        self.rpc('epg', epg)
        
# load all devices
_devices = []

@kaa.coroutine()
def connect(address, password):
    """
    Connect to tvserver using kaa.rpc
    """
    for device in (yield get_devices()):
        rpc = RPCDevice(device)
        rpc.connect(address, password)
        _devices.append(rpc)
    yield _devices is not []
