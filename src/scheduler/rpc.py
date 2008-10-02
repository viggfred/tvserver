# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# rpc.py - kaa.rpc based server
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

__all__ = [ 'RPCServer' ]

# python imports
import logging

# kaa imports
import kaa.rpc
import kaa.epg

# tvserver imports
from config import config
from controller import Controller
from device import TVDevice, add_device, remove_device, get_devices

# get logging object
log = logging.getLogger('tvserver')

class RPCServer(Controller):

    def __init__(self, datafile):
        self._last_listing = []
        self._clients = []
        super(RPCServer, self).__init__(datafile)

    def listen(self):
        """
        Start RPC listen mode for incoming connections
        """
        self._rpc = kaa.rpc.Server(config.rpc.address, config.rpc.password)
        self._rpc.signals['client_connected'].connect(self.client_connected)
        self._rpc.connect(self)
        # get kaa.epg address and port
        ip, port = config.rpc.address.split(':')
        kaa.epg.listen('%s:%s' % (ip, int(port) + 1), config.rpc.password)

    @kaa.coroutine()
    def client_connected(self, client):
        """
        Connect a new client to the server.
        """
        client.signals['closed'].connect(self.client_closed, client)
        info = (yield client.rpc('identify'))
        if info == 'client':
            self._clients.append(client)
        else:
            add_device(RPCDevice(client, *info))

    def client_closed(self, client):
        """
        Callback when a client disconnects.
        """
        log.info('Client disconnected: %s', client)
        if client in self._clients:
            self._clients.remove(client)
        else:
            for device in get_devices():
                if device._rpc == client:
                    remove_device(device)
                    break
            else:
                log.error('unable to find device %s' % client)

    @kaa.coroutine()
    def reschedule(self):
        """
        Reschedule all recordings.
        """
        if not (yield super(RPCServer, self).reschedule()):
            yield False
        sending = []
        listing = []
        for r in self.recordings:
            to_list = r.to_list()
            listing.append(to_list)
            if not to_list in self._last_listing:
                sending.append(to_list)
        self._last_listing = listing
        # send update to all clients
        if sending:
            log.info("send update for %s recordings", len(sending))
            for c in self._clients:
                c.rpc('recording_update', *sending)
        yield True

    def _recorder_start(self, recording):
        super(RPCServer, self)._recorder_start(recording)
        # send update to all clients
        for c in self._clients:
            c.rpc('recording_update', recording.to_list())

    def _recorder_stop(self, recording):
        super(RPCServer, self)._recorder_stop(recording)
        # send update to all clients
        for c in self._clients:
            c.rpc('recording_update', recording.to_list())

    @kaa.rpc.expose()
    def recording_list(self):
        """
        list the current recordins in a short form.
        """
        log.info('send list for %s recordings' % len(self.recordings))
        return [ r.to_list() for r in self.recordings ]

    @kaa.rpc.expose()
    def recording_add(self, name, channel, priority, start, stop, **info):
        """
        add a new recording
        """
        return super(RPCServer, self).recording_add(
            name, channel, priority, start, stop, **info).id

    @kaa.rpc.expose()
    def recording_remove(self, id):
        """
        remove a recording
        """
        return super(RPCServer, self).recording_remove(id)

    @kaa.rpc.expose()
    def rpc_recording_modify(self, id, **kwargs):
        """
        modify a recording
        """
        return super(RPCServer, self).rpc_recording_modify(id, **kwargs)

    @kaa.rpc.expose()
    def favorite_update(self):
        """
        updates favorites with data from the database
        """
        return super(RPCServer, self).favorite_update()

    @kaa.rpc.expose()
    def favorite_list(self):
        """
        Return list of all favorites
        """
        log.info('send list for %s favorites' % len(self.favorites))
        return [ f.to_list() for f in self.favorites ]

    @kaa.rpc.expose()
    def favorite_add(self, name, channels, priority, days, times, once, substring):
        """
        add a favorite
        """
        super(RPCServer, self).favorite_add(
            name, channels, priority, days, times, once, substring)
        # send update to all clients
        msg = [ f.to_list() for f in self.favorites ]
        for c in self._clients:
            c.rpc('favorite_update', *msg)

    @kaa.rpc.expose()
    def favorite_remove(self, id):
        """
        remove a favorite
        """
        super(RPCServer, self).favorite_remove(id)
        # send update to all clients
        msg = [ f.to_list() for f in self.favorites ]
        for c in self._clients:
            c.rpc('favorite_update', *msg)

    @kaa.rpc.expose()
    def favorite_modify(self, id, **kwargs):
        """
        modify a recording
        """
        super(RPCServer, self).favorite_modify(id, **kwargs)
        # send update to all clients
        msg = [ f.to_list() for f in self.favorites ]
        for c in self._clients:
            c.rpc('favorite_update', *msg)


class RPCDevice(TVDevice):

    def __init__(self, rpcsocket, name, priority, multiplexes, capabilities):
        super(RPCDevice, self).__init__(name, priority, multiplexes, capabilities)
        rpcsocket.connect(self)
        self._rpc = rpcsocket
        self.rpc = rpcsocket.rpc

    def schedule(self, recording, start, stop):
        super(RPCDevice, self).schedule(recording, start, stop)
        # update recordings at the remote application
        self.sync()

    def remove(self, recording):
        super(RPCDevice, self).remove(recording)
        # update recordings at the remote application
        self.sync()

    @kaa.coroutine(policy=kaa.POLICY_SYNCHRONIZED)
    def sync(self):
        """
        Check the internal list of recordings and add or remove them from
        the recorder.
        """
        for remote in self.recordings[:]:
            if remote.id is None and not remote.valid:
                # remove it from the list, looks like the recording
                # was already removed and not yet scheduled
                self.recordings.remove(remote)
                continue
            if remote.id is None:
                # add the recording
                remote.id = (yield self.rpc('schedule',
                    remote.channel, remote.start, remote.stop, remote.url))
                continue
            if not remote.valid:
                # remove the recording
                self.recordings.remove(remote)
                yield self.rpc('remove', remote.id)

    def create_fxd(self, filename, content):
        return self.rpc('create_fxd', filename, content)

    @kaa.rpc.expose()
    def started(self, id):
        for remote in self.recordings[:]:
            if remote.id == id:
                remote.started()

    @kaa.rpc.expose()
    def stopped(self, id):
        for remote in self.recordings[:]:
            if remote.id == id:
                remote.stopped()

    @kaa.rpc.expose()
    def epg(self, (backend, data)):
        kaa.epg.update(backend, data)
