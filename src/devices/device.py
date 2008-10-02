# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# device.py - template object for specific cards
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

__all__ = [ 'DeviceInterface' ]

# python imports
import os
import socket
import logging

# kaa imports
import kaa
from kaa.config import Config, Group, Var
from kaa.ioctl import ioctl, pack, unpack, IOR

# get logging object
log = logging.getLogger('config')

class DeviceInterface(object):
    """
    Base class for tv cards.
    """
    suffix = 'unknown'

    def __init__(self, type, number):
        self.device = '%s%s' % (type, number)
        self.configured = True
        # create config group
        self.config = Group(desc='%s card %s' % (type.upper(), number), schema =[
            Var(name='priority', default=5,
                desc='priority of the card'),
            Var(name='activate', default=True,
                desc='Set activate to False if the card should not be used') ])

    def _cfg_set_default(self, key, value):
        """
        Set new default value.
        """
        return self.config._cfg_get(key)._cfg_set(value, default=True)

    def _cfg_add(self, var):
        """
        Add a new variable or group to the config. The parameter 'var' can also be
        a list of variables to add.
        """
        if isinstance(var, (list, tuple)):
            for v in var:
                self.config.add_variable(v._name, v)
            return
        return self.config.add_variable(var._name, var)

    def __getattr__(self, attr):
        """
        Get an attribute. If the attribute is in the config variable return
        this, it not use instance object.
        """
        return getattr(self.config, attr)

    def __setattr__(self, attr, value):
        """
        Set an attribute. If the attribute is in the config variable set
        this, it not use instance object.
        """
        if not attr.startswith('_') and hasattr(self, 'config') and \
               hasattr(self.config, attr):
            return setattr(self.config, attr, value)
        super(DeviceInterface, self).__setattr__(attr, value)

    def __str__(self):
        """
        Return a string with some basic information about the card.
        """
        s = 'Priority: %s\n' % self.priority
        if self.activate:
            return s + 'Status: ready to use\n'
        elif not self.configured:
            return s + 'Status: needs configuration\n'
        else:
            return s + 'Status: deactivated\n'


class DVBCard(DeviceInterface):
    """
    DVB card config object
    """
    suffix = 'ts'

    def __init__(self, number):
        super(DVBCard, self).__init__('dvb', number)
        # get adapter based on number
        self.adapter = '/dev/dvb/adapter%s' % number
        # read frontend0 for aditional information
        INFO_ST = '128s10i'
        val = pack( INFO_ST, "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 )
        devfd = os.open(self.adapter + '/frontend0', os.O_TRUNC)
        r = ioctl(devfd, IOR('o', 61, INFO_ST), val)
        os.close(devfd)
        val = unpack( INFO_ST, r )
        name = val[0]
        if val[1] == 0:
            self.type = 'DVB-S'
            self._cfg_set_default('priority', 10)
        elif val[1] == 1:
            self.type = 'DVB-C'
            self._cfg_set_default('priority', 9)
        elif val[1] == 2:
            self.type = 'DVB-T'
            self._cfg_set_default('priority', 8)
        else:
            # What is that?
            raise SystemError('unknown (%s)' % val[1])
        # special dvb config
        plugin = 'mplayer'
        if kaa.utils.which('dvbstreamer'):
            plugin = 'dvbstreamer'
        self._cfg_add(
            Var(name='plugin', default=plugin,
                desc='plugin to use for this device'))
        # fix name
        if name.find('\0') > 0:
            name = name[:name.find('\0')]
        self.name = name
        log.debug('register dvb device %s' % self.adapter)

    def __str__(self):
        """
        Return a string with some basic information about the card.
        """
        s =  'Adapter: %s\n' % self.adapter
        s += 'Card: %s\n' % self.name
        s += 'Type: %s\n' % self.type
        return s + super(DVBCard, self).__str__()
