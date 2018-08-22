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
import host

from datetime import datetime as datetime, timezone
from flows import *
from host import *

parser = argparse.ArgumentParser(description='Run an isochronous UDP data stream')
parser.add_argument('-s','--server', type=str, default="10.19.87.10", required=False, help='host to run iperf server')
parser.add_argument('-c','--client', type=str, default="10.19.87.7", required=False, help='host to run iperf client')
parser.add_argument('-d','--dst', type=str, default="192.168.1.4",required=False, help='iperf destination ip address')
parser.add_argument('-i','--interval', type=int, required=False, default=0, help='iperf report interval')
parser.add_argument('-l','--length', type=int, required=False, default=180, help='udp payload size')
parser.add_argument('-n','--runcount', type=int, required=False, default=5, help='number of runs')
parser.add_argument('-t','--time', type=float, default=10, required=False, help='time or duration to run traffic')
parser.add_argument('-O','--offered_load', type=str, default="7000pps", required=False, help='offered load; <fps>:<mean>,<variance>')
parser.add_argument('-T','--title', type=str, default="54 nrate", required=False, help='title for graphs')
parser.add_argument('-S','--tos', type=str, default='VO', required=False, help='type of service or access class; BE, VI, VO or BK')
parser.add_argument('-o','--output_directory', type=str, required=False, default='./data', help='output directory')
parser.add_argument('--loglevel', type=str, required=False, default='INFO', help='python logging level, e.g. INFO or DEBUG')
parser.add_argument('--stress_server', type=str, required=False, default=None, help='host to run iperf server for stress traffic')
parser.add_argument('--stress_client', type=str, required=False, default=None, help='host to run iperf client for stress traffic')
parser.add_argument('--stress_proto', type=str, required=False, default='TCP', help='IP protocol for stress traffic')
parser.add_argument('--stress_offered_load', type=str, required=False, default='20M', help='Offered load for stress traffic')
parser.add_argument('--stress_tos', type=str, default='VO', required=False, help='type of service or access class for stress traffic; BE, VI, VO or BK')
parser.add_argument('--stress_dst', type=str, required=False, default=None, help='iperf destination ip address for stress traffic')
parser.add_argument('--isoch', dest='isoch', action='store_true')
parser.add_argument('--bidir', dest='bidir', action='store_true')
parser.set_defaults(isoch=False)
parser.set_defaults(bidir=False)

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

client=host(host=args.client)
client.rexec(cmd='pwd')
exit
plottitle='{} {} {} {} bytes'.format(args.title, args.offered_load, args.tos, args.length)

#main udp isochronous traffic flow
if args.isoch :
    flows = [iperf_flow(name="ISOCHUDP", user='root', server=args.server, client=args.client, udptriggers=True, proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.4', tos=args.tos, isoch=True, debug=False)]
else :
    print("No isoch")
    flows = [iperf_flow(name="UDP", user='root', server=args.server, client=args.client, udptriggers=True, proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst=args.dst, tos=args.tos, length=args.length, isoch=False, debug=False)]
    if args.bidir :
        bidir_flow = [iperf_flow(name="UDP-BiDir", user='root', server=args.client, client=args.server, udptriggers=False, proto='UDP', offered_load=args.offered_load, interval=args.interval, flowtime=args.time, dst='192.168.1.3', tos=args.tos, length=args.length, isoch=False, debug=False)]

#optional "stressor flow"
if args.stress_server and args.stress_client and args.stress_dst :
    flows.append(iperf_flow(name="STRESS", user='root', server=args.stress_server, client=args.stress_client, dst=args.stress_dst, proto=args.stress_proto, offered_load=args.stress_offered_load, interval=args.interval, flowtime=args.time, tos=args.stress_tos, debug=False))
    print("Running stress {} traffic client={} server={} dest={} with load {}".format(args.stress_proto, args.stress_client, args.stress_server, args.stress_dst, args.stress_offered_load, args.time))

for i in range(args.runcount) :
    print("Running ({}) traffic client={} server={} dest=192.168.1.4 with load {} for {} seconds".format(str(i), args.client, args.server, args.offered_load, args.time))
    if args.bidir :
        print("Running bidir flow")
    duts = [args.client, args.server]
    for dut in duts :
        sshcmd=['/usr/bin/ssh', 'root' + '@' + dut, 'wl -i eth0 dump_clear ampdu']
#        childprocess[dut] = await asyncio.create_subprocess_exec(sshcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, loop=loop)
#        logging.info('{} {} {}'.format(dut, sshcmd, childprocess[dut]))        
#    for dut in dut :
#        stdout[dut], stderr[dut] = await childprocess[dut].communicate()
#        if stdout[dut]:
#            logging.info('{}'.format(stdout[dut]))
#        if stderr:
#            logging.error('{}'.format(stderr[dut]))
        
    iperf_flow.run(time=args.time, flows='all', preclean=False)

    
for flow in flows :
    flow.compute_ks_table(directory=args.output_directory, title=plottitle)

# iperf_flow.plot(title=plottitle, directory=args.output_directory)

iperf_flow.close_loop()
logging.shutdown()
