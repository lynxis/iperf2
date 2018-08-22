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
import asyncio, sys
import ssh_nodes

from datetime import datetime as datetime, timezone
from flows import *
from ssh_nodes import *

parser = argparse.ArgumentParser(description='Run an isochronous UDP data stream')
parser.add_argument('-s','--server', type=str, default="10.19.87.10", required=False, help='host to run iperf server')
parser.add_argument('-c','--client', type=str, default="10.19.87.7", required=False, help='host to run iperf client')
parser.add_argument('-d','--dst', type=str, default="192.168.1.4, 192.168.1.2, 192.168.1.1",required=False, help='iperf destination ip address')
parser.add_argument('-i','--interval', type=float, required=False, default=0, help='iperf report interval')
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

logging.basicConfig(filename=fqlogfilename, level=logging.INFO, format='%(asctime)s %(levelname)-8s %(module)-9s  %(message)s')

logging.getLogger('asyncio').setLevel(logging.INFO)
root = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
loop.set_debug(False)
ssh_node.set_loop(loop)
ssh_node.loop.set_debug(False)
loop = asyncio.get_event_loop()

plottitle='{} {} {} {} bytes'.format(args.title, args.offered_load, args.tos, args.length)

duta = ssh_node(name='4377A', ipaddr='10.19.87.7', device='ap0', console=True, ssh_speedups=True)
dutb = ssh_node(name='4377B', ipaddr='10.19.87.10', device='eth0', console=True, ssh_speedups=True)
dutc = ssh_node(name='4357A', ipaddr='10.19.87.8', device='eth0', console=True, ssh_speedups=True)
dutd = ssh_node(name='4357B', ipaddr='10.19.87.9', device='eth0', console=True, ssh_speedups=True)
duts = [duta, dutb, dutc, dutd]

ssh_node.open_consoles()
cids = []
for dut in duts :
    cids.append(dut.wl(cmd='status', ASYNC=True))
ssh_node.run_all_commands()

flows = [iperf_flow(name="UDP1", user='root', server='10.19.87.10', client='10.19.87.7', proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.4', tos=args.tos, length=args.length)]
flows.append(iperf_flow(name="UDP2", user='root', server='10.19.87.8', client='10.19.87.7', proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.1', tos=args.tos, length=args.length))
flows.append(iperf_flow(name="UDP3", user='root', server='10.19.87.9', client='10.19.87.7', proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.2', tos=args.tos, length=args.length))

for i in range(args.runcount) :
    cids = []
    for dut in duts :
        cids.append(dut.wl(cmd='dump_clear ampdu', ASYNC=True))
    ssh_node.run_all_commands()
    print("Running ({}) traffic with load {} for {} seconds".format(str(i), args.offered_load, args.time))
    iperf_flow.run(time=args.time, flows='all', preclean=False)
    cids = []
    for dut in duts :
        cids.append(dut.wl(cmd='dump ampdu', ASYNC=True))
    ssh_node.run_all_commands()

ssh_node.close_consoles()
    
for flow in flows :
    flow.compute_ks_table(directory=args.output_directory, title=plottitle)

# iperf_flow.plot(title=plottitle, directory=args.output_directory)

iperf_flow.close_loop()
logging.shutdown()
