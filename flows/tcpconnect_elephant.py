#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date August 8, 2018
import shutil
import logging
import flows
import argparse
import time, datetime
import os,sys
import ssh_nodes

from datetime import datetime as datetime, timezone
from flows import *
from ssh_nodes import *

parser = argparse.ArgumentParser(description='Run an isochronous UDP data stream')
parser.add_argument('-s','--server', type=str, default='10.19.87.7',required=False, help='host to run iperf server')
parser.add_argument('-c','--client', type=str, default='10.19.87.10', required=False, help='host to run iperf client')
parser.add_argument('-d','--dst', type=str, default='192.168.1.1', required=False, help='iperf destination ip address')
parser.add_argument('-i','--interval', type=int, required=False, default=0, help='iperf report interval')
parser.add_argument('-n','--runcount', type=int, required=False, default=2, help='number of runs')
parser.add_argument('-t','--time', type=float, default=0.5, required=False, help='time or duration to run traffic')
parser.add_argument('-T','--title', type=str, default="", required=False, help='title for graphs')
parser.add_argument('-o','--output_directory', type=str, required=False, default='./data', help='output directory')
parser.add_argument('--loglevel', type=str, required=False, default='INFO', help='python logging level, e.g. INFO or DEBUG')
parser.add_argument('-S','--tos', type=str, default='BE', required=False, help='type of service or access class; BE, VI, VO or BK')

# Parse command line arguments
args = parser.parse_args()

# Set up logging
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


logging.basicConfig(filename='test.log', level=logging.INFO, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')

logging.getLogger('asyncio').setLevel(logging.DEBUG)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)

#instatiate devices
duta = ssh_node(name='SoftAP', ipaddr=args.server, device='ap0')
dutb = ssh_node(name='STA1', ipaddr='10.19.87.10', device='eth0')
dutc = ssh_node(name='STA2', ipaddr='10.19.87.9', device='eth0')
dutd = ssh_node(name='STA3', ipaddr='10.19.87.8', device='eth0')

mouse = iperf_flow(name="Mouse(tcp)", user='root', server=duta.ipaddr, client=dutb.ipaddr, dstip='192.168.1.1', proto='TCP', interval=1, flowtime=args.time, tos=args.tos)
ssh_node.open_consoles(silent_mode=True)

duta.wl(cmd='wme_ac ap')
dutb.wl(cmd='wme_ac sta')
dutc.wl(cmd='wme_ac sta')
dutd.wl(cmd='wme_ac sta')
ssh_node.run_all_commands()

ct_times = []
for i in range(args.runcount) :
    print('run={}'.format(i))
    mouse.stats_reset()
    iperf_flow.run(amount='256K', time=None, flows=[mouse], preclean=False)
    if mouse.connect_time :
        ct_times.append(mouse.connect_time)
    logging.info('flowstats={}'.format(mouse.flowstats))

ssh_node.close_consoles()
loop.close()

if ct_times :
    logging.info('Connect times={}'.format(ct_times))
    print('Connect times={}'.format(ct_times))

logging.shutdown()
