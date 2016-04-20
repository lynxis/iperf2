#!/usr/bin/env python3
#
# Author Robert J. McMahon
# Date April 2016
import flows
import asyncio
import shutil

from flows import *

@asyncio.coroutine
def testloop(loop):
    yield from asyncio.sleep(5)
    return

#tcp.start()
#loop.run_until_complete(testloop(loop))
#tcp.tx.pause()
#loop.run_until_complete(testloop(loop))
#tcp.tx.resume()
#print(tcp.rx.results, time.time())
#tcp.stop()

count=10
iperffromsrc = '../src/iperf' 
if shutil.which(iperffromsrc) is not None :
    flows.iperf = iperffromsrc
flows = [iperf_flow(name="TCP" + str(i)) for i in range(count)]
loop = asyncio.get_event_loop()
loop.set_debug(False)
try :
    for flow in flows :
        flow.start()
        # Careful here, sequential vs concurrent
    loop.run_until_complete(testloop(loop))

finally : 
    for flow in flows :
        flow.stop()
loop.close()
