#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date March 2017
import shutil
import logging
import flows

from flows import *

#logging.basicConfig(filename='test.log', level=logging.DEBUG, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')
logging.basicConfig(filename='test.log', level=logging.INFO, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')

logging.getLogger('asyncio').setLevel(logging.INFO)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)

testtitle = 'test'
count = 1
time = 10

flows = [iperf_flow(name="ISOCH{}".format(str(i)), user='root', server='10.19.87.8', client='10.19.87.9', dst='192.168.1.61', proto='UDP', offered_load="60:18M,0", interval=0, flowtime=time, debug=True) for i in range(count)]

iperf_flow.run(time=time, flows='all', preclean=False)
logging.shutdown()
for flow in flows :
    for histogram in flow.flowstats['histograms'] :
        histogram.plot(title=testtitle)
