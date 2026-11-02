"""Run exact upstream test; block outbound connects, log attempt count."""
import atexit,json,os,runpy,sys
attempts=[]
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):
        attempts.append(event)
        raise RuntimeError('Network disabled for offline reproduction')
sys.addaudithook(audit)
@atexit.register
def report():
    print('OFFLINE_NETWORK_AUDIT='+json.dumps({'attempt_count':len(attempts),'events':attempts}))
runpy.run_module('pytest',run_name='__main__')
