__all__ = [ 'config' ]

import os
import sys
import logging

from kaa.config import Var, Group, Dict, List, Config

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
        desc=_('epg database file')),

    # XMLTV settings
    Group(name='xmltv', desc=_('''
    XMLTV settings

    You can use a xmltv rabber to populate the epg database. To activate the xmltv
    grabber you need to set 'activate' to True and specify a data_file which already
    contains the current listing or define a grabber to fetch the listings.
    Optionally you can define arguments for that grabber and the location of a
    sort program to sort the data after the grabber has finished.
    '''), desc_type='group', schema = [
    Var(name='activate', default=False,
        desc=_('Use XMLTV file to populate database.')),
    Var(name='data_file', default='',
        desc=_('Location of XMLTV data file.')),
    Var(name='grabber', default='',
        desc=_('If you want to run an XMLTV grabber to fetch your listings\n'
               'set this to the full path of your grabber program plus any\n'
               'additional arguments.')),
    Var(name='days', default=5,
        desc=_('How many days of XMLTV data you want to fetch.')),
    Var(name='sort', default='',
        desc=_('Set this to the path of the tv_sort program if you need to\n'
               'sort your listings.')),
    ]),

    # Zap2it settings
    Group(name='zap2it', desc=_('''
    Zap2it settings

    Add more doc here please!
    '''), desc_type='group', schema = [
    Var(name='activate', default=False,
        desc=_('Use Zap2it service to populate database.')),
    Var(name='username', default='',
        desc=_('Zap2it username.')),
    Var(name='password', default='',
        desc=_('Zap2it password.')),
    ]),

    # VDR settings
    Group(name='vdr', desc=_('''
    VDR settings

    Add more doc here please!
    '''), desc_type='group', schema = [
    Var(name='activate', default=False,
        desc=_('Use VDR to populate the database.')),
    Var(name='dir', default='/video',
        desc=_('VDR main directory.')),
    Var(name='channels_file', default='channels.conf',
        desc=_('VDR channels file name.')),
    Var(name='epg_file', default='epg.data',
        desc=_('VDR EPG file name.')),
    Var(name='host', default='localhost',
        desc=_('VDR SVDRP host.')),
    Var(name='port', default=2001,
        desc=_('VDR SVDRP port.')),
    Var(name='access_by', type=('name', 'sid' 'rid'), default='sid',
        desc=_('Which field to access channels by: name, sid (service id), \n'+
               'or rid (radio id).')),
    Var(name='limit_channels', type=('epg', 'chan' 'both'), default='chan',
        desc=_('Limit channels added to those found in the EPG file, the \n'+
               'channels file, or both.  Values: epg, chan, both')),
    ]),

    # EPG mapping
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

# check if a record dir is set
if not config.record.dir or not os.path.isdir(config.record.dir):
    log.error('Please set record.dir to a valid directory.')
    log.error('Check the global config file /etc/freevo/tvserver.conf.')
    if os.getuid() > 0:
        log.error('The personal config file is %s',
                  os.path.join(cfgdir, 'tvserver.conf'))
    sys.exit(0)
