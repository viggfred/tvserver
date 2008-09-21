import time
import logging
import tvserver.devices
import kaa

@kaa.coroutine()
def main():
    device = (yield tvserver.devices.get())[0]
    id = device.schedule('Das Erste', int(time.time()) + 5, int(time.time()) + 20, 'foo')
    yield kaa.delay(6)
    device.remove(id)

logging.getLogger().setLevel(logging.DEBUG)

main()
kaa.main.run()
