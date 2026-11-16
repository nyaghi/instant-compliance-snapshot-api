"""Run retained fixtures without accidentally requesting live registry data."""
import sys,unittest
def offline(event,args):
    if event == 'socket.connect' and isinstance(args[1], tuple) and args[1][0] in {'127.0.0.1','::1','localhost'}:
        return
    if event == 'socket.getaddrinfo' and args[0] in {'127.0.0.1','::1','localhost'}:
        return
    if event in {'socket.connect','socket.getaddrinfo'}:
        raise OSError('Live network is disabled for local policy regression tests')
sys.addaudithook(offline)
unittest.main(module=None)
