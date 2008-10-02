# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# dvbstreamer.py - DVBStreamer based Plugin
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
import time
import logging
import uuid

# kaa imports
import kaa

# tvdev imports
from template import PluginTemplate

# get logging object
log = logging.getLogger('dvbstreamer')


class Plugin(PluginTemplate):

    capabilities = [ 'streaming', 'multiple' ]

    def __init__(self, config):
        super(Plugin, self).__init__(config)
        log.debug('new controller: adapter=%s' % config.adapter)
        self._data = ''
        self._callback = None
        self._requests = []
        self.dvbstreamer = kaa.Process('dvbstreamer')
        self.dvbstreamer.signals['raw-stdout'].connect(self._read)
        self.dvbstreamer.signals['completed'].connect(self._dvbstreamer_died)
        self.ready = False
        self._current_multiplex = None
        self._dvbstreamer_init()

    @kaa.coroutine()
    def _dvbstreamer_init(self):
        """
        DVBStreamer>lsservices -id
        2114.0d01.0002 : arte
        2114.0d01.0003 : Phoenix
        2114.0d01.00a1 : rb TV
        2114.0d01.00a0 : Das Erste
        DVBStreamer>serviceinfo 2114.0d01.00a0
        Name                : Das Erste
        Provider            : ARD
        Type                : Digital TV
        Conditional Access? : Free to Air
        ID                  : 2114.0d01.00a0
        Multiplex UID       : 1220133478
        Source              : 0x00a0
        Default Authority   : (null)
        PMT PID             : 0x0104
        Version             : 2
        """
        mplex = {}
        self.channels = {}
        for service in (yield self.rpc('lsservices -id')).splitlines():
            service = service.strip()
            if not service:
                continue
            service_id, service_name = service.split(' : ',1)
            info = yield self.rpc('serviceinfo %s' % service_id)
            service = {}
            for line in info.split('\n'):
                if not line.find(':') > 0:
                    continue
                attr, value = line.split(':', 1)
                service[attr.strip()] = value.strip()
            if service['Name'] in self.channels:
                continue
            if not service.get('Multiplex UID'):
                # service id contains multiplex uid
                service['Multiplex UID'] = '.'.join(service_id.split('.')[0:1])
            if not service['Multiplex UID'] in mplex:
                mplex[service['Multiplex UID']] = []
            mplex[service['Multiplex UID']].append(service['Name'])
            self.channels[service['Name']] = service
        self.multiplexes = mplex.values()
        self.initialized = True

    def _dvbstreamer_died(self, data):
        log.error('dvbstreamer died! exitcode=%s' % data)

    def _read(self, data):
        self._data += data
        if self._data.find('DVBStreamer>') >= 0:
            result = self._data[:self._data.find('DVBStreamer>')]
            if self._callback:
                self._callback.finish(result)
                self._callback = None
            if self._requests:
                cmd, self._callback = self._requests.pop(0)
                self.dvbstreamer.write(cmd)
            else:
                self.ready = True
            self._data = self._data[self._data.find('DVBStreamer>')+12:]

    @kaa.coroutine()
    def rpc(self, cmd):
        log.info('rpc %s', cmd)
        if self.dvbstreamer.stopping:
            yield self.dvbstreamer.in_progress
        if not self.dvbstreamer.in_progress:
            self.dvbstreamer.start(['-a', self.config.adapter])
        async = kaa.InProgress()
        if self.ready:
            self.ready = False
            self._callback = async
            self.dvbstreamer.write(cmd + '\n')
        else:
            self._requests.append((cmd + '\n', async))
        yield (yield async)

    @kaa.coroutine()
    def start(self, channel, url):
        scheduling_id = str(uuid.uuid4())
        channel = self.channels[channel]
        # switch to new multiplex and service
        if self._current_multiplex != channel['Multiplex UID']:
            self._current_multiplex = channel['Multiplex UID']
            log.info('selecting new multiplex="%s"' % channel['ID'])
            yield self.rpc('select %s' % channel['ID'])
        # add service filter
        yield self.rpc('addsf %s %s' % (scheduling_id, url))
        yield self.rpc('setsf %s %s' % (scheduling_id, channel['ID']))
        yield scheduling_id


    @kaa.coroutine()
    def stop(self, id):
        log.info('stopping recording %s' % id)
        yield self.rpc('setsfmrl %s null://' % id )
        yield self.rpc('rmsf %s' % id)
