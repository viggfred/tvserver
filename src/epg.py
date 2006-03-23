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
import sys
import time
import logging

# kaa imports
from kaa.notifier import OneShotTimer, Timer, Signal, execute_in_timer

# freevo imports
import kaa.epg

# record imports
from record_types import *
from recording import Recording
from config import config

# get logging object
log = logging.getLogger('record')


class EPG(object):

    def __init__(self):
        self.signals = { 'changed': Signal() }


    def channels(self):
        """
        Return list of channels.
        """
        return kaa.epg.get_channels()


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


    @execute_in_timer(Timer, 0.01)
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

        channel = kaa.epg.get_channel(rec.channel)
        if not channel:
            log.error('unable to find %s in epg database', rec.channel)
            return True
            
        # try to find the exact title again
        results = kaa.epg.search(title = rec.name, channel=channel, time = interval)

        for epginfo in results:
            # check all results
            if epginfo.start == rec.start and epginfo.stop == rec.stop:
                # found the recording
                log.debug('found recording: %s', rec.name)
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

        # check if attributes changed 
        for attr in ('description', 'episode', 'subtitle'):
            newattr = getattr(epginfo, attr)
            oldattr = getattr(rec, attr)
            if (newattr or oldattr) and newattr != oldattr:
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


    @execute_in_timer(Timer, 0.01)
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
        # Note: we can't use keyword searching here because it won't match
        # some favorite titles when they have short names.
        if fav.substring:
            # unable to do that right now
            listing = kaa.epg.search(keywords=fav.name)
        else:
            listing = kaa.epg.search(title=kaa.epg.QExpr('like', fav.name))

        for p in listing:
            if not fav.match(p.title, p.channel.name, p.start):
                continue

            rec = Recording(p.title, p.channel.id, fav.priority,
                            p.start, p.stop,
			    info={ "episode":p.episode,
				   "subtitle":p.subtitle,
				   "description":p.description } )

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



def update():
    """
    Update epg data.
    """
    def update_progress(cur, total):
        n = 0
        if total > 0:
            n = int((cur / float(total)) * 50)
        sys.stdout.write("|%51s| %d / %d\r" % (("="*n + ">").ljust(51), cur, total))
        sys.stdout.flush()
        if cur == total:
            print

    guide = kaa.epg.guide

    guide.signals["update_progress"].connect(update_progress)
    guide.signals["updated"].connect(sys.exit)

    if config.epg.xmltv.activate == 1:

        if not config.epg.xmltv.data_file:
            log.error('XMLTV gabber not supported yet. Please download the')
            log.error('file manually and set epg.xmltv.data_file')
        else:

            data_file = str(config.epg.xmltv.data_file)
            log.info('loading data into EPG...')
            guide.update("xmltv", data_file)
            
    else:
        print 'not configured to use xmltv'


    if config.epg.zap2it.activate == 1:
        guide.update("zap2it", username=str(config.epg.zap2it.username), 
                               passwd=str(config.epg.zap2it.password))

    else:
        print 'not configured to use Zap2it'


    if config.epg.vdr.activate == 1:
        print 'update epg based on vdr data'
        guide.update("vdr", vdr_dir=str(config.epg.vdr.dir), 
                     channels_file=str(config.epg.vdr.channels_file), 
                     epg_file=str(config.epg.vdr.epg_file),
                     host=str(config.epg.vdr.host), port=int(config.epg.vdr.port), 
                     access_by=str(config.epg.vdr.access_by), 
                     limit_channels=str(config.epg.vdr.limit_channels))

    else:
        print 'not configured to use VDR'
