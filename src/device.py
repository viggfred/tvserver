# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# device.py - base class for tvserver plugins
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
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

__all__ = [ 'signals', 'get_device', 'add_device', 'remove_device', 'TVDevice' ]

# python imports
import os
import sys
import logging

# kaa imports
import kaa
import kaa.epg
from kaa.utils import property, utc2localtime

# record imports
from config import config

# get logging object
log = logging.getLogger('tvserver')

# signals for this module
signals = { 'changed': kaa.Signal(),
            'start-recording': kaa.Signal(),
            'stop-recording': kaa.Signal()
          }

_devices = []
_channel = {}

def get_device(channel):
    return _channel.get(channel)

def get_devices():
    return _devices

def add_device(device):
    _devices.append(device)
    _rebuild_channels_dict()
    signals['changed'].emit()

def remove_device(device):
    _devices.remove(device)
    _rebuild_channels_dict()
    signals['changed'].emit()

def _rebuild_channels_dict():
    global _channel
    _channel = {}
    for device in _devices:
        for multiplex in device.multiplexes:
            for channel in multiplex:
                if not channel in _channel:
                    _channel[channel] = device
                elif _channel[channel].rating < device.rating:
                    _channel[channel] = device


class RecordingWrapper(object):
    """
    Wrapper for recordings to add some information from the device
    """
    def __init__(self, recording, channel, start, stop):
        self.recording = recording
        self.channel = channel
        self.start = start
        self.stop = stop
        self.id = None
        self.valid = True
        self.url = recording.url

    def started(self):
        signals['start-recording'].emit(self.recording)

    def stopped(self):
        signals['stop-recording'].emit(self.recording)


class TVDevice(object):
    """
    TV Device
    """
    def __init__(self, name, priority, multiplexes, capabilities):
        self.name = name
        self.multiplexes = multiplexes
        self.rating = priority
        self.recordings = []
        self.capabilities = capabilities

    def _normalize_name(self, name):
        return kaa.unicode_to_str(name.replace('.', '').replace(' ', '')).upper().strip()

    def _get_epg_channel(self, name):
        """
        Try to guess EPG name based on given device channel name
        """
        # step 1, try tuner_id
        channel = kaa.epg.guide.get_channel_by_tuner_id(name)
        if channel:
            return channel.name
        # step 2, try name
        channel = kaa.epg.guide.get_channel(name)
        if channel:
            return channel.name
        # Now we start the ugly part of guessing
        # maybe the name is a little bit different
        name = self._normalize_name(name)
        for channel in kaa.epg.guide.get_channels():
            if self._normalize_name(channel.name) == name:
                return channel.name
        return None

    @property
    def multiplexes(self):
        return self.__multiplexes

    @multiplexes.setter
    def multiplexes(self, multiplexes):
        self.__multiplexes = []
        self.channel_mapping = {}
        for multiplex in multiplexes:
            epg_multiplex = []
            for ext_channel in multiplex:
                epg_channel = self._get_epg_channel(ext_channel)
                if not epg_channel:
                    log.error('unable to find %s', ext_channel)
                    epg_channel = ext_channel
                self.channel_mapping[ext_channel] = epg_channel
                epg_multiplex.append(epg_channel)
            self.__multiplexes.append(epg_multiplex)

    @property
    def current_multiplexes(self):
        return self.__multiplexes

    def schedule(self, recording, start, stop):
        """
        Add a recording.
        """
        channel = self.channel_mapping[recording.channel]
        wrapper = RecordingWrapper(recording, channel, start, stop)
        self.recordings.append(wrapper)

    def remove(self, recording):
        """
        Remove a recording
        """
        for wrapper in self.recordings:
            if wrapper.recording == recording:
                wrapper.valid = False

    def create_fxd(self, filename, content):
        pass

    def __repr__(self):
        return '<TVDevice %s>' % (self.name)
