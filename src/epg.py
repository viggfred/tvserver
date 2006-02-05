# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# epg.py - EPG handling for the recordserver
# -----------------------------------------------------------------------------
# $Id: server.py 7893 2006-01-29 17:53:54Z dmeyer $
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
import time
import logging

# kaa imports
import kaa.epg
from kaa.notifier import OneShotTimer, Timer, Signal, execute_in_timer

# record imports
from record_types import *
from recording import Recording

# get logging object
log = logging.getLogger('record')


class EPG(object):

    def __init__(self):
        self.signals = { 'changed': Signal() }


    def channels(self):
        """
        Return list of channels.
        """
        return kaa.epg.channels


    def check_all(self, favorites, recordings, callback, *args, **kwargs):
        """
        Check recordings and favorites against epg.
        """
        self.check_recordings(recordings, self.check_favorities, favorites,
                              recordings, callback, *args, **kwargs)


    def check_recordings(self, recordings, callback, *args, **kwargs):
        """
        Check current recordings against the database
        """
        cb = None
        if callback:
            cb = OneShotTimer(callback, *args, **kwargs)

        # get list of recordings to check
        ctime = time.time() + 60 * 15
        recordings = [ r for r in recordings if r.start - r.start_padding > ctime \
                       and r.status in (CONFLICT, SCHEDULED) ]
        # start check_recordings_step
        self.check_recordings_step(recordings, cb)


    @execute_in_timer(Timer, 0)
    def check_recordings_step(self, recordings, callback):
        """
        Check one recording
        """
        if not recordings:
            # start callback
            if callback:
                callback.start(0)
            return False

        # get one recording to check
        rec = recordings.pop(0)

        # Search epg for that recording. The recording should be at the
        # same time, maybe it has moved +- 20 minutes. If the program
        # moved a larger time interval, it won't be found again.
        interval = (rec.start - 20 * 60, rec.start + 20 * 60)
        results = kaa.epg.search(rec.name, rec.channel, exact_match=True,
                                 interval = interval)

        for epginfo in results:
            # check all results
            if epginfo.start == rec.start and epginfo.stop == rec.stop:
                # found the recording
                break
        else:
            # try to find it
            for epginfo in results:
                if rec.start - 20 * 60 < epginfo.start < rec.start + 20 * 60:
                    # found it again, set new start and stop time
                    old_info = str(rec)
                    rec.start = epginfo.start
                    rec.stop = epginfo.stop
                    log.info('changed schedule\n%s\n%s' % (old_info, rec))
                    self.signals['changed'].emit(rec)
                    break
            else:
                log.info('unable to find recording in epg:\n%s' % rec)
                return True

        # check if attributes changed (Note: String() should not be
        # needed here, everything has to be unicode, at least when
        # kaa.epg2 is done)
        for attr in ('description', 'episode', 'subtitle'):
            if String(getattr(rec, attr)) != String(getattr(epginfo, attr)):
                log.info('%s changed for %s', attr, rec.name)
                setattr(rec, attr, getattr(epginfo, attr))
        return True


    def check_favorities(self, favorites, recordings, callback, *args, **kwargs):
        """
        Check favorites against the database and add them to the list of
        recordings. If callback is given, the callback will be called
        when checking is done.
        """
        cb = None
        if callback:
            cb = OneShotTimer(callback, *args, **kwargs)
        self.check_favorites_step(favorites, favorites[:], recordings, cb)


    @execute_in_timer(Timer, 0)
    def check_favorites_step(self, all_favorites, favorites, recordings, callback):
        """
        Check one favorite or run the callback when finished
        """
        if not favorites:
            # start callback
            if callback:
                callback.start(0)
            return False

        # get favorite to check
        fav = favorites.pop(0)

        # Now search the db
        for p in kaa.epg.search(fav.name, exact_match=not fav.substring):
            if not fav.match(p.title, p.channel.id, p.start):
                continue

            rec = Recording(p.title, p.channel.id, fav.priority,
                            p.start, p.stop, episode=p.episode,
                            subtitle=p.subtitle, description=p.description)

            if rec in recordings:
                # This does not only avoid adding recordings twice, it
                # also prevents from added a deleted favorite as active
                # again.
                continue

            fav.add_data(rec)
            recordings.append(rec)
            log.info('added\n%s', rec)

            self.signals['changed'].emit(rec)

            if fav.once:
                all_favorites.remove(fav)
                break

        # done with this one favorite
        return True
