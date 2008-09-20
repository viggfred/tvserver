import time
import sys
import functools

import kaa
import kaa.rpc
import kaa.epg
from kaa.utils import localtime2utc

class TVServer(object):

    def connect(self, ip, port):
        self._wait = kaa.InProgress()
        self._client = kaa.rpc.Client('%s:%s' % (ip, port))
        self._client.connect(self)
        kaa.epg.connect('%s:%s' % (ip, port+1))
        return self._wait

    @kaa.rpc.expose()
    def recording_update(self, *recordings):
        for r in recordings:
            print r

    @kaa.rpc.expose()
    def identify(self):
        kaa.OneShotTimer(self._wait.finish, None).start(0)
        return 'client'

    @kaa.rpc.expose()
    def favorite_update(self, *fav):
        for f in fav:
            print f

    def __getattr__(self, attr):
        return functools.partial(self._client.rpc, attr)
    
@kaa.coroutine()
def main():
    server = TVServer()
    yield server.connect('192.168.2.2', 7600)
    if 0:
        yield kaa.epg.update()
        yield server.favorite_update()
    if 0:
        print (yield server.recording_list())
    if 1:
        t = int(localtime2utc(time.time()))
        yield server.recording_add('test', 'Das Erste', 10, t+4, t+10, start_padding=0, stop_padding=0)
    if 0:
        yield server.recording_remove(2)
    if 1:
        print (yield server.favorite_list())
    if 0:
        print (yield server.favorite_add(u'Tagesschau', [ 'Das Erste' ],
                           50, [ 0, 1, 2, 3, 4, 5, 6 ], [u'20:00-20:00'], False, False))
    if 0:
        print (yield server.favorite_remove(0))
    if 0:
        print (yield server.favorite_modify(0, priority=20))
    if 1:
        print (yield kaa.epg.search(title=kaa.epg.QExpr('like', u'tagesschau')))

    kaa.OneShotTimer(sys.exit, 0).start(1)

main()
kaa.main.run()
