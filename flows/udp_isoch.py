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
# Date November 2017
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
parser.add_argument('-s','--server', type=str, required=True, help='host to run iperf server')
parser.add_argument('-c','--client', type=str, default='localhost', required=False, help='host to run iperf client')
parser.add_argument('-d','--dst', type=str, required=True, help='iperf destination ip address')
parser.add_argument('-i','--interval', type=int, required=False, default=0, help='iperf report interval')
parser.add_argument('-n','--runcount', type=int, required=False, default=5, help='number of runs')
parser.add_argument('-t','--time', type=float, default=10, required=False, help='time or duration to run traffic')
parser.add_argument('-O','--offered_load', type=str, default="60:100m,40m", required=False, help='offered load; <fps>:<mean>,<variance>')
parser.add_argument('-T','--title', type=str, default="", required=False, help='title for graphs')
parser.add_argument('-S','--tos', type=str, default='BE', required=False, help='type of service or access class; BE, VI, VO or BK')
parser.add_argument('-o','--output_directory', type=str, required=False, default='./data', help='output directory')
parser.add_argument('--loglevel', type=str, required=False, default='INFO', help='python logging level, e.g. INFO or DEBUG')
parser.add_argument('--stress_server', type=str, required=False, default='10.19.87.9', help='host to run iperf server for stress traffic')
parser.add_argument('--stress_client', type=str, required=False, default='10.19.87.8', help='host to run iperf client for stress traffic')
parser.add_argument('--stress_proto', type=str, required=False, default='TCP', help='IP protocol for stress traffic')
parser.add_argument('--stress_offered_load', type=str, required=False, default='40m,4m', help='Offered load for stress traffic')
parser.add_argument('--stress_tos', type=str, default='BE', required=False, help='type of service or access class for stress traffic; BE, VI, VO or BK')
parser.add_argument('--stress_dst', type=str, required=False, default='192.168.1.2', help='iperf destination ip address for stress traffic')
parser.add_argument('--isoch', dest='isoch', action='store_true')
parser.add_argument('--stressor', dest='stressor', action='store_true')
parser.add_argument('--noframeburst', dest='noframeburst', action='store_true')
parser.add_argument('--amsdu', dest='amsdu', action='store_true')
parser.add_argument('--ipg', type=float, default=0.005, required=False, help='set interpacket gab in milliseconds')
parser.set_defaults(amsdu=False)
parser.set_defaults(stressor=False)
parser.set_defaults(noframeburst=False)

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

#instatiate devices
duta = ssh_node(name='SoftAP', ipaddr=args.client, device='ap0')
dutb = ssh_node(name='STA1', ipaddr=args.server, device='eth0')
if args.stressor :
    stressa = ssh_node(name='StressA', ipaddr=args.stress_client, device='eth0')
    stressb = ssh_node(name='StressB', ipaddr=args.stress_server, device='eth0')

srcip = '192.168.1.1'
srcport = '6001'
dstport = '6001'
duts = [duta, dutb]

plottitle='('+ args.offered_load + ' ' + args.tos +') ' + args.title + ' ' + str(args.time) + 'sec '
if args.noframeburst :
    plottitle += 'FB=0'
    fbsetting=0
else :
    plottitle += 'FB=1'
    fbsetting=1

if args.amsdu :
    plottitle += ' AMSDU=1'
    amsdusetting=1
else :
    plottitle += ' AMSDU=0'
    amsdusetting=0

if args.stressor :
    plottitle += ' Stressor=' + args.stress_offered_load

#main udp possibly isochronous traffic flow
flows = [iperf_flow(name='UDP', user='root', server=args.server, client=args.client, dstip=args.dst, dstport=dstport, srcip=srcip, srcport=srcport, proto='UDP', offered_load=args.offered_load, interval=args.interval, ipg=args.ipg, flowtime=args.time, tos=args.tos, udptriggers=True, debug=False, window='32M')]

#optional "stressor flow"
if args.stress_server and args.stress_client and args.stress_dst and args.stressor :
    flows.append(iperf_flow(name="STRESS", user='root', server=args.stress_server, client=args.stress_client, dstip=args.stress_dst, proto=args.stress_proto, offered_load=args.stress_offered_load, interval=args.interval, flowtime=args.time, tos=args.stress_tos, debug=False))
    print("Running stress {} traffic client={} server={} dest={} with load {}".format(args.stress_proto, args.stress_client, args.stress_server, args.stress_dst, args.stress_offered_load, args.time))

ssh_node.open_consoles()

for dut in duts :
    dut.dhd(cmd='pktts_config set src {} srcport {} dst {} dstport {} srcmask 255.255.255.255 dstmask 255.255.255.255 v4 udp'.format(srcip, srcport, args.dst, dstport))
ssh_node.run_all_commands()

for dut in duts :
    dut.wl(cmd='frameburst {}'.format(fbsetting))
ssh_node.run_all_commands()

for dut in duts :
    dut.wl(cmd='amsdu {}'.format(amsdusetting))
ssh_node.run_all_commands()

for i in range(args.runcount) :
    print("Running ({}) isochronous traffic client={} server={} dest={} with load {} for {} seconds".format(str(i), args.client, args.server, args.dst, args.offered_load, args.time))
    for dut in duts :
        dut.wl(cmd='reset_cnts')
    ssh_node.run_all_commands()
    for dut in duts :
        dut.wl(cmd='dump_clear ampdu')
    ssh_node.run_all_commands()

    iperf_flow.run(time=args.time, flows='all', preclean=False)

    for dut in duts :
        dut.wl(cmd='dump ampdu')
        ssh_node.run_all_commands()
    for dut in duts :
        dut.wl(cmd='counters')
        ssh_node.run_all_commands()

for flow in flows :
    flow.compute_ks_table(directory=args.output_directory, title=plottitle)

# iperf_flow.plot(title=plottitle, directory=args.output_directory)

ssh_node.close_consoles()
iperf_flow.close_loop()
logging.shutdown()
