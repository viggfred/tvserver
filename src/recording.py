# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# recording.py - Recording for the TVServer Client
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

__all__ = [ 'Recording', 'Recordings' ]

# python imports
from datetime import datetime

# kaa imports
import kaa
import kaa.dateutils

class Recording(object):
    """
    Recording object
    """
    def __init__(self, link, *args):
        self._link = link
        self._update(*args)

    def _update(self, *args):
        """
        Update recording based on event from tvserver or init
        """
        self.id, self.name, self.channel, self.priority, self.start_timestamp, self.stop_timestamp, \
                 self.status, self.start_padding, self.stop_padding, self.description = args
        # Timezone-aware datetime objects in the local timezone.
        self.start = datetime.fromtimestamp(self.start_timestamp, kaa.dateutils.local)
        self.stop = datetime.fromtimestamp(self.stop_timestamp, kaa.dateutils.local)

    def remove(self):
        """
        Remove the recording

        @returns: InProgress object
        """
        self._link.recording_remove(self.id)

    def __str__(self):
        if self.description.has_key('title') and self.description['title']:
            s = self.description['title']
        else:
            s = self.name
        if self.description.has_key('episode') and self.description['episode']:
            s += u' %s' % self.description['episode']
        if self.description.has_key('subtitle') and \
           self.description['subtitle']:
            s += u' - %s' % self.description['subtitle']
        return kaa.unicode_to_str(s)

    def __getitem__(self, key):
        if hasattr(self, key) and key != 'description':
            return getattr(self, key)
        if key == 'title':
            return self.description.get('title') or self.name
        if self.description.has_key(key):
            return self.description[key]
        raise AttributeError('no attribute %s in Recording' % key)

    def has_key(self, key):
        if hasattr(self, key) and key != 'description':
            return True
        if key == 'title':
            return True
        return self.description.has_key(key)


class Recordings(object):
    """
    List of Recordings
    """
    def __init__(self, link):
        self._link = link
        self._recordings = {}

    def _clear(self):
        """
        Clear the list
        """
        self._recordings = {}

    def _update(self, recordings):
        """
        Update list of recordings based on event from tvserver
        """
        for r in recordings:
            for key, v in self._recordings.items():
                if v.id == r[0]:
                    localr = self._recordings.pop(key)
                    localr._update(*r)
                    break
            else:
                localr = Recording(self._link, *r)
            key = '%s-%s-%s' % (localr.channel, localr.start, localr.stop)
            self._recordings[key] = localr

    def __iter__(self):
        """
        Iterate through the list of recordings
        """
        return self._recordings.values().__iter__()

    def schedule(self, name, channel, priority, start, stop, **info):
        """
        Schedule a recording

        @param name: name of the program
        @param channel: name of the channel
        @param start: start time in seconds since Epoch (UTC)
        @param stop: stop time in seconds since Epoch (UTC)
        @param info: additional information
        @returns: InProgress object
        """
        return self._link.recording_add(name, channel, priority, start, stop, **info)

    def remove(self, id):
        """
        Remove a recording

        @param id: id the the recording to be removed
        @returns: InProgress object
        """
        return self._link.recording_remove(id)

    def get(self, channel, start, stop):
        """
        Get the recording defined by the given channel and time

        @param channel: name of the channel
        @param start: start time in seconds since Epoch (UTC)
        @param stop: stop time in seconds since Epoch (UTC)
        """
        key = '%s-%s-%s' % (channel, start, stop)
        if key in self._recordings:
            return self._recordings[key]
        return None
