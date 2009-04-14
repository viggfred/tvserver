# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# epg.py - EPG handling for the tvserver
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
# Copyright (C) 2006-2008 Dirk Meyer, et al.
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

# python imports
import os
import sys
import time
import logging

# kaa imports
import kaa
import kaa.epg

# record imports
from recording import Recording, SCHEDULED, CONFLICT
from config import config

# get logging object
log = logging.getLogger('tvserver')

signals = {
    'changed': kaa.Signal(),
}

def init():
    # get kaa.epg database filename
    db = os.path.expandvars(os.path.expanduser(config.epg.database)).\
         replace('$(HOME)', os.environ.get('HOME'))
    kaa.epg.load(db)

    # update config.epg.mapping information
#     channels = [ c.name for c in kaa.epg.get_channels() ] + [ u'' ]
#     mapping = config.epg._cfg_get('mapping')
#     mapping._schema._type = channels
#     txt = '\nKnown channels are '
#     for c in channels:
#         if len(txt) + len(c) >= 78:
#             mapping._desc += txt.rstrip() + '\n'
#             txt = ''
#         txt += c + ', '
#     mapping._desc += txt.rstrip(', ')
#     config.save()


@kaa.coroutine()
def check(recordings, favorites):
    """
    Check recordings

    @note: this function modifies the given recordings and favorites list
    """
    ctime = int(time.time()) + 60 * 15
    to_check = [ r for r in recordings if r.start - r.start_padding > ctime and r.status in (CONFLICT, SCHEDULED) ]
    # check recordings
    while to_check:
        if len(to_check) % 10 == 0:
            # back to mainloop
            yield kaa.NotFinished
        # get one recording to check
        rec = to_check.pop(0)
        check_recording(rec)
    # check favorites
    to_check = favorites[:]
    while to_check:
        if len(to_check) % 10 == 0:
            # back to mainloop
            yield kaa.NotFinished
        # get favorite to check
        fav = to_check.pop(0)
        check_favorite(fav, recordings)


def check_recording(rec):
    """
    Search epg for that recording. The recording should be at the
    same time, maybe it has moved +- 20 minutes. If the program
    moved a larger time interval, it won't be found again.
    """
    interval = (rec.start - 20 * 60, rec.start + 20 * 60)
    channel = kaa.epg.get_channel(rec.channel)
    if not channel:
        log.error('unable to find %s in epg database', rec.channel)
        return
    # Try to find the exact title again.
    results = kaa.epg.search(title=rec.name, channel=channel, time=interval)
    for epginfo in results:
        # check all results
        if epginfo.start_timestamp == rec.start and epginfo.stop_timestamp == rec.stop:
            # found the recording
            log.debug('found recording: %s', rec.name)
            break
    else:
        # try to find it
        for epginfo in results:
            if rec.start - 20 * 60 < epginfo.start_timestamp < rec.start + 20 * 60:
                # found it again, set new start and stop time
                old_info = str(rec)
                rec.start = epginfo.start_timestamp
                rec.stop = epginfo.stop_timestamp
                log.info('changed schedule\n%s\n%s' % (old_info, rec))
                signals['changed'].emit(rec)
                break
        else:
            log.info('unable to find recording in epg:\n%s' % rec)
            return
    # check if attributes changed
    for attr in ('description', 'episode', 'subtitle'):
        newattr = getattr(epginfo, attr)
        oldattr = getattr(rec, attr)
        if (newattr or oldattr) and newattr != oldattr:
            log.info('%s changed for %s', attr, rec.name)
            setattr(rec, attr, getattr(epginfo, attr))


def check_favorite(fav, recordings):
    """
    Check the given favorite against the db and add recordings
    """
    # Note: we can't use keyword searching here because it won't match
    # some favorite titles when they have short names.
    if fav.substring:
        # unable to do that right now
        listing = kaa.epg.search(keywords=fav.name)
    else:
        # 'like' search
        listing = kaa.epg.search(title=kaa.epg.QExpr('like', fav.name))
    now = time.time()
    for p in listing:
        if not fav.match(p.title, p.channel.name, p.start_timestamp):
            continue
        if p.stop_timestamp < now:
            # do not add old stuff
            continue
        # we found a new recording.
        rec = Recording(p.title, p.channel.name, fav.priority, p.start_timestamp, p.stop_timestamp,
                  info={ "episode": p.episode, "subtitle": p.subtitle, "description": p.description } )
        if rec in recordings:
            # This does not only avoid adding recordings twice, it
            # also prevents from added a deleted favorite as active
            # again.
            continue
        fav.update_recording(rec)
        recordings.append(rec)
        log.info('added\n%s', rec)
        signals['changed'].emit(rec)
        if fav.once:
            favorites.remove(fav)
            break
