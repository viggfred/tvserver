import sys
import logging

import kaa.notifier
from kaa.base.strutils import format

import freevo.ipc
from freevo.ipc import tvserver

# tv server
SERVER = {'type': 'home-theatre', 'module': 'tvserver'}

def favorite_describe(id):
    """
    """
    try:
        id = int(id)
    except:
        print '\rbad id: %s' % id
        return
    for f in tvserver.favorites.list():
        if f.id == id:
            break
    else:
        print '\rbad id: %s' % id
        return
    s = format('\rFavorite %s', f.title)
    if f.substring:
        s += ' (substring)'
    if f.one_shot:
        s += ' (oneshot)'
    s += format('\nchannels:\n  %s', u'\n  '.join(f.channels))
    print s


def user_input():
    input = sys.stdin.readline().strip()
    if input.find(' ') > 0:
        cmd = input[:input.find(' ')].strip()
        arg = input[input.find(' '):].strip()
    else:
        cmd = input
        arg = ''
        
    if cmd == 'help':
        print '\rpossible commands:'
        print
        print 'rssh commands:'
        print '  help                       print this help'
        print '  exit, bye, quit, q         exit interactive mode'
        print
        print 'record commands:'
        print '  rl                         recordings list'
        print '  rd id                      recording describe'
        print
        print 'favorite commands:'
        print '  fu                         favorites update'
        print '  fl                         favorites list'
        print '  fd id                      favorites describe'
        print

    elif cmd in ('exit', 'bye', 'quit'):
        print
        sys.exit(0)
    elif cmd == '':
        pass
    elif cmd == 'rl':
        print 'not implemented yet'
    elif cmd == 'rd':
        print 'not implemented yet'
    elif cmd == 'fu':
        tvserver.favorites.update()
    elif cmd == 'fl':
        for f in tvserver.favorites.list():
            print u'\r%3d: %s' % (f.id, f.title)
    elif cmd == 'fd':
        favorite_describe(arg)
    else:
        print '\rbad command \'%s\'' % input
    print '\r> ',
    sys.__stdout__.flush()

        
def new_entity(entity):
    if not entity.matches(SERVER):
        return True
    print 'found'
    print '> ',
    sys.__stdout__.flush()
    # register stdin for reading
    kaa.notifier.SocketDispatcher(user_input).register(sys.stdin)
    
mbus = freevo.ipc.Instance('tvcontrol')
mbus.signals['new-entity'].connect(new_entity)

logging.getLogger('record').setLevel(logging.WARNING)

print 'TV Server Shell'
print '-------------------------'
print
print 'waiting for tvserver ...',
sys.__stdout__.flush()
