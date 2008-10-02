import time
import logging
import tvserver.devices
import kaa

@kaa.coroutine()
def main():
    device = (yield tvserver.devices.get())[0]
    print device.multiplexes
    id = device.schedule('ZDF', int(time.time()) + 5, int(time.time()) + 20, 'file:///tmp/foo')
    device.schedule('3sat', int(time.time()) + 10, int(time.time()) + 30, 'file:///tmp/foo2')
    yield kaa.delay(6)
    # device.remove(id)

logging.getLogger().setLevel(logging.DEBUG)

main()
kaa.main.run()
