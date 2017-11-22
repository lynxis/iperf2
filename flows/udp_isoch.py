#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date November 2017
import shutil
import logging
import flows
import argparse

from flows import *

parser = argparse.ArgumentParser(description='Run an isochronous UDP data stream')
parser.add_argument('-s', '--server', type=str, required=True, help='host to run iperf server')
parser.add_argument('-c', '--client', type=str, required=False, default='localhost', help='host to run iperf client')
parser.add_argument('-d', '--dst', type=str, required=True, help='iperf destination ip address')
parser.add_argument('-t', '--time', type=int, default=10, required=False, help='time or duration to run traffic')
parser.add_argument('-S', '--tos', type=str, default='BE', required=False, help='type of service or access class; BE, VI, VO or BK')
args = parser.parse_args()

#logging.basicConfig(filename='test.log', level=logging.DEBUG, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')
logging.basicConfig(filename='test.log', level=logging.INFO, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')

logging.getLogger('asyncio').setLevel(logging.INFO)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)

testtitle = 'test'
count = 1

flows = [iperf_flow(name="ISOCH{}".format(str(i)), user='root', server=args.server, client=args.client, dst=args.dst, proto='UDP', offered_load="60:18M,0", interval=0, flowtime=args.time, tos=args.tos, debug=False) for i in range(count)]
print("Running traffic for {} seconds\n".format(args.time))
iperf_flow.run(time=args.time, flows='all', preclean=False)
for flow in flows :
    for histogram in flow.flowstats['histograms'] :
        histogram.plot(title=testtitle)
        histogram.plot(title=testtitle, outputtype='svg')

logging.shutdown()
