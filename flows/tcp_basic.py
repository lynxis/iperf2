#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date March 2017
import shutil
import logging
import flows

from flows import *

logging.basicConfig(filename='test.log', level=logging.INFO, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')

logging.getLogger('asyncio').setLevel(logging.DEBUG)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)

count = 2
time = 10

flows = [iperf_flow(name="TCP{}".format(str(i)), user='root', server='zeus', client='hera', dst='192.168.100.34', proto='TCP', interval=0.1, flowtime=time) for i in range(count)]
iperf_flow.run(time=time, flows='all', preclean=False)
