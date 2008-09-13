# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# controller.py
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

__all__ = [ 'Controller' ]

# python imports
import copy
import os
import sys
import time
import logging

# kaa imports
import kaa

# freevo imports
import freevo.conf
import freevo.fxdparser

# tvserver imports
from config import config
import recorder
from record_types import *
from recording import Recording
from favorite import Favorite
import scheduler
from epg import EPG

# get logging object
log = logging.getLogger()

class Controller(object):
    """
    Class for the tvserver.
    """
    def __init__(self):
        self.epg = EPG()
        self.locked = False
        # file to load / save the recordings and favorites
        self.fxdfile = freevo.conf.datafile('tvschedule.fxd')
        # load the recordings file
        self.load_fxd()
        # connect to recorder signals
        recorder.signals['start-recording'].connect(self._recorder_start)
        recorder.signals['stop-recording'].connect(self._recorder_stop)
        recorder.signals['changed'].connect(self.reschedule)
        # start by checking the recordings/favorites
        self.check_epg()
        # add schedule timer for SCHEDULE_TIMER / 3 seconds
        kaa.Timer(self.check_epg).start(SCHEDULE_TIMER / 3)

    @kaa.timed(0.1, kaa.OneShotTimer, policy=kaa.POLICY_ONCE)
    def print_schedule(self):
        """
        Print current schedule (for debug only)
        """
        if self.locked:
            # system busy, call again later
            self.print_schedule()
            return True
        if hasattr(self, 'only_print_current'):
            # print only latest recordings
            all = False
        else:
            # print all recordings in the list
            all = True
            # mark that all are printed once
            self.only_print_current = True
        # print only from the last 24 hours
        maxtime = time.time() - 60 * 60 * 24
        info = 'recordings:\n'
        for r in self.recordings:
            if all or r.stop > maxtime:
                info += '%s\n' % r
        log.info(info)
        info = 'favorites:\n'
        for f in self.favorites:
            info += '%s\n' % f
        log.info(info)

    @kaa.coroutine()
    def reschedule(self):
        """
        Reschedule all recordings.
        """
        if self.locked:
            # system busy, call again later
            kaa.OneShotTimer(self.reschedule).start(0.1)
            yield True
        self.locked = True
        yield scheduler.schedule(self.recordings)
        # save fxd file
        self.save_fxd()
        # print some debug
        self.print_schedule()
        # Schedule recordings on recorder for the next SCHEDULE_TIMER seconds.
        log.info('schedule recordings')
        # sort by start time
        self.recordings.sort(lambda l, o: cmp(l.start,o.start))
        # get current time
        ctime = time.time()
        # remove old recorderings
        self.recordings = filter(lambda r: r.start > ctime - 60*60*24*7, self.recordings)
        # schedule current (== now + SCHEDULE_TIMER) recordings
        for r in self.recordings:
            if r.start > ctime + SCHEDULE_TIMER:
                # do not schedule to much in the future
                break
            if r.status == SCHEDULED:
                r.schedule(r.recorder)
            if r.status in (DELETED, CONFLICT):
                r.remove()
        # unlock system
        self.locked = False

    @kaa.coroutine()
    def check_epg(self):
        """
        Update recordings based on favorites and epg.
        """
        if self.locked:
            # system busy, call again later
            kaa.OneShotTimer(self.check_epg).start(0.1)
            return
        self.locked = True
        yield self.epg.check(self.recordings, self.favorites)
        self.locked = False
        self.reschedule()

    #
    # load / save fxd file with recordings and favorites
    #

    def load_fxd(self):
        """
        load the fxd file
        """
        self.recordings = []
        self.favorites = []
        if not os.path.isfile(self.fxdfile):
            return
        try:
            fxd = freevo.fxdparser.Document(self.fxdfile)
        except Exception, e:
            log.exception('tvserver.load: %s corrupt:' % self.fxdfile)
            sys.exit(1)
        for child in fxd.children:
            if child.name == 'recording':
                try:
                    r = Recording(node=child)
                except Exception, e:
                    log.exception('tvserver.load_recording')
                    continue
                if r.status == RECORDING:
                    log.warning('recording in status \'recording\'')
                    # Oops, we are in 'recording' status and this was saved.
                    # That means we are stopped while recording, set status to
                    # missed
                    r.status = MISSED
                if r.status == SCHEDULED:
                    # everything is a conflict for now
                    r.status = CONFLICT
                self.recordings.append(r)
            if child.name == 'favorite':
                try:
                    f = Favorite(node=child)
                except Exception, e:
                    log.exception('tvserver.load_favorite:')
                    continue
                self.favorites.append(f)

    @kaa.timed(1, kaa.OneShotTimer, policy=kaa.POLICY_RESTART)
    def save_fxd(self):
        """
        save the fxd file
        """
        log.info('save fxd file')
        fxd = freevo.fxdparser.Document()
        for r in self.recordings:
            r.to_xml(fxd)
        for f in self.favorites:
            f.to_xml(fxd)
        fxd.save(self.fxdfile)

    #
    # callbacks from the recorder
    #

    def _recorder_start(self, recording):
        log.info('recording started')
        recording.status = RECORDING
        # save fxd file
        self.save_fxd()
        # create fxd file
        recording.create_fxd()
        # print some debug
        self.print_schedule()

    def _recorder_stop(self, recording):
        log.info('recording stopped')
        if recording.url.startswith('file:'):
            filename = recording.url[5:]
            if os.path.isfile(filename):
                recording.status = SAVED
            else:
                log.info('failed: file not found %s' % recording.url)
                recording.status = FAILED
                # Without a recording file, the fxd file is useless
                fxdfile = os.path.splitext(filename)[0] + '.fxd'
                if os.path.isfile(fxdfile):
                    # fxd file must be in real not in overlay dir, without
                    # that, the recorder couldn't even store the file
                    os.unlink(fxdfile)
        else:
            recording.status = SAVED
        if recording.status == SAVED and time.time() + 100 < recording.stop:
            # something went wrong
            log.info('failed: stopped %s secs to early' % \
                     (recording.stop - time.time()))
            recording.status = FAILED
        # save fxd file
        self.save_fxd()
        # print some debug
        self.print_schedule()

    def recording_add(self, name, channel, priority, start, stop, **info):
        """
        add a new recording
        """
        log.info('recording.add: %s', name)
        r = Recording(name, channel, priority, start, stop, info=info)
        if r in self.recordings:
            r = self.recordings[self.recordings.index(r)]
            if r.status == DELETED:
                r.status = CONFLICT
                r.favorite = False
                # update schedule, this will also send an update to all
                # clients registered.
                self.reschedule()
                return r
            raise AttributeError('Already scheduled')
        self.recordings.append(r)
        self.reschedule()
        return r

    def recording_remove(self, id):
        """
        remove a recording
        """
        log.info('recording.remove: %s' % id)
        for r in self.recordings:
            if r.id == id:
                break
        else:
            raise IndexError('Recording not found')
        if r.status == RECORDING:
            r.status = SAVED
        else:
            r.status = DELETED
        # update schedule, this will also send an update to all
        # clients registered.
        self.reschedule()

    def recording_modify(self, id, **kwargs):
        """
        modify a recording
        """
        log.info('recording.modify: %s' % id)
        for r in self.recordings:
            if r.id == id:
                break
        else:
            raise IndexError('Recording not found')
        if r.status == RECORDING:
            return RuntimeError('Currently recording')
        cp = copy.copy(self.recordings[id])
        for key, value in kwargs.items():
            setattr(cp, key, value)
        self.recordings[self.recordings.index(r)] = cp
        # update schedule, this will also send an update to all
        # clients registered.
        self.reschedule()

    def favorite_update(self):
        """
        updates favorites with data from the database
        """
        return self.check_epg()

    def favorite_add(self, name, channels, priority, days, times, once, substring):
        """
        add a favorite
        """
        log.info('favorite.add: %s', name)
        f = Favorite(name, channels, priority, days, times, once, substring)
        if f in self.favorites:
            return NameError('Already scheduled')
        self.favorites.append(f)
        # Align favorites id(s)
        next = 0
        for r in self.favorites:
            r.id = next
            next += 1
        # update schedule
        self.check_epg()

    def favorite_remove(self, id):
        """
        remove a favorite
        """
        for f in self.favorites:
            if id == f.id:
                break
        else:
            return NameError('Favorite not found!')
        log.info('favorite.remove: %s', f)
        self.favorites.remove(f)
        # align favorites id(s)
        next = 0
        for r in self.favorites:
            r.id = next
            next += 1

    def favorite_modify(self, id, **kwargs):
        """
        modify a recording
        """
        log.info('favorite.modify: %s' % id)
        for r in self.favorites:
            if r.id == id:
                break
        else:
            return IndexError('Favorite not found')
        cp = copy.copy(self.favorites[id])
        for key, value in kwargs.items():
            setattr(cp, key, value)
        self.favorites[self.favorites.index(r)] = cp
        # update schedule
        self.check_epg()
