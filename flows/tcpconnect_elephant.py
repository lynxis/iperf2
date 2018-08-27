#!/usr/bin/env python3.5
#
# ---------------------------------------------------------------
# * Copyright (c) 2018
# * Broadcom Corporation
# * All Rights Reserved.
# *---------------------------------------------------------------
# Redistribution and use in source and binary forms, with or without modification, are permitted
# provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this list of conditions
# and the following disclaimer.  Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the documentation and/or other
# materials provided with the distribution.  Neither the name of the Broadcom nor the names of
# contributors may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
# IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Author Robert J. McMahon, Broadcom LTD
# Date August 2018
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
parser.add_argument('-P','--parallel', type=int, default=None, required=False, help='use parallel threads on the mouse client')
parser.add_argument('--initcwnd', type=int, default=None, required=False, help='set initcwnd')
parser.add_argument('--stacktest', dest='stacktest', action='store_true')
parser.add_argument('--edca_vi', dest='edca_vi', action='store_true')
parser.add_argument('--edca_reducebe', dest='edca_reducebe', action='store_true')
parser.add_argument('--txop_reduce', dest='edca_txop_reduce', action='store_true')
parser.add_argument('--nocompete', dest='nocompete', action='store_true')
parser.add_argument('--local', dest='local', action='store_true')
parser.add_argument('--bidir', dest='bidir', action='store_true')
parser.add_argument('--frameburst', dest='frameburst', action='store_true')
parser.set_defaults(stacktest=False)
parser.set_defaults(edca_vi=False)
parser.set_defaults(nocompete=False)
parser.set_defaults(edca_reducebe=False)
parser.set_defaults(edca_txop_reduce=False)
parser.set_defaults(local=False)
parser.set_defaults(bidir=False)
parser.set_defaults(frameburst=False)

# Parse command line arguments
args = parser.parse_args()

# Set directoy name and plot title
plottitle='Mouse at ' + args.tos
dirtxt = '_' + str(args.tos)
if args.local :
    scopetxt = 'local'
else :
    scopetxt = 'uplink'
if args.nocompete :
    dirtxt +='_nocompete'
else :
    plottitle +=', 2 TCP ' + scopetxt + ' BE Elephants, '
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
elif args.edca_reducebe :
    plottitle +='(edca=be_reduce)'
    dirtxt +='_be_reduce'
elif args.edca_txop_reduce :
    plottitle +='(edca=txop_reduce27)'
    dirtxt +='_be_txop_reduce'
else :
    dirtxt +='_ac'
if args.local :
    dirtxt += '_local'
    plottitle += '(local)'
if args.bidir :
    dirtxt += '_bidir'
    plottitle += '(bidir)'
if args.parallel :
    dirtxt += '_p{}'.format(args.parallel)
    plottitle += 'p({})'.format(args.parallel)
if args.frameburst :
    plottitle += '(fb=1)'
    dirtxt +='_fb1'
else :
    plottitle += '(fb=0)'
    dirtxt +='_fb0'
if args.initcwnd :
    plottitle += '(cwnd={})'.format(args.initcwnd)
    dirtxt += '_cwnd{}'.format(args.initcwnd)

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
duta = ssh_node(name='SoftAP', ipaddr=args.server, device='ap0', devip='192.168.1.1')
dutb = ssh_node(name='STA1', ipaddr='10.19.87.10', device='eth0', devip ='192.168.1.4')
dutc = ssh_node(name='STA2', ipaddr='10.19.87.9', device='eth0', devip ='192.168.1.2')
dutd = ssh_node(name='STA3', ipaddr='10.19.87.8', device='eth0', devip ='192.168.1.3')

ap = duta
dut_observe = dutb
duts = [ap, dut_observe]

#instatiate traffic flows to be used by the test
mouse = iperf_flow(name="Mouse(tcp)", user='root', server=ap, client=dut_observe, dstip=args.dst, proto='TCP', interval=1, flowtime=args.time, tos=args.tos, debug=False)
if not args.nocompete :
    dut_obstruct = [dutc, dutd]
    duts.extend(dut_obstruct)
    if args.stacktest :
        elephant1 = iperf_flow(name="Elephant1(tcp)", user='root', server=ap, client=dut_observe, dstip=ap.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephant2 = iperf_flow(name="Elephant2(tcp)", user='root', server=ap, client=dut_observe, dstip=ap.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
    elif args.local :
        elephant1 = iperf_flow(name="Elephant1(tcp)", user='root', server=dutd, client=dutc, dstip=dutd.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephant2 = iperf_flow(name="Elephant2(tcp)", user='root', server=dutc, client=dutd, dstip=dutc.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
    else :
        elephant1 = iperf_flow(name="Elephant1(tcp)", user='root', server=ap, client=dut_obstruct[0], dstip=ap.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephant2 = iperf_flow(name="Elephant2(tcp)", user='root', server=ap, client=dut_obstruct[1], dstip=ap.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
    elephants=[elephant1, elephant2]
    if args.bidir :
        elephant3 = iperf_flow(name="Elephant3(tcp)", user='root', server=dutc, client=dutd, dstip=dutc.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephant4 = iperf_flow(name="Elephant4(tcp)", user='root', server=dutd, client=dutc, dstip=dutd.devip, proto='TCP', interval=1, flowtime=7200, tos="BE", window='4M')
        elephants.extend([elephant3, elephant4])

# Open ssh node consoles (will setup up ssh master control session as well)
ssh_node.open_consoles(silent_mode=True)

# Perform any pretest wl commands
edca_vi='wme_ac sta be ecwmax 4 ecwmin 3 txop 94 aifsn 2 acm 0'
edca_be='wme_ac sta be ecwmax 10 ecwmin 4 txop 0 aifsn 3 acm 0'
edca_be_disadvantage='wme_ac sta be ecwmax 10 ecwmin 5 txop 0 aifsn 8 acm 0'
edca_txop_reduce='wme_ac sta be ecwmax 10 ecwmin 5 txop 27 aifsn 8 acm 0'
for dut in duts :
    #reset all BE edcas to default values
    dut.wl(cmd=edca_be)
    dut.wl(cmd='status')
    if args.frameburst :
        dut.wl(cmd='frameburst 1')
    else :
        dut.wl(cmd='frameburst 0')
    dut.rexec(cmd='pkill dmesg')
    dut.rexec(cmd='pkill iperf')
if args.initcwnd :
    dut_observe.rexec(cmd='ip route change {}/32 initcwnd {} initrwnd {} dev {}'.format(ap.devip, str(args.initcwnd), str(args.initcwnd), dut_observe.device))
ssh_node.run_all_commands()

# Possibly override BE EDCA parameters
if args.tos == 'BE' :
    if args.edca_vi :
        dut_observe.wl(cmd=edca_vi)
    elif args.edca_reducebe :
        for dut in dut_obstruct :
            dut.wl(cmd=edca_be_disadvantage)
    elif args.edca_txop_reduce :
        for dut in dut_obstruct :
            dut.wl(cmd=edca_txop_reduce)
    ssh_node.run_all_commands()

#Display actual EDCA used per device
ap.wl(cmd='wme_ac ap')
for dut in duts[1:] :
    dut.wl(cmd='wme_ac sta')
if args.initcwnd :
    dut_observe.rexec(cmd='ip route show')
ssh_node.run_all_commands()

# OK, finally get test going
if not args.nocompete :
    logging.info('Commencing elephants')
    iperf_flow.commence(time=7200, flows=elephants, preclean=False)

connect_times = []
trip_times = []
total_times = []
for i in range(args.runcount) :
    print('run={} {}'.format(i, plottitle))

    for dut in [dut_observe, ap] :
        dut.wl(cmd='dump_clear ampdu')
    ssh_node.run_all_commands()
    mouse.stats_reset()

    iperf_flow.run(amount='256K', time=None, flows=[mouse], preclean=False, parallel=args.parallel, triptime=True)

    for dut in [dut_observe, ap] :
        dut.wl(cmd='dump ampdu')
    ssh_node.run_all_commands()

    if mouse.connect_time :
        connect_times.extend(mouse.connect_time)
        if mouse.trip_time :
            trip_times.extend(mouse.trip_time)
            total_times.extend([mouse.trip_time[0] + mouse.connect_time[0]])
    logging.info('flowstats={}'.format(mouse.flowstats))


#  example tcpdump to capture 3WHS
#  tcpdump -i ap0 -n "(tcp[tcpflags] & (tcp-syn) != 0) or (src 192.168.1.1 and dst 192.168.1.4 and (tcp[tcpflags] & tcp-ack != 0))" -ttttnnvvS
#  tcpdump -i ap0 -n "(tcp[tcpflags] & (tcp-syn) != 0) or (src 192.168.1.1 and dst 192.168.1.4 and (tcp[tcpflags] & tcp-ack != 0))" -ttttnn

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
    fqplot = os.path.join(args.output_directory, "connect_times.png")
    plt.figure(figsize=(10,5))
    plt.title("{}(ct)".format(plottitle))
    plt.hist(connect_times, bins='auto', color='blue')
    plt.savefig('{}'.format(fqplot))

    logging.info('Trip times={}'.format(trip_times))
    mystats = 'Trip time stats={}'.format(stats.describe(trip_times))
    logging.info(mystats)
    fqplot = os.path.join(args.output_directory, "trip_times.png")
    plt.figure(figsize=(10,5))
    plt.title("{}(trip)".format(plottitle))
    plt.hist(trip_times, bins='auto', color='burlywood')
    plt.savefig('{}'.format(fqplot))

    logging.info('Total times={}'.format(total_times))
    mystats = 'Total time stats={}'.format(stats.describe(total_times))
    logging.info(mystats)
    fqplot = os.path.join(args.output_directory, "total_times.png")
    plt.figure(figsize=(10,5))
    plt.title("{}(tot)".format(plottitle))
    plt.hist(total_times, bins='auto', color='darkseagreen')
    plt.savefig('{}'.format(fqplot))

    fqplot = os.path.join(args.output_directory, "combined.png")
    plt.hist([connect_times, trip_times, total_times], bins='auto', label=['ct', 'trip', 'tot'])
    plt.title("{}(all)".format(plottitle))
    plt.legend(loc='upper right')
    plt.savefig('{}'.format(fqplot))

logging.shutdown()
