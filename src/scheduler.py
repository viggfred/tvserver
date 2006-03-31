# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# scheduler.py - Schedule future recordings to devices
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
import time
import logging

# record imports
import recorder
from record_types import *
from conflict import Conflict

# get logging object
log = logging.getLogger('record')


class Scheduler(object):

    def __init__(self, callback):
        self.callback = callback
        self.conflict = Conflict(self.conflict_callback)


    def schedule(self, recordings):

        # get current time
        ctime = time.time()

        # remeber data (before copy and deleting any)
        self.recordings = recordings

        # create a new list of recordings based on the status
        recordings = [ r for r in recordings if r.status in \
                       (CONFLICT, SCHEDULED, RECORDING) ]

        # new dict for schedule information. Each entry is r.status,
        # r.recorder, r.respect_start_padding, r.respect_stop_padding
        schedule = {}

        # sort by start time
        recordings.sort(lambda l, o: cmp(l.start,o.start))

        for r in recordings[:]:
            # check recordings we missed (stop passed or start over 10
            # minutes ago), remember that in status and remove this
            # recording from the list.
            if r.stop < ctime or (r.start + 600 < ctime and r.status != RECORDING):
                schedule[r.id] = [ MISSED, None, True, True ]
                recordings.remove(r)

            elif r.status == RECORDING:
                # mark current running recordings
                schedule[r.id] = [ r.status, r.recorder, r.respect_start_padding, \
                                   r.respect_stop_padding ]

            else:
                device = recorder.get_recorder(r.channel)
                if device:
                    # set to the best recorder for each recording
                    schedule[r.id] = [ SCHEDULED, device, True, True ]
                else:
                    # no recorder found, remove from the list
                    schedule[r.id] = [ CONFLICT, None, True, True ]
                    recordings.remove(r)

        # recordings is a list fo current running or future recordings
        # detect possible conflicts (delayed to avoid blocking the main loop)
        self.conflict.scan(recordings, schedule)


    def conflict_callback(self, schedule):
        for r in self.recordings:
            if r.id in schedule:
                r.status, r.recorder, r.respect_start_padding, \
                          r.respect_stop_padding = schedule[r.id]
            elif r.status in (CONFLICT, RECORDING, SCHEDULED):
                log.error('missing info for %s', r)

        self.callback()
