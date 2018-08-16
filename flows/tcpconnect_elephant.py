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
import numpy as np
import tkinter
import matplotlib.pyplot as plt

from flows import *
from ssh_nodes import *
from datetime import datetime as datetime, timezone
from scipy import stats

parser = argparse.ArgumentParser(description='Run mouse flow connect tests with elephant flows')
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
parser.add_argument('--stacktest', dest='stack', action='store_true')
parser.add_argument('--edca_vi', dest='edca_vi', action='store_true')
parser.add_argument('--nocompete', dest='nocompete', action='store_true')
parser.set_defaults(stacktest=False)
parser.set_defaults(edca_vi=False)
parser.set_defaults(nocompete=False)


# Parse command line arguments
args = parser.parse_args()
plottitle='Mouse at ' + args.tos
if not args.nocompete:
    plottitle +=' , 2 TCP uplink BE Elephants'
if args.stacktest :
    plottitle +='(stack)'
else :
    if args.edca_vi :
        plottitle +='(mac edca)'
    else :
        plottitle +='(mac ac)'
plottitle += ' (cnt=' + args.runcnt + ')'

# Set up logging
logfilename='test.log'
if not os.path.exists(args.output_directory):
    print('Making log directory {}'.format(args.output_directory))
    os.makedirs(args.output_directory)

fqlogfilename = os.path.join(args.output_directory, logfilename)
print('Writing log to {}'.format(fqlogfilename))

logging.basicConfig(filename=fqlogfilename, level=logging.INFO, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')
logging.getLogger('asyncio').setLevel(logging.DEBUG)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)

#instatiate devices
duta = ssh_node(name='SoftAP', ipaddr=args.server, device='ap0')
dutb = ssh_node(name='STA1', ipaddr='10.19.87.10', device='eth0')
dutc = ssh_node(name='STA2', ipaddr='10.19.87.9', device='eth0')
dutd = ssh_node(name='STA3', ipaddr='10.19.87.8', device='eth0')

mouse = iperf_flow(name="Mouse(tcp)", user='root', server=duta.ipaddr, client=dutb.ipaddr, dstip=args.dst, proto='TCP', interval=1, flowtime=args.time, tos=args.tos)

if not args.nocompete :
    duts = [duta, dutb, dutc, dutd]
    if args.stacktest :
        elephant1 = iperf_flow(name="Elephant1(tcp)", user='root', server=duta.ipaddr, client=dutb.ipaddr, dstip=args.dst, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephant2 = iperf_flow(name="Elephant2(tcp)", user='root', server=duta.ipaddr, client=dutb.ipaddr, dstip=args.dst, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
    else :
        elephant1 = iperf_flow(name="Elephant1(tcp)", user='root', server=duta.ipaddr, client=dutc.ipaddr, dstip=args.dst, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephant2 = iperf_flow(name="Elephant2(tcp)", user='root', server=duta.ipaddr, client=dutd.ipaddr, dstip=args.dst, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephants=[elephant1, elephant2]
else :
    duts = [duta, dutb]

ssh_node.open_consoles(silent_mode=True)

for dut in duts :
    dut.wl(cmd='status')
ssh_node.run_all_commands()

edca_vi='wme_ac sta be ecwmax 4 ecwmin 3 txop 94 aifsn 2 acm 0'
edca_be='wme_ac sta be ecwmax 10 ecwmin 4 txop 0 aifsn 3 acm 0'
ap = duts[0]
dut_observe = duts[1]

# Use EDCA parameters if requesed
if args.tos == 'BE' :
    if args.edca_vi :
        dut_observe.wl(cmd=edca_vi)
    else :
        dut_observe.wl(cmd=edca_be)
    ssh_node.run_all_commands()

ap.wl(cmd='wme_ac ap')
for dut in duts[1:-1] :
    dut.wl(cmd='wme_ac sta')
ssh_node.run_all_commands()

connect_times = []

if not args.nocompete:
    iperf_flow.commence(time=7200, flows=elephants, preclean=False)
for i in range(args.runcount) :
    print('run={}'.format(i))
    mouse.stats_reset()
    iperf_flow.run(amount='256K', time=None, flows=[mouse], preclean=False)
    if mouse.connect_time :
        connect_times.append(mouse.connect_time)
    logging.info('flowstats={}'.format(mouse.flowstats))

# shut down async
logging.info('Ceasing elephants')
if not args.nocompete:
    iperf_flow.cease(flows=elephants)
ssh_node.close_consoles()
loop.close()

# produce plots
if connect_times :
    logging.info('Connect times={}'.format(connect_times))
    logging.info('Connect time stats={}'.format(stats.describe(connect_times)))
    print('Connect times={}'.format(connect_times))

    fqdata = os.path.join(args.output_directory, "ctimes.data")
    fqplot = os.path.join(args.output_directory, "connect_times.png")
    ct_histo=np.histogram(connect_times, bins=int(args.runcount/10))
    logging.info('Histogram={}'.format(ct_histo))
    plt.figure(figsize=(10,5))
    plt.title("{}".format(plottitle))
    plt.hist(connect_times, bins='auto')
    plt.savefig('{}'.format(fqplot))

logging.shutdown()
