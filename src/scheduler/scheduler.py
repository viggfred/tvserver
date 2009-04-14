# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# scheduler.py - Schedule future recordings to devices
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
# Copyright (C) 2006,2008 Dirk Meyer, et al.
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
import time
import logging

# kaa imports
import kaa

# record imports
from device import get_device
from recording import SCHEDULED, RECORDING, CONFLICT, MISSED
import conflict

# get logging object
log = logging.getLogger('tvserver')

@kaa.coroutine()
def schedule(recordings):
    # get current time in UTC
    ctime = int(time.time())
    all_recordings = recordings
    # create a new list of recordings based on the status
    recordings = [ r for r in recordings if r.status in \
                   (CONFLICT, SCHEDULED, RECORDING) ]
    # new dict for schedule information. Each entry is r.status,
    # r.device, r.respect_start_padding, r.respect_stop_padding
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
            schedule[r.id] = [ r.status, r.device, r.respect_start_padding, \
                               r.respect_stop_padding ]
        else:
            device = get_device(r.channel)
            if device:
                # set to the best device for each recording
                schedule[r.id] = [ SCHEDULED, device, True, True ]
            else:
                # no device found, remove from the list
                schedule[r.id] = [ CONFLICT, None, True, True ]
                recordings.remove(r)

    # recordings is a list fo current running or future recordings
    # detect possible conflicts (delayed to avoid blocking the main loop)
    schedule = yield conflict.resolve(recordings, schedule)
    for r in all_recordings:
        if r.id in schedule:
            r.status, r.device, r.respect_start_padding, \
                      r.respect_stop_padding = schedule[r.id]
