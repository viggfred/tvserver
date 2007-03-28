# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# favorite.py -
# -----------------------------------------------------------------------------
# $Id$
#
# Example for favorite in tvschedule.fxd
#
# <favorite id="1">
#     <name>Genial daneben - Die Comedy-Arena</name>
#     <priority>50</priority>
#     <days>5 6</days>
#     <channels>
#         <channel>SAT1</channel>
#     </channels>
#     <times>
#         <start>20:10-20:20</start>
#         <start>21:00-23:50</start>
#     </times>
#     <padding start="0" stop="0"/>
# </favorite>
#
# -----------------------------------------------------------------------------
# Freevo - A Home Theater PC framework
# Copyright (C) 2005-2007 Dirk Meyer, et al.
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
import re
import time
import logging

# kaa imports
from kaa.strutils import unicode_to_str, str_to_unicode

# record imports
from config import config
from record_types import *

# get logging object
log = logging.getLogger('record')


# internal regexp for time format
_time_re = re.compile('([0-9]*):([0-9]*)-([0-9]*):([0-9]*)')

class Favorite(object):
    """
    Base class for a favorite.
    """
    NEXT_ID = 0

    def __init__(self, name = 'unknown', channels = [],
                 priority = 0, days = [], times = [], once = False,
                 substring = False, node=None):
        self.id        = Favorite.NEXT_ID
        Favorite.NEXT_ID += 1

        self.name      = name
        self.channels  = channels
        self.priority  = priority
        self.days      = days
        self.times     = []
        self.url       = ''
        self.fxdname   = ''
        self.once      = once
        self.substring = substring
        for t in times:
            m = _time_re.match(t).groups()
            start = int(m[0])*100 + int(m[1])
            stop  = int(m[2])*100 + int(m[3])
            self.times.append((start, stop))
        self.start_padding = config.record.start_padding
        self.stop_padding  = config.record.stop_padding

        if not node:
            return

        # Parse informations from a fxd node and set the internal variables.
        for child in node:
            for var in ('name', 'fxdname'):
                if child.name == var:
                    setattr(self, var, child.content)
            if child.name == 'url':
                self.url = unicode_to_str(child.content)
            if child.name == 'once':
                self.once = True
            if child.name == 'substring':
                self.substring = True
            if child.name == 'channels':
                self.channels = []
                for c in child.children:
                    self.channels.append(c.content)
            if child.name == 'days':
                self.days = []
                for v in child.content.split(' '):
                    self.days.append(int(v))
            if child.name == 'times':
                self.times = []
                for t in child.children:
                    m = _time_re.match(t.content).groups()
                    start = int(m[0])*100 + int(m[1])
                    stop  = int(m[2])*100 + int(m[3])
                    self.times.append((start, stop))
            if child.name == 'padding':
                self.start_padding = int(child.getattr('start'))
                self.stop_padding  = int(child.getattr('stop'))
            if child.name == 'priority':
                setattr(self, 'priority', int(child.content))


    def short_list(self):
        """
        Return a short list with informations about the favorite.
        """
        return self.id, self.name, self.priority


    def long_list(self):
        """
        Return a long list with every information about the favorite.
        """
        return self.id, self.name, self.channels, self.priority, self.days, \
               self.times, self.once, self.substring


    def match(self, name, channel, start):
        """
        Return True if name, channel and start match this favorite.
        """
        if str_to_unicode(name.lower()) != self.name.lower() and not self.substring:
            return False
        if name.lower().find(self.name.lower()) == -1:
            return False
        if not channel in self.channels:
            return False
        timestruct = time.localtime(start)
        if not int(time.strftime('%w', timestruct)) in self.days:
            return False
        stime = int(timestruct[3]) * 100 + int(timestruct[4])
        for t1, t2 in self.times:
            if stime >= t1 and stime <= t2:
                return True
        return False


    def __fill_template(self, rec, text, is_url):
        """
        Fill template like url and fxdname from the favorite to something
        specific for the recording.
        """
        t = time.strftime('%Y %m %d %H:%M', time.localtime(rec.start))
        year, month, day, hour_min = t.split(' ')
        options = { 'title'    : rec.name,
                    'year'     : year,
                    'month'    : month,
                    'day'      : day,
                    'time'     : hour_min,
                    'episode'  : rec.episode,
                    'subtitle' : rec.subtitle }
        if is_url:
            # url is string and an extra '/' is not allowed. Replace '/'
            # with '_' and also convert all args to string.
            for o in options:
                options[o] = unicode_to_str(options[o]).replace('/', '_')
        for pattern in re.findall('%\([a-z]*\)', text):
            if not str(pattern[2:-1]) in options:
                options[pattern[2:-1]] = pattern
        text = re.sub('%\([a-z]*\)', lambda x: x.group(0)+'s', text)
        text = text % options
        return text.rstrip(' -_:')


    def add_data(self, rec):
        """
        Add additional data from the favorite to the recording
        """
        rec.favorite      = True
        rec.start_padding = self.start_padding
        rec.stop_padding  = self.stop_padding
        rec.fxdname       = self.fxdname
        if self.url:
            # add url template to recording
            try:
                rec.url = unicode_to_str(self.__fill_template(rec, self.url, True) + '.suffix')
            except Exception, e:
                log.exception('Error setting recording url')
                rec.url = ''
        if self.fxdname:
            # add fxd name template to recording
            try:
                rec.fxdname = self.__fill_template(rec, self.fxdname, False)
            except Exception, e:
                log.exception('Error setting recording fxd name:')
                rec.fxdname = ''
        return True


    def __str__(self):
        """
        A simple string representation for a favorite for debugging in the
        recordserver.
        """
        name = self.name
        if len(name) > 30:
            name = name[:30] + u'...'
        name = u'"' + name + u'"'
        if self.once:
            once = '(schedule once)'
        else:
            once = ''
        if self.substring:
            substring = '(substring matching)'
        else:
            substring = '(exact matching)'
        return '%3d %-35s %4d %s %s' % \
               (self.id, unicode_to_str(name), self.priority, once, substring)


    def toxml(self, root):
        """
        Dump informations about the favorite in a fxd file node.
        """
        node = root.add_child('favorite', id=self.id)
        for var in ('name', 'priority', 'url', 'fxdname'):
            if getattr(self, var):
                node.add_child(var, getattr(self, var))
        node.add_child('days', ' '.join([ str(d) for d in self.days]))
        channels = node.add_child('channels')
        for chan in self.channels:
            channels.add_child('channel', chan)
        times = node.add_child('times')
        for t in self.times:
            times.add_child('start', '%02d:%02d-%02d:%02d' % \
                            (t[0] / 100, t[0] % 100, t[1] / 100, t[1] % 100))
        if self.once:
            node.add_child('once')
        if self.substring:
            node.add_child('substring')
        node.add_child('padding', start=self.start_padding, stop=self.stop_padding)
        return node


    def __cmp__(self, obj):
        """
        Compare basic informations between Favorite objects
        """
        if not isinstance(obj, Favorite):
            return True
        return self.name != obj.name or self.channels != obj.channels or \
               self.days != obj.days or self.times != obj.times

