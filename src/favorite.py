# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# favorite.py - Favorite for the TVServer Client
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
# Copyright (C) 2008 Dirk Meyer, et al.
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

__all__ = [ 'Favorite', 'Favorites' ]

# python imports
import time


class Favorite(object):
    """
    A favorite object from the tvserver
    """
    def __init__(self, link, *args):
        """
        The init function creates the object. The parameters are the complete
        list of the favorite_list return.
        """
        self.id, self.title, self.channels, self.priority, self.days, self.times, \
                 self.one_shot, self.substring = args
        self._link = link

    def remove(self, id):
        """
        remove the favorite
        """
        return self._link.favorite_remove(self.id)

    def modify(self, id, **kwargs):
        """
        modify the favorite
        """
        return self._link.favorite_modify(self.id, **kwargs)


class Favorites(list):
    """
    List of Favorite objects
    """
    def __init__(self, link):
        """
        Create Favorites list
        """
        super(Favorites, self).__init__()
        self._link = link

    def _clear(self):
        """
        Clear the list
        """
        while self:
            self.pop(0)

    def _update(self, favorites):
        """
        Handle updated list from tvserver
        """
        for f in favorites:
            for localf in self:
                if localf.id == f[0]:
                    favorites.remove(localf)
                    break
            self.append(Favorite(self._link, *f))

    def get(self, title, channel, start, stop):
        """
        Get favorite based on title, channel, start and stop time.
        """
        day = min(time.localtime(start)[6] + 1, 6)
        for f in self:
            if title == f.title and channel in f.channels and day in f.days:
                return f
        return None

    def update(self):
        """
        Check list of favorites against EPG and update
        """
        return self._link.favorite_update()

    def add(self, title, channels, days, times, priority, once):
        """
        add a favorite

        @param channels: list of channel names are 'ANY'
        @param days: list of days ( 0 = Sunday - 6 = Saturday ) or 'ANY'
        @param times: list of hh:mm-hh:mm or 'ANY'
        @param priority: priority for the recordings
        @param once: True if only one recodring should be made
        """
        return self._link.favorite_add(title, channels, priority, days, times, once)

    def remove(self, id):
        """
        remove a favorite

        @param id: id of the favorite
        """
        return self._link.favorite_remove(id)

    def modify(self, id, **kwargs):
        """
        modify the favorite

        @param id: id of the favorite
        """
        return self._link.favorite_modify(id, **kwargs)
