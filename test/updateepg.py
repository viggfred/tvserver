import time
import sys
import kaa
import kaa.rpc
import kaa.epg

class Events(object):

    @kaa.rpc.expose()
    def recording_update(self, *recordings):
        for r in recordings:
            print r

    @kaa.rpc.expose()
    def identify(self):
        return 'client'
    
    @kaa.rpc.expose()
    def favorite_update(self, *fav):
        for f in fav:
            print f

@kaa.coroutine()
def main():
    c = kaa.rpc.Client('192.168.2.2:7600')
    c.connect(Events())
    kaa.epg.connect('192.168.2.2:7601')
    if 0:
        yield kaa.epg.update()
        yield c.rpc('favorite_update')
    if 1:
        print (yield c.rpc('recording_list'))
    if 0:
        yield c.rpc('recording_add', 'Tagesschau', 'Das Erste', 10,
                    int(time.time())+10000, time.time()+10200)
    if 0:
        yield c.rpc('recording_remove', 2)
    if 1:
        print (yield c.rpc('favorite_list'))
    if 0:
        print (yield c.rpc('favorite_add', u'Tagesschau', [ 'Das Erste' ],
                           50, [ 0, 1, 2, 3, 4, 5, 6 ], [u'20:00-20:00'], False, False))
    if 0:
        print (yield c.rpc('favorite_remove', 0))
    if 0:
        print (yield c.rpc('favorite_modify', 0, priority=20))
    if 1:
        print (yield kaa.epg.search(title=kaa.epg.QExpr('like', u'tagesschau')))
        
    kaa.OneShotTimer(sys.exit, 0).start(1)

main()
kaa.main.run()
