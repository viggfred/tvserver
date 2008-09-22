# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# TVServer Interface
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

# import some classes
from recording import Recording
from favorite import Favorite

# client connection
_client = None

# list of recordings, favorites and signals that
# will be set on connect
recordings = None
favorites = None
signals = None

def connect(address, password=''):
    """
    Connect to a remote TVServer as client
    """
    from rpc import TVServer
    global _client
    global recordings
    global favorites
    global signals
    _client = TVServer(address, password)
    recordings = _client.recordings
    favorites = _client.favorites
    signals = _client.signals

def wait():
    """
    Wait until the client is connected to the TVServer
    """
    return signals.subset('connected').any()

def is_connected():
    """
    Return if the client is connected to the TVServer
    """
    return _client and _client.connected
