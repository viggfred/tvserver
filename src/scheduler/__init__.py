from rpc import RPCServer
from config import config

_server = None

def init(datafile):
    global _server
    _server = RPCServer(datafile)

def listen():
    _server.listen()

