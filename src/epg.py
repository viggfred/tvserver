# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# epg.py - EPG handling for the recordserver
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
import sys
import time
import logging

# kaa imports
import kaa.notifier

# freevo imports
import kaa.epg

# record imports
from record_types import *
from recording import Recording
from config import config

# get logging object
log = logging.getLogger('record')


class EPG(object):


    # -------------------------------------------------------------------------
    # Public Interface
    # -------------------------------------------------------------------------

    def __init__(self):
        self.signals = {
            'changed': kaa.notifier.Signal(),
            'updated': kaa.notifier.Signal()
            }
        self.updating = False

        # update config.epg.mapping information
        channels = [ c.name for c in self.channels() ] + [ u'' ]
        mapping = config.epg._cfg_get('mapping')
        mapping._schema._type = channels
        txt = '\nKnown channels are '
        for c in channels:
            if len(txt) + len(c) >= 78:
                mapping._desc += txt.rstrip() + '\n'
                txt = ''
            txt += c + ', '
        mapping._desc += txt.rstrip(', ')
        config.save()


    def channels(self):
        """
        Return list of channels.
        """
        return kaa.epg.get_channels()


    @kaa.notifier.yield_execution()
    def check(self, recordings, favorites):
        """
        Check recordings
        """
        # Note: this function takes a lot of time. But we don't need to call
        # YieldContinue because every kaa.epg search yield will go back to
        # the main loop.
        ctime = time.time() + 60 * 15
        to_check = [ r for r in recordings if r.start - r.start_padding > ctime \
                     and r.status in (CONFLICT, SCHEDULED) ]
        # check recordings
        while to_check:
            # get one recording to check
            rec = to_check.pop(0)

            # Search epg for that recording. The recording should be at the
            # same time, maybe it has moved +- 20 minutes. If the program
            # moved a larger time interval, it won't be found again.
            interval = (rec.start - 20 * 60, rec.start + 20 * 60)

            channel = kaa.epg.get_channel(rec.channel)
            if not channel:
                log.error('unable to find %s in epg database', rec.channel)
                continue

            # Try to find the exact title again.
            wait = kaa.epg.search(title = rec.name, channel=channel, time = interval)
            yield wait
            results = wait()

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
                    continue

            # check if attributes changed
            for attr in ('description', 'episode', 'subtitle'):
                newattr = getattr(epginfo, attr)
                oldattr = getattr(rec, attr)
                if (newattr or oldattr) and newattr != oldattr:
                    log.info('%s changed for %s', attr, rec.name)
                    setattr(rec, attr, getattr(epginfo, attr))

        # check favorites
        to_check = favorites[:]
        while to_check:
            # get favorite to check
            fav = to_check.pop(0)

            # Now search the db.
            # Note: we can't use keyword searching here because it won't match
            # some favorite titles when they have short names.

            if fav.substring:
                # unable to do that right now
                wait = kaa.epg.search(keywords=fav.name)
            else:
                # 'like' search
                wait = kaa.epg.search(title=kaa.epg.QExpr('like', fav.name))
            yield wait
            listing = wait()

            now = time.time()
            for p in listing:
                if not fav.match(p.title, p.channel.name, p.start):
                    continue
                if p.stop < now:
                    # do not add old stuff
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
                    favorites.remove(fav)
                    break


    @kaa.notifier.yield_execution()
    def update(self):
        """
        Update the epg data in the epg server
        """
        if self.updating:
            log.info('epg update in progress')
            yield False

        self.updating = True
        sources = kaa.epg.sources.items()[:]
        sources.sort(lambda x,y: cmp(x[0], y[0]))

        while sources:
            name, module = sources.pop(0)
            if not module.config.activate:
                log.info('skip epg update on %s', name)
                continue

            if kaa.epg.guide.status == kaa.epg.CONNECTED:
                log.info('start epg update on %s', name)
                wait = kaa.epg.guide.update(name)
                yield wait
                try:
                    wait()
                except Exception, e:
                    log.exception(e)
            log.info('done epg update on %s', name)

        log.info('epg update complete')
        self.updating = False
        self.signals['updated'].emit()
