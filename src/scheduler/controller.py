# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# controller.py
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
# Copyright (C) 2004-2009 Dirk Meyer, et al.
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
import kaa.xmlutils

# tvserver imports
from config import config
import device
from recording import Recording, MISSED, SAVED, SCHEDULED, RECORDING, CONFLICT, DELETED, FAILED
from favorite import Favorite
import scheduler
import epg

# get logging object
log = logging.getLogger('tvserver')

# Time when to schedule the recording on a recorder
# (only next hour, update every 30 minutes)
SCHEDULE_TIMER = 60 * 60

class Controller(object):
    """
    Class for the tvserver.
    """
    def __init__(self, datafile):
        epg.init()
        self.locked = False
        self.datafile = datafile
        # load the recordings file
        self.load_schedule()
        # connect to recorder signals
        device.signals['start-recording'].connect(self._recorder_start)
        device.signals['stop-recording'].connect(self._recorder_stop)
        device.signals['changed'].connect(self.reschedule)
        # start by checking the recordings/favorites
        self.check_favorites_and_reschedule()
        # add schedule timer for SCHEDULE_TIMER / 3 seconds
        kaa.Timer(self.check_favorites_and_reschedule).start(SCHEDULE_TIMER / 3)

    @kaa.timed(0.1, kaa.OneShotTimer, policy=kaa.POLICY_ONCE)
    def print_schedule(self):
        """
        Print current schedule (for debug only)
        """
        if self.locked:
            # system busy, call again later
            self.print_schedule()
            return False
        if hasattr(self, 'only_print_current'):
            # print only latest recordings
            all = False
        else:
            # print all recordings in the list
            all = True
            # mark that all are printed once
            self.only_print_current = True
        # print only from the last 24 hours
        maxtime = int(time.time()) - 60 * 60 * 24
        info = 'recordings:\n'
        for r in self.recordings:
            if all or r.stop > maxtime:
                info += '%s\n' % r
        log.info(info)
        info = 'favorites:\n'
        for f in self.favorites:
            info += '%s\n' % f
        log.info(info)
        return True

    @kaa.coroutine()
    def reschedule(self):
        """
        Reschedule all recordings.
        """
        if self.locked:
            # system busy, call again later
            kaa.OneShotTimer(self.reschedule).start(0.1)
            yield False
        self.locked = True
        # get current time (UTC)
        ctime = int(time.time())
        # remove old recorderings
        self.recordings = filter(lambda r: r.start > ctime - 60*60*24*7, self.recordings)
        # run the scheduler to attach devices to recordings
        yield scheduler.schedule(self.recordings)
        # sort by start time
        self.recordings.sort(lambda l, o: cmp(l.start,o.start))
        # save schedule
        self.save_schedule()
        self.print_schedule()
        # Schedule recordings on recorder for the next SCHEDULE_TIMER seconds.
        log.info('schedule recordings')
        for r in self.recordings:
            if r.start < ctime + SCHEDULE_TIMER and r.status == SCHEDULED:
                r.schedule()
        self.locked = False
        yield True

    @kaa.coroutine()
    def check_favorites_and_reschedule(self):
        """
        Update recordings based on favorites and epg.
        """
        if self.locked:
            # system busy, call again later
            kaa.OneShotTimer(self.check_favorites_and_reschedule).start(0.1)
            yield False
        self.locked = True
        yield epg.check(self.recordings, self.favorites)
        self.locked = False
        self.reschedule()
        yield True

    #
    # load / save schedule file with recordings and favorites
    #

    def load_schedule(self):
        """
        load the schedule file
        """
        self.recordings = []
        self.favorites = []
        if not os.path.isfile(self.datafile):
            return
        try:
            xml = kaa.xmlutils.create(self.datafile, root='schedule')
        except Exception, e:
            log.exception('tvserver.load: %s corrupt:' % self.datafile)
            sys.exit(1)
        for child in xml:
            if child.nodename == 'recording':
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
            if child.nodename == 'favorite':
                try:
                    f = Favorite(node=child)
                except Exception, e:
                    log.exception('tvserver.load_favorite:')
                    continue
                self.favorites.append(f)

    @kaa.timed(1, kaa.OneShotTimer, policy=kaa.POLICY_RESTART)
    def save_schedule(self):
        """
        save the schedule file
        """
        log.info('save schedule')
        xml = kaa.xmlutils.create(root='schedule')
        for r in self.recordings:
            r.__xml__(xml)
        for f in self.favorites:
            f.__xml__(xml)
        if not os.path.isdir(os.path.dirname(self.datafile)):
            os.makedirs(os.path.dirname(self.datafile))
        xml.save(self.datafile)

    #
    # callbacks from the recorder
    #

    def _recorder_start(self, recording):
        log.info('recording started')
        recording.status = RECORDING
        # save schedule file
        self.save_schedule()
        # create fxd file
        recording.create_fxd()
        # print some debug
        self.print_schedule()

    def _recorder_stop(self, recording, success=True):
        log.info('recording stopped')
        if not success:
            # FIXME: delete fxd file
            recording.status = FAILED
        elif time.time() + 100 < recording.stop:
            # something went wrong
            log.info('failed: stopped %s secs to early' % (recording.stop - int(time.time())))
            recording.status = FAILED
        else:
            recording.status = SAVED
        # save schedule file
        self.save_schedule()
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

    #
    # API
    #

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
        return self.check_favorites_and_reschedule()

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
        self.check_favorites_and_reschedule()

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
        self.check_favorites_and_reschedule()
