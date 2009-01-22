import time
import sys
import functools

import kaa
import kaa.rpc
import kaa.epg
import tvserver

@kaa.coroutine()
def main():
    tvserver.connect('192.168.2.4:7600')
    yield tvserver.wait()
    if 0:
        yield kaa.epg.update()
        yield tvserver.favorites.update()
    if 0:
        for r in tvserver.recordings:
            print r
    if 1:
        t = int(time.time())
        yield tvserver.recordings.schedule('test', 'Das Erste', 10, t+4, t+10, start_padding=0, stop_padding=0)
    if 0:
        yield server.recording_remove(2)
    if 0:
        print tvserver.favorites
    if 0:
        print (yield tvserver.favorites.add(
            u'Tagesschau', [ 'Das Erste' ], 50, [ 0, 1, 2, 3, 4, 5, 6 ],
            [u'20:00-20:00'], False, False))
    if 0:
        print (yield tvserver.favorites.remove(0))
    if 0:
        print (yield tvserver.favorites.modify(0, priority=20))
    if 0:
        print (yield kaa.epg.search(title=kaa.epg.QExpr('like', u'tagesschau')))

    kaa.OneShotTimer(sys.exit, 0).start(1)

main()
kaa.main.run()
