from recording import Recording
from favorite import Favorite

_client = None

recordings = None
favorites = None
signals = None

def connect(address, password=''):
    from rpc import TVServer
    global _client
    global recordings
    global favorites
    global signals
    _client = TVServer(address, password)
    recordings = _client.recordings
    favorites = _client.favorites
    signals = _client.signals

def wait():
    return signals.subset('connected').any()

def is_connected():
    return _client and _client.connected
