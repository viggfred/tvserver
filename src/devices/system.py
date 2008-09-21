# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# system.py - tv card detection and device setup
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# TVServer - A generic TV device wrapper and scheduler
# Copyright (C) 2004-2008 Dirk Meyer, et al.
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

__all__ = [ 'config', 'info', 'get_devices' ]

# python imports
import os
import socket
import logging

# kaa imports
import kaa
from kaa.config import Config, Group, Var

# tvdev imports
from device import DVBCard

# get logging object
log = logging.getLogger('tvdev')

# config object
config = Config(schema=[])
rpcgroup = Group(desc='Remote access to the server', schema=[
    Var(name='address', default='127.0.0.1:7600',
        desc='IP address and port to use for inter-process communication'),
    Var(name='password', default='',
        desc='Password to secure the communication')])
config.add_variable(name='rpc', value=rpcgroup)
config.add_variable(name='directory', value=Var(default=os.path.expanduser('~/Videos'),
        desc='Default recording directory'))

# list of detected cards
log.info('Detecting DVB cards.')
info = []
for i in range(10):
    if os.path.isdir('/dev/dvb/adapter%s' % i):
        try:
            card = DVBCard(i)
            # add card
            info.append(card)
            # add to global config object
            config.add_variable(name=card.device, value=card.config)
            log.debug('DVB card detected as dvb%s' % i)
        except OSError:
            # likely no device attached
            pass
        except:
            log.exception('dvb detection')

_devices = None

@kaa.coroutine()
def get_devices():
    global _devices
    if _devices is not None:
        yield _devices
    # list of devices
    _devices = []
    for i in info:
        if not i.activate:
            # device is not working or should not be used
            if not i.configured:
                log.info('skipping %s, not configured' % i.device)
            else:
                log.info('skipping %s' % i.device)
            continue
        exec('from plugins.%s import Plugin' % i.plugin)
        device = Plugin(i)
        yield device.initialized
        _devices.append(device)
    yield _devices
