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
log = logging.getLogger('tvserver.device.dvbstreamer')


class Plugin(PluginTemplate):

    capabilities = [ 'streaming', 'multiple', 'epg' ]

    def __init__(self, config):
        super(Plugin, self).__init__(config)
        log.debug('new controller: adapter=%s' % config.adapter)
        self._data = ''
        self._callback = None
        self._requests = []
        self.dvbstreamer = kaa.Process('dvbstreamer')
        self.dvbstreamer.signals['raw-stdout'].connect(self._read)
        self.dvbstreamer.signals['completed'].connect(self._dvbstreamer_died)
        self._ready = False
        self._busy = True
        self._current_multiplex = None
        self._dvbstreamer_init()
        self._epg_counter = -1
        self._recordings = 0

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
        for service in (yield self._call('lsservices -id')).splitlines():
            service = service.strip()
            if not service:
                continue
            service_id, service_name = service.split(' : ',1)
            info = yield self._call('serviceinfo %s' % service_id)
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
        self.idle()

    def _dvbstreamer_died(self, data):
        log.info('dvbstreamer stopped')

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
                self._ready = True
            self._data = self._data[self._data.find('DVBStreamer>')+12:]

    @kaa.timed(60)
    def idle(self):
        self._epg_counter += 1
        if self._epg_counter < 0:
            # no need to scan again, check tuner status
            if not self._recordings and self.dvbstreamer.in_progress and \
                   not self.dvbstreamer.stopping:
                if self._busy:
                    # mark as not busy
                    self._busy = False
                else:
                    # shut down dvbstreamer, we do not need it
                    log.info('shut down dvbstreamer')
                    self.dvbstreamer.stop()
            return
        if self._recordings:
            # busy, wait a minute
            self._epg_counter = -1
            return
        if self._epg_counter >= len(self.multiplexes):
            # scan again in 3 hours
            self.signals['epg-update'].emit()
            self._epg_counter = - 3 * 60
            return
        channel = self.channels[self.multiplexes[self._epg_counter][0]]
        self._current_multiplex = channel['Multiplex UID']
        self._call('select %s' % channel['ID'])

    @kaa.coroutine()
    def _call(self, cmd):
        self._busy = True
        log.debug('cmd %s', cmd)
        if self.dvbstreamer.stopping:
            yield self.dvbstreamer.in_progress
        if not self.dvbstreamer.in_progress:
            # FIXME: this only works up to dvb9 but that should be enough
            self.dvbstreamer.start(['-a', self.config.adapter[-1]])
        async = kaa.InProgress()
        if self._ready:
            self._ready = False
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
            self._call('select %s' % channel['ID'])
        self._recordings += 1
        # add service filter
        yield self._call('addsf %s %s' % (scheduling_id, url))
        yield self._call('setsf %s %s' % (scheduling_id, channel['ID']))
        yield scheduling_id

    @kaa.coroutine()
    def stop(self, id):
        log.info('stopping recording %s' % id)
        self._recordings -= 1
        yield self._call('setsfmrl %s null://' % id )
        yield self._call('rmsf %s' % id)

    @kaa.coroutine()
    def epg(self):
        yield 'xmltv', (yield self._call('dumpxmltv'))
