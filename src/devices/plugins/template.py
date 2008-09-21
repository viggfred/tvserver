# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# template.py - Plugin template
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

__all__ = [ 'PluginTemplate' ]

# python imports
import time
import logging
import os

# kaa imports
import kaa
from kaa.utils import property

# tvdev imports
from ..system import config

# get logging object
log = logging.getLogger('tvdev')

class Schedule(object):
    __next = 0

    def __init__(self, device, channel, start, stop, url):
        self.device = device
        self.channel = channel
        self.start = start
        self.stop = stop
        self.url = url
        self.rec_id = None
        self.id = Schedule.__next
        Schedule.__next += 1
        # internal timer
        self.timer = {
            'start': kaa.OneShotTimer(self._start),
            'stop': kaa.OneShotTimer(self._stop)
        }
        self._schedule()

    @kaa.coroutine()
    def abort(self):
        log.info('abort schedule %s' % self.id)
        for t in self.timer.values():
            if t.active:
                t.stop()
        if self.rec_id is not None:
            yield self._stop()

    def _schedule(self):
        """
        Schedule timer for recording.
        """
        if self.rec_id is None:
            # not started yet
            wait = int(max(0, self.start - time.time()))
            log.info('start recording %s in %s seconds' % (self.id, wait))
            self.timer['start'].start(wait)
        wait = int(max(0, self.stop - time.time()))
        log.info('stop recording %s in %s seconds' % (self.id, wait))
        self.timer['stop'].start(wait)

    @kaa.coroutine()
    def _start(self):
        """
        Callback to start the recording.
        """
        log.info('start recording %s' % self.id)
        result = self.device.start(self.channel, self.url)
        if isinstance(result, kaa.InProgress):
            result = yield result
        self.rec_id = result
        self.device.signals['started'].emit(self.id)

    @kaa.coroutine()
    def _stop(self):
        """
        Callback to stop the recording.
        """
        if self.rec_id is None:
            # ignore, already dead
            log.info('recording %s already dead' % self.id)
            yield False
        log.info('stop recording %s' % self.id)
        result = self.device.stop(self.rec_id)
        if isinstance(result, kaa.InProgress):
            yield result
        self.rec_id = None
        self.device.signals['stopped'].emit(self.id)


class PluginTemplate(object):
    """
    Template for tvdev plugins. A plugin must provide a start and stop function
    or override schedule and remove. Once the plugin is initialized it must set
    self.initialized. This can be done directly in __init__ or in case a coroutine
    runs in __init__ at the end of that coroutine. A plugin should also set its
    capabilities. Possible capabilities are epg (plugin get receive an epg),
    streaming (plugin supports streaming to udp:urls) and multiple (plugin can
    record multiple recordings on the same frequency).
    """
    capabilities = []

    def __init__(self, config):
        self.signals = kaa.Signals('started', 'stopped')
        self.config = config
        self.multiplexes = []
        self._schedule_id = 0
        self.__initialized = kaa.InProgress()
        self.schedules = {}

    def schedule(self, channel, start, stop, url):
        """
        Schedule a recording on this device. A plugin may override this function
        and start a scanning for VPS or something similar. The default behaviour
        is to create a Schedule object which will call self.start and self.stop.

        @param channel: Channel name as defined in the multiplex
        @param start: start time in local time
        @param stop: stop time in local time
        @param url: file:// or udp:// url
        @returns unique schedule id
        """
        if url.find('://') == -1:
            url = 'file:' + os.path.join(config.directory, url)
        if url.startswith('file:'):
            url = url + '.' + self.config.suffix
            # check if target dir exists
            d = os.path.dirname(url[5:])
            if not os.path.isdir(d):
                os.makedirs(d)
        s = Schedule(self, channel, start, stop, url)
        self.schedules[s.id] = s
        return s.id

    def remove(self, id):
        """
        Remove a recording. If the recording is currently running it is stopped.

        @param id: schedule id
        """
        s = self.schedules.pop(id, None)
        if s is None:
            log.error('schedule %s undefined', id)
            return
        s.abort()

    def start(self, channel, url):
        """
        Start recording the channel and store to the given url. This function is
        called by the Schedule object and must be implemented in the plugin if
        it does not redefine self.schedule and self.remove.

        @param channel: Channel name as defined in the multiplex
        @param url: file:// or udp:// url
        @returns unique recording id
        """
        raise NotImplemented

    def stop(self, id):
        """
        Stop a running recording. This function is called by the Schedule object
        and must be implemented in the plugin if it does not redefine self.schedule
        and self.remove.

        @param id: recording id
        """
        raise NotImplemented

    @property
    def priority(self):
        return int(self.config.priority)

    @property
    def name(self):
        return self.config.device

    @property
    def initialized(self):
        return self.__initialized

    @initialized.setter
    def initialized(self, dummy):
        self.__initialized.finish(dummy)
