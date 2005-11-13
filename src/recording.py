# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# recording.py -
# -----------------------------------------------------------------------------
# $Id$
#
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

__all__ = [ 'Recording' ]

# python imports
import time
import copy
import re
import logging
import os

# freevo imports
from freevo import fxdparser
# FIXME: from util.fxdimdb import FxdImdb, makeVideo

# record imports
import config
from record_types import *

# get logging object
log = logging.getLogger('record')

def _int2time(i):
    """
    Helper function to create a time string from an int.
    """
    return time.strftime('%Y%m%d.%H:%M', time.localtime(i))


def _time2int(s):
    """
    Helper function to create an int from a string created by _int2time
    """
    return int(time.mktime(time.strptime(s, '%Y%m%d.%H:%M')))


class Recording(object):
    """
    Base class for a recording.
    """
    NEXT_ID = 0
    
    def __init__(self, name = 'unknown', channel = 'unknown',
                 priority = 0, start = 0, stop = 0, info = {},
                 status = SCHEDULED ):

        self.id       = Recording.NEXT_ID
        Recording.NEXT_ID += 1
        
        self.name     = name
        self.channel  = channel
        self.priority = priority
        self.start    = start
        self.stop     = stop
        self.status   = status
        self.info     = {}

        self.subtitle    = ''
        self.episode     = ''
        self.description = ''
        self.url         = ''
        self.fxdname     = ''

        # recorder where the recording is scheduled
        self.scheduled_recorder = None
        self.scheduled_start    = 0
        self.scheduled_stop     = 0
        
        self.start_padding = config.RECORD_START_PADDING
        self.stop_padding  = config.RECORD_STOP_PADDING
        for i in info:
            if i == 'subtitle':
                self.subtitle = Unicode(info[i])
            elif i == 'description':
                self.description = Unicode(info[i])
            elif i == 'url':
                self.url = String(info[i])
            elif i == 'start-padding':
                self.start_padding = int(info[i])
            elif i == 'stop-padding':
                self.stop_padding = int(info[i])
            else:
                self.info[i] = Unicode(info[i])
        self.recorder = None
        self.respect_start_padding = True
        self.respect_stop_padding = True


    def short_list(self):
        """
        Return a short list with informations about the recording.
        """
        return self.id, self.channel, self.priority, self.start, \
               self.stop, self.status


    def long_list(self):
        """
        Return a long list with every information about the recording.
        """
        info = copy.copy(self.info)
        if self.subtitle:
            info['subtitle'] = self.subtitle
        if self.episode:
            info['episode'] = self.episode
        if self.url:
            info['url'] = Unicode(self.url)
        if self.description:
            info['description'] = Unicode(self.description)
        return self.id, self.name, self.channel, self.priority, self.start, \
               self.stop, self.status, self.start_padding, self.stop_padding, \
               info


    def parse_fxd(self, parser, node):
        """
        Parse informations from a fxd node and set the internal variables.
        """
        for child in node.children:
            for var in ('name', 'channel', 'status', 'subtitle', 'fxdname',
                        'episode', 'description'):
                if child.name == var:
                    setattr(self, var, parser.gettext(child))
            if child.name == 'url':
                self.url = String(parser.gettext(child))
            if child.name == 'priority':
                self.priority = int(parser.gettext(child))
            if child.name == 'padding':
                self.start_padding = int(parser.getattr(child, 'start'))
                self.stop_padding  = int(parser.getattr(child, 'stop'))
            if child.name == 'timer':
                self.start = _time2int(parser.getattr(child, 'start'))
                self.stop  = _time2int(parser.getattr(child, 'stop'))
        parser.parse_info(node, self)
        if self.status == 'recording':
            log.warning('recording in status \'recording\'')
            # Oops, we are in 'recording' status and this was saved.
            # That means we are stopped while recording, set status to
            # missed
            self.status = 'missed'

        
    def __str__(self):
        """
        A simple string representation for a recording for debugging in the
        recordserver.
        """
        channel = self.channel
        if len(channel) > 10:
            channel = channel[:10]
        diff = (self.stop - self.start) / 60
        name = self.name
        if len(name) > 23:
            name = name[:20] + u'...'
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
            
        return '%3d %10s %-25s %4d %s-%s %2s %2s %s' % \
               (self.id, String(channel), String(name),
                self.priority, _int2time(self.start)[4:],
                _int2time(self.stop)[9:], start_padding,
                stop_padding, String(status))


    def __fxd__(self, fxd):
        """
        Dump informations about the recording in a fxd file node.
        """
        node = fxdparser.XMLnode('recording', [ ('id', self.id ) ] )
        for var in ('name', 'channel', 'priority', 'url', 'status',
                    'subtitle', 'fxdname', 'episode', 'description'):
            if getattr(self, var):
                subnode = fxdparser.XMLnode(var, [],
                                            Unicode(getattr(self, var)) )
                fxd.add(subnode, node)
        timer = fxdparser.XMLnode('timer', [ ('start', _int2time(self.start)),
                                             ('stop', _int2time(self.stop)) ])
        fxd.add(timer, node)
        padding = fxdparser.XMLnode('padding', [ ('start', self.start_padding),
                                                 ('stop', self.stop_padding) ])
        fxd.add(padding, node)
        info = fxdparser.XMLnode('info')
        for i in self.info:
            subnode = fxdparser.XMLnode(i, [], Unicode(self.info[i]) )
            fxd.add(subnode, info)
        fxd.add(info, node)
        return node


    def __cmp__(self, obj):
        """
        Compare basic informations between Recording objects
        """
        if not isinstance(obj, Recording):
            return True
        return self.name != obj.name or self.channel != obj.channel or \
               self.start != obj.start or self.stop != obj.stop


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

        if self.scheduled_recorder == recorder and \
               self.scheduled_start == start and \
               (self.scheduled_stop == stop or \
                self.status == RECORDING):
            # no update
            return
            
        if self.scheduled_recorder:
            self.scheduled_recorder.remove(self)
        self.scheduled_recorder = recorder
        self.scheduled_start    = start
        self.scheduled_stop     = stop
        log.info('schedule %s on %s' % (self.name, recorder))
        recorder.record(self, start, stop)


    def remove(self):
        """
        Remove from scheduled recorder.
        """
        if self.scheduled_recorder:
            self.scheduled_recorder.remove(self)
        self.scheduled_recorder = None

            
    def create_fxd(self):
        """
        Create a fxd file for the recording.
        """
        if not self.url.startswith('file:'):
            return

        # FIXME:
        return
        
        filename = self.url[5:]

        fxd = FxdImdb()
        (filebase, fileext) = os.path.splitext(filename)
        fxd.setFxdFile(filebase, overwrite = True)

        video = makeVideo('file', 'f1', os.path.basename(filename))
        fxd.setVideo(video)
        if self.episode:
            fxd.info['episode'] = fxd.str2XML(self.episode)
            if self.subtitle:
                fxd.info['subtitle'] = fxd.str2XML(self.subtitle)
        elif self.subtitle:
            fxd.info['tagline'] = fxd.str2XML(self.subtitle)
        if self.description:
            fxd.info['plot'] = fxd.str2XML(self.description)
        for i in self.info:
            fxd.info[i] = fxd.str2XML(self.info[i])

        fxd.info['runtime'] = '%s min.' % int((self.stop - self.start) / 60)
        fxd.info['record-start'] = str(int(time.time()))
        fxd.info['record-stop'] = str(self.stop + self.stop_padding)
        fxd.info['year'] = time.strftime('%m-%d %H:%M', time.localtime(self.start))
        if self.fxdname:
            fxd.title = self.fxdname
        else:
            fxd.title = self.name
        fxd.writeFxd()
