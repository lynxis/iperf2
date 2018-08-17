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
parser.add_argument('--stacktest', dest='stacktest', action='store_true')
parser.add_argument('--edca_vi', dest='edca_vi', action='store_true')
parser.add_argument('--nocompete', dest='nocompete', action='store_true')
parser.set_defaults(stacktest=False)
parser.set_defaults(edca_vi=False)
parser.set_defaults(nocompete=False)

# Parse command line arguments
args = parser.parse_args()

# Set directoy name and plot title
plottitle='Mouse at ' + args.tos
dirtxt = '_' + str(args.tos)
if args.nocompete :
    dirtxt +='_nocompete'
else :
    plottitle +=', 2 TCP uplink BE Elephants, '
    dirtxt +='_elephants'
    if args.stacktest :
        plottitle +='(stack)'
        dirtxt +='_stack'
    else :
        plottitle +='(multi-mac)'
        dirtxt +='_macs'
if args.edca_vi :
    plottitle +='(edca=vi)'
    dirtxt +='_viedca'
else :
    dirtxt +='_ac'
plottitle += ' (cnt=' + str(args.runcount) + ')'
args.output_directory += dirtxt

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

#instatiate devices for control using control network, also list the wifi dev
duta = ssh_node(name='SoftAP', ipaddr=args.server, device='ap0')
dutb = ssh_node(name='STA1', ipaddr='10.19.87.10', device='eth0')
dutc = ssh_node(name='STA2', ipaddr='10.19.87.9', device='eth0')
dutd = ssh_node(name='STA3', ipaddr='10.19.87.8', device='eth0')

#instatiate traffic flows to be used by the test
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

# Open ssh node consoles (will setup up ssh master control session as well)
ssh_node.open_consoles(silent_mode=True)

# Perform any pretest wl commands
for dut in duts :
    dut.wl(cmd='status')
ssh_node.run_all_commands()
edca_vi='wme_ac sta be ecwmax 4 ecwmin 3 txop 94 aifsn 2 acm 0'
edca_be='wme_ac sta be ecwmax 10 ecwmin 4 txop 0 aifsn 3 acm 0'
ap = duts[0]
dut_observe = duts[1]

# Possibly override BE EDCA parameters, reset to default if not
if args.tos == 'BE' :
    if args.edca_vi :
        dut_observe.wl(cmd=edca_vi)
    else :
        dut_observe.wl(cmd=edca_be)
    ssh_node.run_all_commands()

#Display EDCA used per device
ap.wl(cmd='wme_ac ap')
for dut in duts[1:] :
    dut.wl(cmd='wme_ac sta')
ssh_node.run_all_commands()

# OK, finally get test going
if not args.nocompete :
    logging.info('Commencing elephants')
    iperf_flow.commence(time=7200, flows=elephants, preclean=False)

connect_times = []
for i in range(args.runcount) :
    print('run={} {}'.format(i, plottitle))
    mouse.stats_reset()
    iperf_flow.run(amount='256K', time=None, flows=[mouse], preclean=False)
    if mouse.connect_time :
        connect_times.append(mouse.connect_time)
    logging.info('flowstats={}'.format(mouse.flowstats))

# Test over, shut down traffic and all async
if not args.nocompete:
    logging.info('Ceasing elephants')
    iperf_flow.cease(flows=elephants)
ssh_node.close_consoles()
loop.close()

# Log results and produce final plots
if connect_times :
    logging.info('Connect times={}'.format(connect_times))
    mystats = 'Connect time stats={}'.format(stats.describe(connect_times))
    logging.info(mystats)
    print('Connect times={}'.format(connect_times))
    fqplot = os.path.join(args.output_directory, "connect_times.png")
    plt.figure(figsize=(10,5))
    plt.title("{}".format(plottitle))
#    plt.annotate(mystats, xy=(1, 1), xytext=(1,1))
    plt.hist(connect_times, bins='auto')
    plt.savefig('{}'.format(fqplot))

logging.shutdown()
