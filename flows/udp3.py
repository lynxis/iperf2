#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date November 2017
import shutil
import logging
import flows
import argparse
import time, datetime
import os,sys
import asyncio, sys

from datetime import datetime as datetime, timezone
from flows import *

parser = argparse.ArgumentParser(description='Run an isochronous UDP data stream')
parser.add_argument('-s','--server', type=str, default="10.19.87.10", required=False, help='host to run iperf server')
parser.add_argument('-c','--client', type=str, default="10.19.87.7", required=False, help='host to run iperf client')
parser.add_argument('-d','--dst', type=str, default="192.168.1.4, 192.168.1.2, 192.168.1.1",required=False, help='iperf destination ip address')
parser.add_argument('-i','--interval', type=int, required=False, default=0, help='iperf report interval')
parser.add_argument('-l','--length', type=int, required=False, default=1470, help='udp payload size')
parser.add_argument('-n','--runcount', type=int, required=False, default=5, help='number of runs')
parser.add_argument('-t','--time', type=float, default=10, required=False, help='time or duration to run traffic')
parser.add_argument('-O','--offered_load', type=str, default="500pps", required=False, help='offered load; <fps>:<mean>,<variance>')
parser.add_argument('-T','--title', type=str, default="3 Stream", required=False, help='title for graphs')
parser.add_argument('-S','--tos', type=str, default='BE', required=False, help='type of service or access class; BE, VI, VO or BK')
parser.add_argument('-o','--output_directory', type=str, required=False, default='./data', help='output directory')
parser.add_argument('--loglevel', type=str, required=False, default='INFO', help='python logging level, e.g. INFO or DEBUG')

args = parser.parse_args()

logfilename='test.log'
if not os.path.exists(args.output_directory):
    print('Making log directory {}'.format(args.output_directory))
    os.makedirs(args.output_directory)

fqlogfilename = os.path.join(args.output_directory, logfilename)
print('Writing log to {}'.format(fqlogfilename))

logging.basicConfig(filename=fqlogfilename, level=logging.INFO, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')

logging.getLogger('asyncio').setLevel(logging.INFO)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)

plottitle='{} {} {} {} bytes'.format(args.title, args.offered_load, args.tos, args.length)

flows = [iperf_flow(name="UDP1", user='root', server='10.19.87.10', client='10.19.87.7', proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.4', tos=args.tos, length=args.length)]
flows.append(iperf_flow(name="UDP2", user='root', server='10.19.87.8', client='10.19.87.7', proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.1', tos=args.tos, length=args.length))
flows.append(iperf_flow(name="UDP3", user='root', server='10.19.87.9', client='10.19.87.7', proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.2', tos=args.tos, length=args.length))
for i in range(args.runcount) :
    print("Running ({}) traffic with load {} for {} seconds".format(str(i), args.client, args.server, args.dst, args.offered_load, args.time))
    iperf_flow.run(time=args.time, flows='all', preclean=False)
    
for flow in flows :
    flow.compute_ks_table(directory=args.output_directory, title=plottitle)

# iperf_flow.plot(title=plottitle, directory=args.output_directory)

iperf_flow.close_loop()
logging.shutdown()
