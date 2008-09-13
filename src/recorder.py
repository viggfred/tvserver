# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# recorder.py - base class for recorder plugins
# -----------------------------------------------------------------------------
# $Id$
#
# TODO: Handle unknown channels by letting user record them even with no EPG
#       data.
#
# THIS CODE IS BROKEN
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

__all__ = [ 'signals', 'connect', 'get_recorder' ]

# python imports
import os
import sys
import time
import string
import copy
import logging

# kaa imports
import kaa
import kaa.epg

# record imports
from config import config
from record_types import *

# get logging object
log = logging.getLogger('record')

# internal 'unique' ids
UNKNOWN_ID  = -1

class RecorderList(object):
    def __init__(self):
        self.recorder = []
        self.best_recorder = {}

    def append(self, recorder):
        if not recorder in self.recorder:
            log.info('add %s' % recorder)
            self.recorder.append(recorder)
        self.check()

    def remove(self, recorder):
        if recorder in self.recorder:
            log.info('remove %s' % recorder)
            self.recorder.remove(recorder)
            self.check()

    def check(self):
        """
        Check all possible recorders.
        """
        # reset best recorder list
        self.best_recorder = {}
        for p in self.recorder:
            for l in p.current_bouquets:
                for c in l:
                    if not self.best_recorder.has_key(c):
                        self.best_recorder[c] = -1, None
                    if self.best_recorder[c][0] < p.rating:
                        self.best_recorder[c] = p.rating, p, p.device
        for c in self.best_recorder:
            self.best_recorder[c] = self.best_recorder[c][1]
        signals['changed'].emit()

    def __iter__(self):
        return self.recorder.__iter__()

    @kaa.coroutine()
    def FIXME_new_client(self, entity):
        """
        Update recorders on entity changes.
        """
        result = yield entity.rpc('home-theatre.device.list')
        if not result:
            log.error(result)
            return
        for device in result:
            Recorder(entity, self, device)

    def FIXME_recording_started_or_stopped(self, event):
        for r in self.recorder:
            if r.entity != event.source:
                continue
            for rec in r.recordings:
                if rec.id == event[0]:
                    break
            else:
                continue
            break
        else:
            # FIXME: the recording may be changed in the last second to
            # a different recorder
            log.error('unable to find recorder for event %s' % event)
            return True
        if event.name.endswith('started'):
            signals['start-recording'].emit(rec.recording)
        else:
            signals['stop-recording'].emit(rec.recording)
        return True


class RemoteRecording(object):
    """
    Wrapper for recordings to add 'id' and 'valid' for internal use inside
    the recorder.
    """
    def __init__(self, recording, start):
        self.recording = recording
        self.id = UNKNOWN_ID
        self.valid = True
        self.start = start


class Recorder(object):
    """
    External recorder
    """
    def __init__(self, entity, handler, device):
        self.type = 'recorder'
        # reference to the tvserver
        self.handler = handler
        self.entity = entity
        self.device = device
        self.name = '%s:%s' % (entity.addr['id'], device)
        self.recordings = []
        self.check_timer = kaa.OneShotTimer(self.check_recordings)
        self.entity.signals['lost-entity'].connect(self.lost_entity)
        self.rating = 0
        self.known_channels = {}
        self._describe()

    def __repr__(self):
        return '<Recorder for %s>' % (self.name)

    def lost_entity(self):
        log.info('%s lost entity' % self)
        self.handler.remove(self)

    def sys_exit(self):
        log.error('Unknown channels detected on device %s.' % self.device)
        log.error('Please check %s' % config.get_filename())
        log.error('Freevo guessed some settings, so maybe a new start will work\n')
        sys.exit(0)

    def normalize_name(self, name):
        return kaa.unicode_to_str(name.replace('.', '').replace(' ', '')).upper().strip()

    def add_channel(self, chan_obj, chan_id):
        if chan_obj.name in self.known_channels:
            # duplicate, skip it
            return
        chan_obj.tuner_id = chan_id
        self.known_channels[chan_obj.name] = chan_obj
        self.possible_bouquets[-1].append(chan_obj.name)

    @kaa.coroutine()
    def _describe(self):
        """
        """
        result = yield self.entity.rpc('home-theatre.device.describe', self.device)
        if not result:
            log.error(result)
            self.handler.remove(self)
            yield False
        self.possible_bouquets = []
        error = False
        guessing = False
        for bouquet in result[2]:
            self.possible_bouquets.append([])
            for channel in bouquet:
                # step 1, see config for override
                if channel in config.epg.mapping:
                    chan = yield kaa.epg.guide.get_channel(config.epg.mapping[channel])
                    if chan:
                        self.add_channel(chan, channel)
                        continue
                # step 2, try tuner_id
                chan = yield kaa.epg.guide.get_channel_by_tuner_id(channel)
                if not chan:
                    # step 3, try name
                    chan = yield kaa.epg.guide.get_channel(channel)
                if chan:
                    self.add_channel(chan, channel)
                    continue
                if channel in config.epg.mapping:
                    # Stop here. The channel is in the mapping list but not
                    # detected by the system. Before we do some bad guessing,
                    # just set the channel to a non epg channel
                    chan = yield kaa.epg.guide.new_channel(name=channel)
                    self.add_channel(chan, channel)
                    continue
                # Now we start the ugly part of guessing
                guessing = True
                found = False
                # maybe the name is a little bit different
                normchannel = self.normalize_name(channel)
                for c in (yield kaa.epg.guide.get_channels()):
                    if self.normalize_name(c.name) == normchannel:
                        self.add_channel(c, channel)
                        config.epg.mapping[channel] = c.name
                        found = True
                        break
                # TODO: also compare all tuner ids we have for a similar
                # name and also force harder by checking substrings
                if found:
                    continue
                # if we got this far that means there is nothing to connect
                # the channel reported by tvdev to one in the EPG
                if not channel in config.epg.mapping:
                    error = True
                    config.epg.mapping[channel] = ''
        if guessing:
            config.save()
        if error:
            kaa.OneShotTimer(self.sys_exit).start(1)
            return
        self.rating = result[1]
        self.update()

    def update(self):
        self.current_bouquets = self.possible_bouquets
        self.handler.append(self)

    def get_url(self, rec):
        """
        Return url (e.g. filename) for the given recording
        """
        if not rec.url:
            filename_array = { 'progname': kaa.unicode_to_str(rec.name),
                               'title'   : kaa.unicode_to_str(rec.subtitle) }
            filemask = config.record.filemask % filename_array
            filename = ''
            for letter in time.strftime(filemask, time.localtime(rec.start)):
                if letter in string.ascii_letters + string.digits:
                    filename += letter
                elif filename and filename[-1] != '_':
                    filename += '_'
            filename = filename.rstrip(' -_:') + '.mpg'
            filename = 'file:' + os.path.join(config.record.dir, filename)
        else:
            # check filename
            if rec.url.startswith('file:'):
                filename = os.path.join(config.record.dir, rec.url[5:])
                if filename.endswith('.suffix'):
                    filename = os.path.splitext(filename)[0] + '.mpg'
                filename = 'file:' + filename
        if filename.startswith('file:'):
            # check if target dir exists
            d = os.path.dirname(filename[5:])
            if not os.path.isdir(d):
                os.makedirs(d)
        return filename

    def record(self, recording, start, stop):
        """
        Add a recording.
        """
        self.recordings.append(RemoteRecording(recording, start))
        # update recordings at the remote application
        self.check_timer.start(0.1)

    def remove(self, recording):
        """
        Remove a recording
        """
        for remote in self.recordings:
            if remote.recording == recording:
                remote.valid = False
        # update recordings at the remote application
        self.check_timer.start(0.1)

    @kaa.coroutine(policy=kaa.POLICY_SYNCHRONIZED)
    def check_recordings(self):
        """
        Check the internal list of recordings and add or remove them from
        the recorder.
        """
        for remote in copy.copy(self.recordings):
            if not self.entity:
                # entity is gone
                log.info('%s: remove %s', self.name, remote.recording.name)
                self.recordings.remove(remote)
                continue
            if remote.id == UNKNOWN_ID and not remote.valid:
                # remove it from the list, looks like the recording
                # was already removed and not yet scheduled
                self.recordings.remove(remote)
                continue
            if remote.id == UNKNOWN_ID:
                # add the recording
                rec      = remote.recording
                channel  = self.known_channels[rec.channel].tuner_id
                filename = self.get_url(rec)
                rec.url  = filename
                log.info('%s: schedule %s', self.name, rec.name)
                result = yield self.entity.rpc(
                    'home-theatre.vdr.record', self.device, channel, remote.start,
                    rec.stop + rec.stop_padding, filename, ())
                if not result:
                    log.error(result)
                    self.handler.remove(self)
                    yield False
                remote.id = result[0]
                continue
            if not remote.valid:
                # remove the recording
                log.info('%s: remove %s', self.name, remote.recording.name)
                self.recordings.remove(remote)
                result = yield self.entity.rpc('home-theatre.vdr.remove', remote.id)
                if not result:
                    log.error(result)
                    self.handler.remove(self)
                    yield False



# ****************************************************************************
# API
# ****************************************************************************

# global RecorderList object
_recorder = RecorderList()

# signals for this module
signals = { 'changed': kaa.Signal(),
            'start-recording': kaa.Signal(),
            'stop-recording': kaa.Signal()
          }

def get_recorder(channel=None):
    """
    Get recorder. If channel is given, return the best recorder for this
    channel, if not, return all recorder objects.
    """
    if channel:
        return _recorder.best_recorder.get(channel)
    return _recorder.recorder
