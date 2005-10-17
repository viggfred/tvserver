# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# server.py -
# -----------------------------------------------------------------------------
# $Id$
#
#
# -----------------------------------------------------------------------------
# Freevo - A Home Theater PC framework
# Copyright (C) 2002-2004 Krister Lagerstrom, Dirk Meyer, et al.
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file freevo/Docs/CREDITS for a complete list of authors.
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
import notifier

# kaa.epg
import kaa.epg
import kaa.thumb
from kaa.notifier import Timer, OneShotTimer

# freevo imports
import freevo.fxdparser
from freevo.mcomm import RPCServer, RPCError, RPCReturn

# record imports
import config
import recorder

from record_types import *
from recording import Recording
from favorite import Favorite
import conflict

# get logging object
log = logging.getLogger('record')


class RecordServer(RPCServer):
    """
    Class for the recordserver. It handles the rpc calls and checks the
    schedule for recordings and favorites.
    """
    LIVE_TV_ID = 0
    
    def __init__(self):
        RPCServer.__init__(self, 'recordserver')
        self.clients = []
        self.last_listing = []
        self.live_tv_map = {}
        # add port for channels and check if they are in live-tv mode
        port = 6000
        for index, channel in enumerate(kaa.epg.channels):
            channel.port = port + index
            channel.registered = []
        
        # file to load / save the recordings and favorites
        self.fxdfile = freevo.conf.datafile('recordserver.fxd')
        # load the recordings file
        self.load()

        # timer to handle save and print debug in background
        self.save_timer = OneShotTimer(self.save, False)
        self.ps_timer = OneShotTimer(self.print_schedule, False)

        # add notify callback
        mbus = self.mbus_instance
        mbus.register_entity_notification(self.entity_update)

        # create recorder
        self.recorder = recorder.RecorderList(self)
        
        # start by checking the favorites
        self.check_current_recordings()
        self.check_favorites()

        # add schedule timer for SCHEDULE_TIMER / 3 seconds
        Timer(self.schedule).start(SCHEDULE_TIMER / 3)

        
    def send_update(self, update):
        """
        Send and updated list to the clients
        """
        for c in self.clients:
            log.info('send update to %s' % c)
            self.mbus_instance.send_event(c, 'record.list.update', update)
        # save fxd file
        self.save()


    def print_schedule(self, schedule=True):
        """
        Print current schedule (for debug only)
        """
        if schedule:
            if not self.ps_timer.active():
                self.ps_timer.start(0.01)
            return

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

        
    def check_recordings(self, force=False):
        """
        Check the current recordings. This includes checking conflicts,
        removing old entries. At the end, the timer is set for the next
        recording.
        """
        ctime = time.time()
        # remove informations older than one week
        self.recordings = filter(lambda r: r.start > ctime - 60*60*24*7,
                                 self.recordings)
        # sort by start time
        self.recordings.sort(lambda l, o: cmp(l.start,o.start))

        to_check = (CONFLICT, SCHEDULED, RECORDING)

        # check recordings we missed
        for r in self.recordings:
            if r.stop < ctime and r.status in to_check:
                r.status = MISSED

        # scan for conflicts
        next_recordings = filter(lambda r: r.stop + r.stop_padding > ctime \
                                 and r.status in to_check, self.recordings)

        for r in next_recordings:
            try:
                r.recorder = self.recorder.best_recorder[r.channel]
                if r.status != RECORDING:
                    r.status = SCHEDULED
                    r.respect_start_padding = True
                    r.respect_stop_padding  = True
            except KeyError:
                r.recorder = None
                r.status   = CONFLICT

        if force:
            # clear conflict resolve cache
            conflict.clear_cache()
            
        # Resolve conflicts. This will resolve the conflicts for the
        # next recordings now, the others will be resolved with a timer
        conflict.resolve(next_recordings, self.recorder)

        # send update
        sending = []
        listing = []
        for r in self.recordings:
            short_list = r.short_list()
            listing.append(short_list)
            if not short_list in self.last_listing:
                sending.append(short_list)
        self.last_listing = listing
        self.send_update(sending)

        # print some debug
        self.print_schedule()
        
        # sort by start time
        self.recordings.sort(lambda l, o: cmp(l.start,o.start))

        # schedule recordings in recorder
        self.schedule()


    def schedule(self):
        """
        Schedule recordings on recorder for the next SCHEDULE_TIMER seconds.
        """
        ctime = time.time()
        log.info('calling self.schedule')
        for r in self.recordings:
            if r.start > ctime + SCHEDULE_TIMER:
                # do not schedule to much in the future
                break
            if r.status == SCHEDULED:
                r.schedule(r.recorder)
            if r.status in (DELETED, CONFLICT):
                r.remove()
        return True
    

    def check_current_recordings(self):
        """
        Check current recordings against the database/
        """
        ctime = time.time() + 60 * 15
        recordings = filter(lambda r: r.start - r.start_padding > ctime \
                            and r.status in (CONFLICT, SCHEDULED),
                            self.recordings)

        # list of changes
        update = []
        for rec in recordings:
            # This could block the main loop. But we guess that there is
            # a reasonable number of future recordings, not 1000 recordings
            # that would block us here. Still, we need to find out if a very
            # huge database with over 100 channels will slow the database
            # down.

            # FIXME: This keeps the main loop alive but is ugly.
            # Change it to something better when kaa.epg is thread based
            kaa.notifier.step(False)
            
            # Search epg for that recording. The recording should be at the
            # same time, maybe it has moved +- 20 minutes. If the program
            # moved a larger time interval, it won't be found again.
            interval = (rec.start - 20 * 60, rec.start + 20 * 60)
            results = kaa.epg.search(rec.name, rec.channel, exact_match=True,
                                     interval = interval)
            epginfo = None
            changed = False
            for p in results:
                # check all results
                if p.start == rec.start and p.stop == rec.stop:
                    # found the recording
                    epginfo = p
                    break
            else:
                # try to find it
                for p in results:
                    if rec.start - 20 * 60 < p.start < rec.start + 20 * 60:
                        # found it again, set new start and stop time
                        old_info = str(rec)
                        rec.start = p.start
                        rec.stop = p.stop
                        log.info('changed schedule\n%s\n%s' % (old_info, rec))
                        changed = True
                        epginfo = p
                        break
                else:
                    log.info('unable to find recording in epg:\n%s' % rec)

            if epginfo:
                # check if attributes changed
                if String(rec.description) != String(epginfo.description):
                    log.info('description changed for %s' % String(rec.name))
                    rec.description = epginfo.description
                if String(rec.episode) != String(epginfo.episode):
                    log.info('episode changed for %s' % String(rec.name))
                    rec.episode = epginfo.episode
                if String(rec.subtitle) != String(epginfo.subtitle):
                    log.info('subtitle changed for %s' % String(rec.name))
                    rec.subtitle = epginfo.subtitle

            if changed:
                update.append(rec.short_list())
                
        # send update about the recordings
        self.send_update(update)

        
    def check_favorites(self):
        """
        Check favorites against the database and add them to the list of
        recordings
        """
        t1 = time.time()

        update = []
        
        # Check current scheduled recordings if the start time has changed.
        # Only check recordings with start time greater 15 minutes from now
        # to avoid changing running recordings
        for f in copy.copy(self.favorites):
            # Now check all the favorites. Again, this could block but we
            # assume a reasonable number of favorites.
            for p in kaa.epg.search(f.name, exact_match=True):

                # FIXME: This keeps the main loop alive but is ugly.
                # Change it to something better when kaa.epg is thread based
                kaa.notifier.step(False)
            
                if not f.match(p.title, p.channel.id, p.start):
                    continue

                r = Recording(p.title, p.channel.id, f.priority,
                              p.start, p.stop)
                if r in self.recordings:
                    # This does not only avoid adding recordings twice, it
                    # also prevents from added a deleted favorite as active
                    # again.
                    continue
                r.episode  = p.episode
                r.subtitle = p.subtitle
                r.description = p.description
                log.info('added %s: %s (%s)' % (String(p.channel.id),
                                                String(p.title), p.start))
                f.add_data(r)
                self.recordings.append(r)
                update.append(r.short_list())
                if f.once:
                    self.favorites.remove(f)
                    break

        t2 = time.time()
        log.info('check favorites took %s secs' % (t2-t1))
        
        # send update about the new recordings
        self.send_update(update)

        # now check the schedule again
        self.check_recordings()

        t2 = time.time()
        log.info('everything scheduled after %s secs' % (t2-t1))
        

    #
    # load / save fxd file with recordings and favorites
    #

    def __load_recording(self, parser, node):
        """
        callback for <recording> in the fxd file
        """
        try:
            r = Recording()
            r.parse_fxd(parser, node)
            self.recordings.append(r)
        except Exception, e:
            log.exception('recordserver.load_recording')


    def __load_favorite(self, parser, node):
        """
        callback for <favorite> in the fxd file
        """
        try:
            f = Favorite()
            f.parse_fxd(parser, node)
            self.favorites.append(f)
        except Exception, e:
            log.exception('recordserver.load_favorite:')


    def load(self):
        """
        load the fxd file
        """
        self.recordings = []
        self.favorites = []
        try:
            fxd = freevo.fxdparser.FXD(self.fxdfile)
            fxd.set_handler('recording', self.__load_recording)
            fxd.set_handler('favorite', self.__load_favorite)
            fxd.parse()
        except Exception, e:
            log.exception('recordserver.load: %s corrupt:' % self.fxdfile)


    def save(self, schedule=True):
        """
        save the fxd file
        """
        if schedule:
            if not self.save_timer.active():
                self.save_timer.start(0.01)
            return
        
        if not len(self.recordings) and not len(self.favorites):
            # do not save here, it is a bug I havn't found yet
            log.info('do not save fxd file')
            return
        try:
            log.info('save fxd file')
            if os.path.isfile(self.fxdfile):
                os.unlink(self.fxdfile)
            fxd = freevo.fxdparser.FXD(self.fxdfile)
            for r in self.recordings:
                fxd.add(r)
            for r in self.favorites:
                fxd.add(r)
            fxd.save()
        except:
            log.exception('lost the recordings.fxd, send me the trace')


    #
    # function to change a status
    #

    def start_recording(self, recording):
        if not recording:
            log.info('live tv started')
            return
        log.info('recording started')
        recording.status = RECORDING
        # send update to mbus entities
        self.send_update([recording.short_list()])
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
        # send update to mbus entities
        self.send_update([recording.short_list()])
        # print some debug
        self.print_schedule()
        
    
    #
    # global mbus stuff
    #

    def entity_update(self, entity):
        if not entity.present and entity in self.clients:
            log.info('lost client %s' % entity)
            self.clients.remove(entity)
            return
        return

    
    #
    # home.theatre.recording rpc commands
    #

    def __rpc_recording_list__(self, addr, val):
        """
        list the current recordins in a short form.
        result: [ ( id channel priority start stop status ) (...) ]
        """
        if not addr in self.clients:
            log.info('add client %s' % addr)
            self.clients.append(addr)
        self.parse_parameter(val, () )
        ret = []
        for r in self.recordings:
            ret.append(r.short_list())
        return RPCReturn(ret)


    def __rpc_recording_describe__(self, addr, val):
        """
        send a detailed description about a recording
        parameter: id
        result: ( id name channel priority start stop status padding info )
        """
        id = self.parse_parameter(val, ( int, ))
        for r in self.recordings:
            if r.id == id:
                return RPCReturn(r.long_list())
        return RPCError('Recording not found')


    def __rpc_recording_add__(self, addr, val):
        """
        add a new recording
        parameter: name channel priority start stop optionals
        optionals: subtitle, url, start-padding, stop-padding, description
        """
        if len(val) == 2 or len(val) == 5:
            # missing optionals
            val.append([])
        if len(val) == 3:
            # add by dbid
            dbid, priority, info = \
                  self.parse_parameter(val, ( int, int, dict ))
            prog = kaa.epg.guide.get_program_by_id(dbid)
            if not prog:
                return RPCError('Unknown id')
            channel = prog.channel.id
            name = prog.name
            start = prog.start
            stop = prog.stop
            if prog.subtitle and not info.has_key('subtitle'):
                info['subtitle'] = prog.subtitle
            if prog.episode and not info.has_key('episode'):
                info['episode'] = prog.episode
            if prog.description and not info.has_key('description'):
                info['description'] = prog.description
        else:
            name, channel, priority, start, stop, info = \
                  self.parse_parameter(val, ( unicode, unicode, int, int, int,
                                              dict ) )
        # fix description encoding
        if info.has_key('description') and \
               info['description'].__class__ == str:
            info['description'] = Unicode(info['description'], 'UTF-8')

        log.info('recording.add: %s' % String(name))
        r = Recording(name, channel, priority, start, stop, info = info)

        if r in self.recordings:
            r = self.recordings[self.recordings.index(r)]
            if r.status == DELETED:
                r.status   = SCHEDULED
                r.favorite = False
                # send update about the new recording
                self.send_update(r.short_list())
                self.check_recordings()
                return RPCReturn(r.id)
            return RPCError('Already scheduled')
        self.recordings.append(r)
        self.check_recordings()
        return RPCReturn(r.id - 1)


    def __rpc_recording_remove__(self, addr, val):
        """
        remove a recording
        parameter: id
        """
        id = self.parse_parameter(val, ( int, ))
        log.info('recording.remove: %s' % id)
        for r in self.recordings:
            if r.id == id:
                if r.status == RECORDING:
                    r.status = SAVED
                else:
                    r.status = DELETED
                # send update about the new recording
                self.send_update(r.short_list())
                # update listing
                self.check_recordings()
                return RPCReturn()
        return RPCError('Recording not found')


    def __rpc_watch_start__(self, addr, val):
        """
        live recording
        parameter: channel
        """
        channel = self.parse_parameter(val, ( str, ))
        for c in kaa.epg.channels:
            if c.id == channel:
                channel = c
                break
        else:
            return RPCError('channel %s not found' % channel)

        if channel.registered:
            # Already sending a stream of this channel, reuse it
            channel.registered.append(addr)

            RecordServer.LIVE_TV_ID += 1
            id = RecordServer.LIVE_TV_ID
            self.live_tv_map[id] = channel

            return RPCReturn((id, url))
            
        # Find a device for recording. The device should be not recording
        # right now and for the next 5 minutes or recording on the same
        # bouquet. And it should the recorder with the best priority.
        
        # FIXME: right now we take one recorder no matter if it is
        # recording right now.
        rec = self.recorder.best_recorder[channel.id]
        if not rec:
            return RPCError('no recorder for %s found' % channel.id)

        url = 'udp://%s:%s' % (conf.LIVETV_URL, channel.port)

        # no app is watching this channel right now, start recorder
        rec_id = rec.start_livetv(channel.id, url)
        # save id and recorder in channel
        channel.recorder = rec, rec_id
        channel.registered.append(addr)

        RecordServer.LIVE_TV_ID += 1
        id = RecordServer.LIVE_TV_ID
        self.live_tv_map[id] = channel

        # return id and url
        return RPCReturn((id, url))

        
    def __rpc_watch_stop__(self, addr, val):
        """
        live recording
        parameter: id
        """
        id = self.parse_parameter(val, ( int, ))
        log.info('stop live tv with id %s' % id)
        if not id in self.live_tv_map:
            return RPCError('invalid id %s' % id)
            
        channel = self.live_tv_map[id]
        del self.live_tv_map[id]

        # remove watcher
        if not addr in channel.registered:
            return RPCError('%s is not watching channel', addr)
            
        channel.registered.remove(addr)

        if not channel.registered:
            # channel is no longer watched
            recorder, id = channel.recorder
            recorder.stop_livetv(id)
            
        return RPCReturn()
        
        
    def __rpc_recording_modify__(self, addr, val):
        """
        modify a recording
        parameter: id [ ( var val ) (...) ]
        """
        id, key_val = self.parse_parameter(val, ( int, dict ))
        log.info('recording.modify: %s' % id)
        for r in self.recordings:
            if r.id == id:
                if r.status == RECORDING:
                    return RPCError('Currently recording')
                cp = copy.copy(self.recordings[id])
                for key in key_val:
                    setattr(cp, key, key_val[key])
                self.recordings[self.recordings.index(r)] = cp
                # send update about the new recording
                self.send_update(r.short_list())
                # update listing
                self.check_recordings()
                return RPCReturn()
        return RPCError('Recording not found')


    #
    # home.theatre.favorite rpc commands
    #

    def __rpc_favorite_update__(self, addr=None, val=[]):
        """
        updates favorites with data from the database
        """
        self.check_current_recordings()
        self.check_favorites()
        return RPCReturn()


    def __rpc_favorite_add__(self, addr, val):
        """
        add a favorite
        parameter: name channels priority days times
        channels is a list of channels
        days is a list of days ( 0 = Sunday - 6 = Saturday )
        times is a list of hh:mm-hh:mm
        """
        name, channels, priority, days, times, once = \
              self.parse_parameter(val, ( unicode, list, int, list, list,
                                          bool ))
        log.info('favorite.add: %s' % String(name))
        f = Favorite(name, channels, priority, days, times, once)
        if f in self.favorites:
            return RPCError('Already scheduled')
        self.favorites.append(f)
        return self.__rpc_favorite_update__()


    def __rpc_favorite_list__(self, addr, val):
        """
        """
        if not addr in self.clients:
            log.info('add client %s' % addr)
            self.clients.append(addr)
        self.parse_parameter(val, () )
        ret = []
        for f in self.favorites:
            ret.append(f.long_list())
        return RPCReturn(ret)


    def __rpc_status__(self, addr, val):
        """
        Send status on rpc status request.
        """
        status = {}
        ctime = time.time()

        # find currently running recordings
        rec = filter(lambda r: r.status == RECORDING, self.recordings)
        if rec:
            # something is recording, add busy time of first recording
            busy = rec[0].stop + rec[0].stop_padding - ctime
            status['busy'] = max(1, int(busy / 60) + 1)

        # find next scheduled recordings for wakeup
        rec = filter(lambda r: r.status == SCHEDULED and \
                     r.start - r.start_padding > ctime, self.recordings)
        if rec:
            # set wakeup time
            status['wakeup'] = rec[0].start - rec[0].start_padding

        # return results
        return RPCReturn(status)
