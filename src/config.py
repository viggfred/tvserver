__all__ = [ 'config' ]

import os
import sys
import logging

from kaa.base.config import Var, Group, Dict, List, Config

import freevo.conf

# get logging object
log = logging.getLogger()

config = Config(desc=_('TV Server configuration'), schema=[
    Var(name='livetv_url', default='224.224.224.10',
        desc=('streaming url for live tv')),

    # record group
    Group(name='record', desc=_('record settings'), schema=[
    Var(name='start_padding', default=60,
        desc=_('try to start all recordings before their time with the given padding')),
    Var(name='stop_padding', default=180,
        desc=_('try to keep the recording running for the given padding')),
    Var(name='filemask', default='%%m-%%d %%H:%%M %(progname)s - %(title)s',
        desc=_('default filemask for recordings')),
    Var(name='dir', default='',
        desc=_('directory where to store recordings')) ]),

    # epg group
    Group(name='epg', desc=_('epg settings'), schema=[
    Var(name='database', default='$(DATADIR)/epg.db',
        desc=_('Filename for the sqlite database file')),
    Dict(name='mapping', type=unicode, schema=Var(type=unicode),
        desc=_('EPG channel mapping'))])
    ])

config.load('/etc/freevo/tvserver.conf')
# if started as user add personal config file
if os.getuid() > 0:
    cfgdir = os.path.expanduser('~/.freevo')
    config.load(os.path.join(cfgdir, 'tvserver.conf'))

# save the file again in case it did not exist or the variables changed
config.save()
