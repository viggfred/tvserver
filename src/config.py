import os
import sys
import logging

from freevo.conf import *

# get logging object
log = logging.getLogger()

schema = { 'RECORD_START_PADDING': int,
           'RECORD_STOP_PADDING' : int,
           'SERVER_UID' : int,
           'START_TVDEV': bool }

conf = Config('tvserver.conf', schema)

for key, value in conf.normalize():
    if key.find(' ') == -1:
        globals()[key] = value

if not RECORD_DIR:
    conf.save()
    log.error('Error: record_dir not set')
    log.error('Please check the config file: %s' % conf.filename)
    sys.exit(0)

EPG_FILENAME = EPG_FILENAME.replace('$(DATADIR)', DATADIR)
EPG_MAPPING  = conf['epg mapping']
