__all__ = [ 'config' ]

import os
import sys
import logging

from kaa.config import Var, Group, Dict, List, Config
import kaa.epg

import freevo.conf

# get logging object
log = logging.getLogger()

config = Config(desc=_('TV Server configuration'), schema=[
    Var(name='loglevel', type=('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'),
        default='INFO',
        desc=_('The log level of the server: CRITICAL, ERROR, WARNING, INFO, DEBUG.')),
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
    Group(name='epg', desc=_('EPG settings'), schema=[
    Var(name='database', default=freevo.conf.datafile('epg.sqlite'),
        desc=_('epg database file'))
    ])
    ])
# Now add the source config
sources = kaa.epg.sources.items()
sources.sort(lambda x,y: cmp(x[0], y[0]))
for name, module in sources:
    config.epg.add_variable(name, module.config)

# EPG mapping
config.epg.add_variable('mapping', Dict(name='mapping', type=unicode,
                                        schema=Var(type=unicode),
                                        desc=_('EPG channel mapping')))

config.load('/etc/freevo/tvserver.conf')
# if started as user add personal config file
if os.getuid() > 0:
    cfgdir = os.path.expanduser('~/.freevo')
    config.load(os.path.join(cfgdir, 'tvserver.conf'))

# save the file again in case it did not exist or the variables changed
config.save()

# check if a record dir is set
if not config.record.dir or not os.path.isdir(config.record.dir):
    log.error('Please set record.dir to a valid directory.')
    log.error('Check the global config file /etc/freevo/tvserver.conf.')
    if os.getuid() > 0:
        log.error('The personal config file is %s',
                  os.path.join(cfgdir, 'tvserver.conf'))
    sys.exit(0)
