# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# conflict.py - resolve conflicts for the recordserver
# -----------------------------------------------------------------------------
# $Id$
#
# This module resolves conflicts by choosing cards for the different recordings
# to record as much as possible with the best combination.
#
# Recordings have priorities between 40 and 100 if the are low priority and
# around 500 for medium and between 1000 and 1100 for high priority
# recordings.
# As a default favorites get a priority of 50, manual records of 1000 to make
# sure they always win. Important favorites can be adjusted in the priority.
#
# Cards have a quality between 1 (poor) and 10 (best). The module will try
# to make sure the best card is used for the highest rated recording.
#
# A conflict only in start and stop padding gives minus points based on the
# number of involved programs and the rating of them.
#
# Algorithm:
# sum up recording prio * (devices priority * 0.1 + 1)
# meaning the devices have a priority between 1.1 and 2
# After that reduce the rating with the rating of the overlapping
# (see function rate_conflict for documentation)
#
# Note: The algorithm isn't perfect. In fact, it can't be perfect because
# people have a different oppinion what is the correct way to resolve the
# conflict. Maybe it should also contain the number of seconds in a recording.
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


__all__ = [ 'resolve', 'clear_cache' ]

# python imports
import logging
import time

# record imports
import recorder
from record_types import *

# get logging object
log = logging.getLogger('conflict')


class Device(object):
    def __init__(self, recorder=None):
        self.recorder     = None
        self.rating       = 0
        self.listing      = []
        self.all_channels = []
        self.rec          = []
        if recorder:
            self.recorder = recorder
            self.rating   = recorder.rating
            self.listing  = recorder.current_bouquets
            for l in self.listing:
                self.all_channels += l


    def append(self, recording):
        """
        Append recording to list of possible and return True. If not possible,
        do not append and return False.
        """
        if not self.recorder:
            # dummy recorder, it is always possible not record it
            self.rec.append(recording)
            return True

        recording.conflict_padding = []

        # Set status to False if the recording is currently recording
        # but not on this device.
        if recording.status == RECORDING and \
               recording.recorder != self.recorder:
            return False

        if not recording.channel in self.all_channels:
            # channel not supported
            return False

        if not len(self.rec):
            # first recording, has to fit
            self.rec.append(recording)
            return True

        # get the bouquet where the current recordings are
        bouquet = [ x for x in self.listing if recording.channel in x ][0]
        
        # Get all recordings conflicting with the current one by time. based on
        # a sort listing, the others will start before or at the same time as
        # the latest. So when the stop time of an other is before the new start
        # time, it is no conflict. (ignoring padding here for once)
        # If the conflict is only based on the padding, add it to conflict_padding
        
        for r in self.rec:
            if r.channel in bouquet:
                # same bouquet, will always work
                continue
            if r.stop > recording.start:
                # overlapping time, won't work
                return False
            if r.stop + r.stop_padding > recording.start - recording.start_padding:
                # overlapping padding
                recording.conflict_padding.append(r)

        self.rec.append(recording)
        return True


    def remove_last(self):
        self.rec = self.rec[:-1]
        

def scan(recordings):
    """
    Scan the schedule for conflicts. A conflict is a list of recordings
    with overlapping times.
    """
    for r in recordings:
        r.start -= r.start_padding
        r.stop  += r.stop_padding
    # Sort by start time
    recordings.sort(lambda l, o: cmp(l.start,o.start))

    # all conflicts found
    conflicts = []

    # recordings already scanned
    scanned   = []

    # get current time
    ctime = time.time()
    
    # Check all recordings in the list for conflicts
    for r in recordings:
        if r in scanned:
            # Already marked as conflict
            continue
        current = []
        # Set stop time for the conflict area to current stop time. The
        # start time doesn't matter since the recordings are sorted by
        # start time and this is the first
        stop = r.stop
        while True:
            for c in recordings[recordings.index(r)+1:]:
                # Check all recordings after the current 'r' if the
                # conflict
                if c in scanned:
                    # Already marked as conflict
                    continue
                if c.start < stop:
                    # Found a conflict here. Mark the item as conflict and
                    # add to the current conflict list
                    current.append(c)
                    scanned.append(c)
                    # Get new stop time and repeat the scanning with it
                    # starting from 'r' + 1
                    stop = max(stop, c.stop)
                    break
            else:
                # No new conflicts found, the while True is done
                break
        if current:
            # Conflict found. Mark the current 'r' as conflict and
            # add it to the conflict list. 'current' will be reset to
            # [] for the next scanning to get groups of conflicts
            conflicts.append([ r ] + current)

    for r in recordings:
        r.start += r.start_padding
        r.stop  -= r.stop_padding
    return conflicts


def rate_conflict(clist):
    """
    Rate a conflict list created by 'scan'. Result is a negative value
    about the conflict lists.
    """
    number   = 0
    prio     = 0
    ret      = 0
    if not clist:
        return 0
    # Ideas from Sep. 02
    #
    # Rating (will be called when everything is set, for all devices except NULL)
    # for r in recordings:
    #    result += (0.1 * dev.prio) + 1 * (rec.prio + rec.length * 0.001) - cr
    # and cr is based on all recordings starting incl. padding before r, overlap
    # with r and are not in the same bouquet as r.
    # so cr is AveragePrio * 0.01 + overlapping time in minutes
    for c in clist:
        for pos, r1 in enumerate(c[:-1]):
          # check all pairs of conflicts (stop from x with start from x + 1)
          # next recording
          r2 = c[pos+1]
          # overlapping time in seconds
          time_diff = r1.stop + r1.stop_padding - r2.start - r2.start_padding
          # min priority of the both recordings
          min_prio = min(r1.priority, r2.priority)
          # average priority of the both recordings
          average_prio = (r1.priority + r2.priority) / 2

          # Algorithm for the overlapping rating detection:
          # min_prio / 2 (difference between 5 card types) +
          # average_prio / 100 (low priority in algorithm) +
          # number of overlapping minutes
          ret -= min_prio / 2 + average_prio / 100 + time_diff / 60
    return ret


def rate(devices, best_rating):
    """
    Rate device/recording settings. If the rating is better then best_rating,
    store the choosen recorder in the recording item.
    """
    rating = 0
    for d in devices[:-1]:
        for r in d.rec:
            rating += (0.1 * d.rating + 1) * r.priority
            if len(r.conflict_padding):
                rating += rate_conflict([[ r ] + r.conflict_padding])

    if rating > best_rating:
        # remember
        best_rating = rating

        for d in devices[:-1]:
            for r in d.rec:
                if r.status != RECORDING:
                    r.status = SCHEDULED
                    r.recorder = d.recorder
                    r.respect_start_padding = True
                    r.respect_stop_padding = True
                    if r.conflict_padding:
                        # the start_padding conflicts with the stop paddings
                        # the recordings in r.conflict_padding. Fix it by
                        # removing the padding
                        # FIXME: maybe start != stop
                        r.respect_start_padding = False
                        for c in r.conflict_padding:
                            c.respect_stop_padding = False
        for r in devices[-1].rec:
            r.status   = CONFLICT
            r.recorder = None
    return best_rating



def check(devices, fixed, to_check, best_rating, dropped=1):
    """
    Check all possible combinations from the recordings in to_check on all
    devices. Call recursive again.
    """
    if not dropped and len(devices[-1].rec):
        # There was a solution without any recordings dropped.
        # It can't get better because devices[-1].rec already contains
        # at least one recording
        return best_rating, dropped

    if not to_check:
        return rate(devices, best_rating), len(devices[-1].rec)

    c = to_check[0]
    for d in devices:
        if d.append(c):
            best_rating, dropped = check(devices, fixed + [ c ], to_check[1:],
                                         best_rating, dropped)
            d.remove_last()
    return best_rating, dropped


# list of devices
_devices = []

def resolve(recordings, recorder):
    """
    Find and resolve conflicts in recordings.
    """
    t1 = time.time()
    if not _devices:
        # create 'devices'
        _devices.append(Device())
        for p in recorder:
            _devices.append(Device(p))
        _devices.sort(lambda l, o: cmp(o.rating,l.rating))

    # sort recordings
    recordings.sort(lambda l, o: cmp(l.start,o.start))

    # resolve recordings
    for c in scan(recordings):
        if 0:
            info = 'found conflict:\n'
            log.info(info)
        check(_devices, [], c, 0)
        if 0:
            info ='solved by setting:\n'
            for r in c:
                info += '%s\n' % str(r)
            log.debug(info)
    t2 = time.time()
    log.info('resolve conflict took %s secs' % (t2-t1))


def clear_cache():
    """
    Clear the global conflict resolve cache
    """
    global _devices
    _devices = []
