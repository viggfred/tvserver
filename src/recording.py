# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# recording.py -
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Freevo - A Home Theater PC framework
# Copyright (C) 2004-2008 Dirk Meyer, et al.
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

__all__ = [ 'Recording' ]

# python imports
import time
import copy
import re
import logging
import os

# kaa imports
import kaa

# freevo imports
import freevo.fxdparser

# record imports
from config import config
from record_types import *

# get logging object
log = logging.getLogger('tvserver')

def _time_int2str(i):
    """
    Helper function to create a time string from an int. The timestring
    contains the timezone as integer, e.g. CEST == +0200. The input
    time must be in UTC
    """
    adjust = time.timezone
    if time.daylight:
        adjust = time.altzone
    s = time.localtime(i - adjust)
    if adjust < 0:
        adjust = '+%04d' % (-adjust / 36)
    else:
        adjust = '-%04d' % (adjust / 36)
    return time.strftime('%Y%m%d%H%M', s) + ' ' + adjust

def _time_str2int(s):
    """
    Helper function to create an int from a string created by _time_int2str.
    The returned time in seconds is in UTC.
    """
    sec = int(time.mktime(time.strptime(s.split()[0], '%Y%m%d%H%M')))
    return sec - int(s.split()[1]) * 36


class Recording(object):
    """
    Base class for a recording.
    """
    NEXT_ID = 0

    def __init__(self, name='unknown', channel='unknown', priority=0, start=0, stop=0,
                 node=None, info={} ):
        self.id = Recording.NEXT_ID
        Recording.NEXT_ID += 1
        self.name = name
        self.channel = channel
        self.priority = priority
        self.start = start
        self.stop = stop
        # optional information
        self.subtitle = ''
        self.episode = ''
        self.description = ''
        self.url = ''
        self.fxdname = ''
        self.info = {}
        self.status = CONFLICT
        self.start_padding = config.recording.start_padding
        self.stop_padding  = config.recording.stop_padding
        self.respect_start_padding = True
        self.respect_stop_padding = True
        for key, value in info.items():
            if key in ('subtitle', 'description') and value:
                setattr(self, key, kaa.str_to_unicode(value))
            elif key == 'url' and value:
                self.url = kaa.unicode_to_str(value)
            elif key in ('start-padding', 'stop_padding'):
                setattr(self, key, int(value))
            elif value:
                self.info[key] = kaa.str_to_unicode(value)
        # recorder where the tvserver wants to schedule the recording
        self.recorder = None
        # external recorder where the recording is currently scheduled
        self._scheduled_recorder = None
        if node:
            self._add_xml_data(node)

    def _add_xml_data(self, node):
        """
        Parse informations from a fxd node and set the internal variables.
        """
        # Parse informations from a fxd node and set the internal variables.
        for child in node.children:
            for var in ('name', 'channel', 'status', 'subtitle', 'fxdname',
                        'episode', 'description'):
                if child.name == var:
                    setattr(self, var, child.content)
            if child.name == 'url':
                self.url = kaa.unicode_to_str(child.content)
            if child.name == 'priority':
                self.priority = int(child.content)
            if child.name == 'padding':
                self.start_padding = int(child.getattr('start'))
                self.stop_padding  = int(child.getattr('stop'))
            if child.name == 'timer':
                self.start = _time_str2int(child.getattr('start'))
                self.stop  = _time_str2int(child.getattr('stop'))
            if child.name == 'info':
                for info in child.children:
                    self.info[info.name] = info.content

    def schedule(self, recorder):
        """
        Schedule the recording on the given recorder
        """
        start = self.start
        if self.respect_start_padding:
            start -= self.start_padding
        stop = self.stop
        if self.respect_stop_padding:
            stop += self.stop_padding
        if self._scheduled_recorder == recorder and \
               self._scheduled_start == start and \
               (self._scheduled_stop == stop or \
                self.status == RECORDING):
            # no update
            return
        if self._scheduled_recorder:
            self._scheduled_recorder.remove(self)
        self._scheduled_recorder = recorder
        self._scheduled_start = start
        self._scheduled_stop = stop
        log.info('schedule %s on %s' % (self.name, recorder))
        recorder.record(self, start, stop)

    def remove(self):
        """
        Remove from scheduled recorder.
        """
        if self._scheduled_recorder:
            self._scheduled_recorder.remove(self)
        self._scheduled_recorder = None

    def create_fxd(self):
        """
        Create a fxd file for the recording.
        """
        if not self.url.startswith('file:'):
            return
        # create root node
        fxd = freevo.fxdparser.Document()
        # create <movie> with title
        title = self.name
        if self.fxdname:
            fxd.title = self.fxdname
        movie = fxd.add_child('movie', title=title)
        # add <video> to movie
        video = movie.add_child('video')
        video.add_child('file', os.path.basename(self.url[5:]), id='f1')
        # add <info> to movie
        info = movie.add_child('info')
        if self.episode:
            info.add_child('episode', self.episode)
            if self.subtitle:
                info.add_child('subtitle', self.subtitle)
        elif self.subtitle:
            info.add_child('tagline', self.subtitle)
        if self.description:
            info.add_child('plot', self.description)
        for key, value in self.info.items():
            info.add_child(key, value)
        info.add_child('runtime', '%s min.' % int((self.stop - self.start) / 60))
        info.add_child('record-start', int(time.time()))
        info.add_child('record-stop', self.stop + self.stop_padding)
        info.add_child('year', time.strftime('%m-%d %H:%M', time.localtime(self.start)))
        # and save file
        fxd.save(os.path.splitext(self.url[5:])[0] + '.fxd')

    def __str__(self):
        """
        A simple string representation for a recording for debugging in the
        tvserver.
        """
        channel = self.channel
        if len(channel) > 10:
            channel = channel[:10]
        diff = (self.stop - self.start) / 60
        name = self.name
        if len(name) > 17:
            name = name[:14] + u'...'
        name = u'"' + name + u'"'
        status = self.status
        if status == 'scheduled' and self.recorder:
            status = self.recorder.device
        if self.respect_start_padding:
            start_padding = int(self.start_padding/60)
        else:
            start_padding = 0
        if self.respect_stop_padding:
            stop_padding = int(self.stop_padding/60)
        else:
            stop_padding = 0
        return '%3d %10s %-19s %4d %s/%s-%s %2s %2s %s' % \
               (self.id, kaa.unicode_to_str(channel), kaa.unicode_to_str(name),
                self.priority, _time_int2str(self.start)[4:8],
                _time_int2str(self.start)[8:-6], _time_int2str(self.stop)[8:],
                start_padding, stop_padding, kaa.unicode_to_str(status))

    def to_list(self):
        """
        Return a long list with every information about the recording.
        """
        info = copy.copy(self.info)
        if self.subtitle:
            info['subtitle'] = self.subtitle
        if self.episode:
            info['episode'] = self.episode
        if self.url:
            info['url'] = kaa.str_to_unicode(self.url)
        if self.description:
            info['description'] = kaa.str_to_unicode(self.description)
        return self.id, self.name, self.channel, self.priority, self.start, \
               self.stop, self.status, int(self.start_padding), \
               int(self.stop_padding), info

    def to_xml(self, root):
        """
        Dump informations about the recording in a fxd file node.
        """
        node = root.add_child('recording', id=self.id)
        for var in ('name', 'channel', 'priority', 'status',
                    'subtitle', 'fxdname', 'episode', 'description'):
            if getattr(self, var):
                node.add_child(var, getattr(self, var))
        if self.url:
            node.add_child('url', kaa.str_to_unicode(self.url))

        node.add_child('timer', start=_time_int2str(self.start),
                       stop=_time_int2str(self.stop))
        node.add_child('padding', start=self.start_padding, stop=self.stop_padding)

        info = node.add_child('info')
        for key, value in self.info.items():
            info.add_child(key, value)
        return node

    def __cmp__(self, obj):
        """
        Compare basic informations between Recording objects
        """
        if not isinstance(obj, Recording):
            return True
        return self.name != obj.name or self.channel != obj.channel or \
               self.start != obj.start or self.stop != obj.stop
