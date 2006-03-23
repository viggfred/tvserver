# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# server.py -
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


# python imports
import copy
import os
import sys
import time
import logging

import kaa.thumb
from kaa.notifier import Timer, OneShotTimer, Callback, execute_in_timer
from kaa import xml

# freevo imports
import freevo.ipc

# record imports
from config import config
import recorder

from record_types import *
from recording import Recording
from favorite import Favorite
from scheduler import Scheduler
from epg import EPG

# get logging object
log = logging.getLogger('record')

class RecordServer(object):
    """
    Class for the recordserver. It handles the rpc calls and checks the
    schedule for recordings and favorites.
    """
    LIVE_TV_ID = 0

    def __init__(self):
        self.scheduler = Scheduler(self.scheduler_callback)
        self.epg = EPG()
        self.epg.signals['updated'].connect(self.epg_update)
        
        self.last_listing = []
        self.live_tv_map = {}
        self.locked = False
        self.epgaddr = ('', 0)
        
        # add port for channels and check if they are in live-tv mode
        port = 6000
        for index, channel in enumerate(self.epg.channels()):
            channel.port = port + index
            channel.registered = []

        # file to load / save the recordings and favorites
        self.fxdfile = freevo.conf.datafile('recordserver.fxd')
        # load the recordings file
        self.load()

        # connect to recorder signals and create recorder
        recorder.signals['start-recording'].connect(self.start_recording)
        recorder.signals['stop-recording'].connect(self.stop_recording)
        recorder.signals['changed'].connect(self.reschedule)
        recorder.connect()

        # start by checking the recordings/favorites
        self.epg_update()

        # add schedule timer for SCHEDULE_TIMER / 3 seconds
        Timer(self.schedule).start(SCHEDULE_TIMER / 3)

        Timer(self.update_status).start(60)

        # create mbus instance
        mbus = freevo.ipc.Instance('tvserver')

        # connect exposed functions
        mbus.connect(self)

        # set status information
        mbus.connect('freevo.ipc.status')
        self.status = mbus.status
        self.send_event = mbus.send_event

        # update status and start timer
        self.update_status()


    @execute_in_timer(OneShotTimer, 0.1, type='once')
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


    def reschedule(self):
        """
        Reschedule all recordings.
        """
        if self.locked:
            # system busy, call again later
            OneShotTimer(self.reschedule).start(0.1)
            return True
        self.locked = True
        self.scheduler.schedule(self.recordings)


    def scheduler_callback(self):
        log.info('answer from scheduler')

        # unlock system
        self.locked = False

        # send update
        sending = []
        listing = []

        for r in self.recordings:
            short_list = r.short_list()
            listing.append(short_list)
            if not short_list in self.last_listing:
                sending.append(short_list)
        self.last_listing = listing

        # send update to all clients
        self.send_event('home-theatre.record.list.update', *sending)

        # save fxd file
        self.save()

        # print some debug
        self.print_schedule()

        # schedule recordings in recorder
        self.schedule()


    def schedule(self):
        """
        Schedule recordings on recorder for the next SCHEDULE_TIMER seconds.
        """
        if self.locked:
            # system busy, call again later
            OneShotTimer(self.schedule).start(0.1)
            return True
        
        log.info('calling self.schedule')
        # sort by start time
        self.recordings.sort(lambda l, o: cmp(l.start,o.start))

        # get current time
        ctime = time.time()

        # remove old recorderings
        self.recordings = filter(lambda r: r.start > ctime - 60*60*24*7,
                                 self.recordings)
        # schedule current (== now + SCHEDULE_TIMER) recordings
        for r in self.recordings:
            if r.start > ctime + SCHEDULE_TIMER:
                # do not schedule to much in the future
                break
            if r.status == SCHEDULED:
                r.schedule(r.recorder)
            if r.status in (DELETED, CONFLICT):
                r.remove()
        return True


    def epg_update(self):
        """
        Update recordings based on favorites and epg.
        """
        if self.locked:
            # system busy, call again later
            OneShotTimer(self.epg_update).start(0.1)
            return True
        self.locked = True
        self.epg.check_all(self.favorites, self.recordings, self.epg_update_callback)


    def epg_update_callback(self):
        """
        """
        self.locked = False
        self.reschedule()

        
    #
    # load / save fxd file with recordings and favorites
    #

    def load(self):
        """
        load the fxd file
        """
        self.recordings = []
        self.favorites = []

        if not os.path.isfile(self.fxdfile):
            return

        try:
            fxd = xml.Document(self.fxdfile, 'freevo')
        except Exception, e:
            log.exception('recordserver.load: %s corrupt:' % self.fxdfile)
            sys.exit(1)

        for child in fxd:
            if child.name == 'recording':
                try:
                    r = Recording(node=child)
                except Exception, e:
                    log.exception('recordserver.load_recording')
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
                    log.exception('recordserver.load_favorite:')
                    continue
                self.favorites.append(f)


    @execute_in_timer(OneShotTimer, 1, type='override')
    def save(self):
        """
        save the fxd file
        """
        log.info('save fxd file')
        fxd = xml.Document(root='freevo')
        for r in self.recordings:
            fxd.add_child(r)
        for f in self.favorites:
            fxd.add_child(f)
        fxd.save(self.fxdfile)


    #
    # callbacks from the recorder
    #

    def start_recording(self, recording):
        if not recording:
            log.info('live tv started')
            return
        log.info('recording started')
        recording.status = RECORDING
        # send update to all clients
        self.send_event('home-theatre.record.list.update', recording.short_list())
        # save fxd file
        self.save()
        # create fxd file
        recording.create_fxd()
        # print some debug
        self.print_schedule()


    def stop_recording(self, recording):
        if not recording:
            log.info('live tv stopped')
            return
        log.info('recording stopped')
        if recording.url.startswith('file:'):
            filename = recording.url[5:]
            if os.path.isfile(filename):
                recording.status = SAVED
                # create thumbnail
                kaa.thumb.videothumb(filename)
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
        # send update to all clients
        self.send_event('home-theatre.record.list.update', recording.short_list())
        # save fxd file
        self.save()
        # print some debug
        self.print_schedule()


    #
    # home.theatre.recording rpc commands
    #

    @freevo.ipc.expose('home-theatre.recording.list', add_source=True)
    def rpc_recording_list(self, source):
        """
        list the current recordins in a short form.
        result: [ ( id channel priority start stop status ) (...) ]
        """
        ret = []
        for r in self.recordings:
            ret.append(r.short_list())
        return ret


    @freevo.ipc.expose('home-theatre.recording.describe')
    def rpc_recording_describe(self, id):
        """
        send a detailed description about a recording
        parameter: id
        result: ( id name channel priority start stop status padding info )
        """
        for r in self.recordings:
            if r.id == id:
                return r.long_list()
        raise IndexError('Recording %s (%s) not found', id, type(id))


    @freevo.ipc.expose('home-theatre.recording.add')
    def rpc_recording_add(self, name, channel, priority, start, stop, info=()):
        """
        add a new recording
        parameter: name channel priority start stop optionals
        optionals: subtitle, url, start-padding, stop-padding, description
        """
        info = dict(info)

        log.info('recording.add: %s' % String(name))
        r = Recording(name, channel, priority, start, stop, info=info)

        if r in self.recordings:
            r = self.recordings[self.recordings.index(r)]
            if r.status == DELETED:
                r.status   = CONFLICT
                r.favorite = False
                # update schedule, this will also send an update to all
                # clients registered.
                self.reschedule()
                return [ r.id ]
            raise AttributeError('Already scheduled')
        self.recordings.append(r)
        self.reschedule()
        return [ r.id - 1 ]


    @freevo.ipc.expose('home-theatre.recording.remove')
    def rpc_recording_remove(self, id):
        """
        remove a recording
        parameter: id
        """
        log.info('recording.remove: %s' % id)
        for r in self.recordings:
            if r.id == id:
                if r.status == RECORDING:
                    r.status = SAVED
                else:
                    r.status = DELETED
                # update schedule, this will also send an update to all
                # clients registered.
                self.reschedule()
                return []
        raise IndexError('Recording not found')


    @freevo.ipc.expose('home-theatre.recording.modify')
    def rpc_recording_modify(self, int, info):
        """
        modify a recording
        parameter: id [ ( var val ) (...) ]
        """
        key_val = dict(info)
        log.info('recording.modify: %s' % id)
        for r in self.recordings:
            if r.id == id:
                if r.status == RECORDING:
                    return RuntimeError('Currently recording')
                cp = copy.copy(self.recordings[id])
                for key in key_val:
                    setattr(cp, key, key_val[key])
                self.recordings[self.recordings.index(r)] = cp
                # update schedule, this will also send an update to all
                # clients registered.
                self.reschedule()
                return []
        return IndexError('Recording not found')


    #
    # home.theatre.watch rpc commands
    #

    @freevo.ipc.expose('home-theatre.watch.start', add_source=True)
    def rpc_watch_start(self, source, channel):
        """
        live recording
        parameter: channel
        """
        for c in self.epg.channels():
            if c.name == channel:
                channel = c
                break
        else:
            raise IndexError('channel %s not found' % channel)

        url = 'udp://%s:%s' % (config.livetv_url, channel.port)

        if channel.registered:
            # Already sending a stream of this channel, reuse it
            channel.registered.append(source)

            RecordServer.LIVE_TV_ID += 1
            id = RecordServer.LIVE_TV_ID
            self.live_tv_map[id] = channel

            return [ id, url ]

        # Find a device for recording. The device should be not recording
        # right now and for the next 5 minutes or recording on the same
        # bouquet. And it should the recorder with the best priority.

        # FIXME: right now we take one recorder no matter if it is
        # recording right now.
        rec = recorder.get_recorder(channel.id)
        if not rec:
            return RuntimeError('no recorder for %s found' % channel.id)

        # no app is watching this channel right now, start recorder
        rec_id = rec.start_livetv(channel.id, url)
        # save id and recorder in channel
        channel.recorder = rec, rec_id
        channel.registered.append(source)

        RecordServer.LIVE_TV_ID += 1
        id = RecordServer.LIVE_TV_ID
        self.live_tv_map[id] = channel

        # return id and url
        return [ id, url ]


    @freevo.ipc.expose('home-theatre.watch.stop', add_source=True)
    def rpc_watch_stop(self, source, id):
        """
        live recording
        parameter: id
        """
        log.info('stop live tv with id %s' % id)
        if not id in self.live_tv_map:
            return IndexError('invalid id %s' % id)

        channel = self.live_tv_map[id]
        del self.live_tv_map[id]

        # remove watcher
        if not source in channel.registered:
            raise RuntimeError('%s is not watching channel', source)

        channel.registered.remove(source)

        if not channel.registered:
            # channel is no longer watched
            recorder, id = channel.recorder
            recorder.stop_livetv(id)

        return []



    #
    # home.theatre.favorite rpc commands
    #

    @freevo.ipc.expose('home-theatre.favorite.update')
    def rpc_favorite_update(self):
        """
        updates favorites with data from the database
        """
        self.epg_update()
        return []


    @freevo.ipc.expose('home-theatre.favorite.add')
    def rpc_favorite_add(self, name, channels, priority, days, times, once):
        """
        add a favorite
        parameter: name channels priority days times
        channels is a list of channels
        days is a list of days ( 0 = Sunday - 6 = Saturday )
        times is a list of hh:mm-hh:mm
        """
        log.info('favorite.add: %s' % String(name))
        f = Favorite(name, channels, priority, days, times, once)
        if f in self.favorites:
            return NameError('Already scheduled')
        self.favorites.append(f)
        self.rpc_favorite_update()
        return []


    @freevo.ipc.expose('home-theatre.favorite.list', add_source=True)
    def rpc_favorite_list(self, source):
        """
        """
        ret = []
        for f in self.favorites:
            ret.append(f.long_list())
        return ret


    #
    # home.theatre.epg rpc commands
    #


    @freevo.ipc.expose('home-theatre.epg.connect')
    def rpc_epg_connect(self):
        """
        """
        return self.epgaddr


    @freevo.ipc.expose('home-theatre.epg.update')
    def rpc_epg_update(self):
        """
        """
        log.info('home-theatre.epg.update')
        self.epg.update()
        return []


    #
    # mbus.status handling
    #

    def update_status(self):
        """
        Update status information every minute.
        """
        ctime = time.time()

        # reset status
        self.status.set('busy', 0)
        self.status.set('wakeup', 0)

        # find currently running recordings
        rec = filter(lambda r: r.status == RECORDING, self.recordings)
        if rec:
            # something is recording, add busy time of first recording
            busy = rec[0].stop + rec[0].stop_padding - ctime
            self.status.set('busy', max(1, int(busy / 60) + 1))
        elif self.epg.updating:
            # epg update in progress
            self.status.set('busy', 1)
            
        # find next scheduled recordings for wakeup
        # FIXME: what about CONFLICT? we don't need to start the server
        # for a normal conflict, but we may need it when tvdev is not running
        # right now.
        rec = filter(lambda r: r.status == SCHEDULED and \
                     r.start - r.start_padding > ctime, self.recordings)
        if rec:
            # set wakeup time
            self.status.set('wakeup', rec[0].start - rec[0].start_padding)

        return True
