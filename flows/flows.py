#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date April 2016

import re
import subprocess
import logging
import asyncio, sys
import time, datetime
import locale
import signal
import weakref
import os

from datetime import datetime as datetime

logger = logging.getLogger(__name__)

class iperf_flow(object):
    port = 61000
    iperf = '/usr/bin/iperf'
    instances = weakref.WeakSet()
    loop = None
    flow_scope = ("flowstats")

    @classmethod
    def sleep(cls, time=0, text=None, stoptext=None) :
        loop = asyncio.get_event_loop()
        if text :
            logging.info('Sleep {} ({})'.format(time, text))
        loop.run_until_complete(asyncio.sleep(time))
        if stoptext :
            logging.info('Sleep done ({})'.format(stoptext))

    @classmethod
    def get_instances(cls):
        return list(iperf_flow.instances)

    @classmethod
    def set_loop(cls, loop=None):
        if loop :
            iperf_flow.loop = loop
        elif os.name == 'nt':
            # On Windows, the ProactorEventLoop is necessary to listen on pipes
            iperf_flow.loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.get_event_loop()
            iperf_flow.loop = asyncio.get_event_loop()

    @classmethod
    def run(cls, time=None, flows='all', preclean=False) :
        if flows == 'all' :
            flows = iperf_flow.get_instances()
        if not flows:
            logging.warn('flow run method called with no flows instantiated')
            return

        if preclean:
            hosts = [flow.server for flow in flows]
            hosts.extend([flow.client for flow in flows])
            hosts=list(set(hosts))
            tasks = [asyncio.ensure_future(iperf_flow.cleanup(user='root', host=host)) for host in hosts]
            try :
                iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
            except asyncio.TimeoutError:
                logging.error('preclean timeout')
            raise

        logging.info('flow run invoked')
        tasks = [asyncio.ensure_future(flow.rx.start(time=time), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow server start timeout')
            raise
        tasks = [asyncio.ensure_future(flow.tx.start(time=time), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow client start timeout')
            raise

        iperf_flow.sleep(time=0.3, text="ramp up", stoptext="ramp up done")

        tasks = [asyncio.ensure_future(flow.is_traffic(), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow traffic check timeout')
            raise

        iperf_flow.sleep(time=time, text="Running traffic start", stoptext="Stopping flows")

        # Signal the remote iperf client sessions to stop them
        tasks = [asyncio.ensure_future(flow.tx.signal_stop(), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=3, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow tx stop timeout')
            raise

        # Now signal the remote iperf server sessions to stop them
        tasks = [asyncio.ensure_future(flow.rx.signal_stop(), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=3, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow tx stop timeout')
            raise

        iperf_flow.loop.close()
        logging.info('flow run finished')

    @classmethod
    def plot(cls, flows='all') :
        if flows == 'all' :
            flows = iperf_flow.get_instances()
        for flow in flows:
            print(flow.flowstats)

    @classmethod
    def stop(cls, flows='all') :
        loop = asyncio.get_event_loop()
        if flows == 'all' :
            flows = iperf_flow.get_instances()
        iperf_flow.set_loop(loop=loop)
        tasks = [asyncio.ensure_future(flow.tx.stop(), loop=loop) for flow in flows]
        try :
            loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow server start timeout')
            raise

        tasks = [asyncio.ensure_future(flow.rx.stop(), loop=loop) for flow in flows]
        try :
            loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow server start timeout')
            raise

    @classmethod
    async def cleanup(cls, host=None, sshcmd='/usr/bin/ssh', user='root') :
        if host:
            logging.info('ssh {}@{} pkill iperf'.format(user, host))
            childprocess = await asyncio.create_subprocess_exec(sshcmd, '{}@{}'.format(user, host), 'pkill', 'iperf', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, loop=iperf_flow.loop)
            stdout, _ = await childprocess.communicate()
            if stdout:
                logging.info('cleanup: host({}) stdout={} '.format(host, stdout))

    def __init__(self, name='iperf', server='localhost', client = 'localhost', user = 'root', proto = 'TCP', dst = '127.0.0.1', interval = 0.5, flowtime=10):
        iperf_flow.instances.add(self)
        if not iperf_flow.loop :
            iperf_flow.set_loop()
        self.loop = iperf_flow.loop
        self.name = name
        self.flowname = name
        iperf_flow.port += 1
        self.port = iperf_flow.port
        self.server = server
        self.client = client
        self.user = user
        self.proto = proto
        self.dst = dst
        self.interval = interval
        self.TRAFFIC_EVENT_TIMEOUT = round(self.interval * 4, 3)
        self.flowstats = {'current_rxbytes' : None , 'current_txbytes' : None , 'flowrate' : None}
        self.flowtime = flowtime
        # use python composition for the server and client
        # i.e. a flow has a server and a client
        self.rx = iperf_server(name='{}->RX({})'.format(name, str(self.server)), loop=self.loop, user=self.user, host=self.server, flow=self)
        self.tx = iperf_client(name='{}->TX({})'.format(name, str(self.client)), loop=self.loop, user=self.user, host=self.client, flow=self)
        # Initialize the flow stats dictionary
        self.flowstats['txdatetime']=[]
        self.flowstats['txbytes']=[]
        self.flowstats['txthroughput']=[]
        self.flowstats['writes']=[]
        self.flowstats['errwrites']=[]
        self.flowstats['retry']=[]
        self.flowstats['cwnd']=[]
        self.flowstats['rtt']=[]
        self.flowstats['rxdatetime']=[]
        self.flowstats['rxbytes']=[]
        self.flowstats['rxthroughput']=[]
        self.flowstats['reads']=[]

    def destroy(self) :
        iperf_flow.instances.remove(self)

    async def start(self):
        await self.rx.start()
        await self.tx.start()

    async def is_traffic(self) :
        self.rx.traffic_event.clear()
        self.tx.traffic_event.clear()
        logging.debug('{} {}'.format(self.name, 'traffic check invoked'))
        await self.rx.traffic_event.wait()
        await self.tx.traffic_event.wait()

    async def stop(self):
        self.tx.stop()
        self.rx.stop()

    def stats(self):
        logging.info('stats')


class iperf_server(object):

    class IperfServerProtocol(asyncio.SubprocessProtocol):
        def __init__(self, server, flow):
            self.__dict__['flow'] = flow
            self._exited = False
            self._closed_stdout = False
            self._closed_stderr = False
            self._mypid = None
            self._server = server
            self._stdoutbuffer = ""
            self._stderrbuffer = ""

        def __setattr__(self, attr, value):
            if attr in iperf_flow.flow_scope:
                self.flow.__setattr__(self.flow, attr, value)
            else:
                self.__dict__[attr] = value

        # methods and attributes not here are handled by the flow object,
        # aka, the flow object delegates to this object per composition
        def __getattr__(self, attr):
            if attr in iperf_flow.flow_scope:
                return getattr(self.flow, attr)

        @property
        def finished(self):
            return self._exited and self._closed_stdout and self._closed_stderr

        def signal_exit(self):
            if not self.finished:
                return
            self._server.closed.set()
            self._server.opened.clear()

        def connection_made(self, trans):
            self._server.closed.clear()
            self._mypid = trans.get_pid()
            logging.debug('server connection made pid=({})'.format(self._mypid))

        def pipe_data_received(self, fd, data):
            # logging.debug('{} {}'.format(fd, data))
            data = data.decode("utf-8")
            if fd == 1:
                self._stdoutbuffer += data
                while "\n" in self._stdoutbuffer:
                    line, self._stdoutbuffer = self._stdoutbuffer.split("\n", 1)
                    logging.info('{} {} (stdout,{})'.format(self._server.name, line, self._server.remotepid))
                    if not self._server.opened.is_set() :
                        m = self._server.regex_open_pid.match(line)
                        if m :
                            # logging.debug('remote pid match {}'.format(m.group('pid')))
                            self._server.remotepid = m.group('pid')
                            self._server.opened.set()

                    else :
                        m = self._server.regex_traffic.match(line)
                        if m :
                            timestamp = datetime.now()
                            if not self._server.traffic_event.is_set() :
                                self._server.traffic_event.set()

                            bytes = float(m.group('bytes'))
                            if self.flowstats['current_txbytes'] :
                                flowrate = round((bytes / self.flowstats['current_txbytes']), 2)
                                # *consume* the current *txbytes* where the client pipe will repopulate on its next sample
                                # do this by setting the value to None
                                self.flowstats['current_txbytes'] = None
                                # logging.debug('{} flow  ratio={:.2f}'.format(self._server.name, flowrate))
                                self.flowstats['flowrate'] = flowrate
                            else :
                                # *produce* the current *rxbytes* so the client pipe can know this event occurred
                                # indicate this by setting the value to value
                                self.flowstats['current_rxbytes'] = bytes

                            self.flowstats['rxdatetime'].append(timestamp)
                            self.flowstats['rxbytes'].append(m.group('bytes'))
                            self.flowstats['rxthroughput'].append(m.group('throughput'))
                            self.flowstats['reads'].append(m.group('reads'))
            elif fd == 2:
                self._stderrbuffer += data
                while "\n" in self._stderrbuffer:
                    line, self._stderrbuffer = self._stderrbuffer.split("\n", 1)
                    logging.info('{} {} (stderr)'.format(self._server.name, line))


        def pipe_connection_lost(self, fd, exc):
            if fd == 1:
                self._closed_stdout = True
                logging.debug('stdout pipe to {} closed (exception={})'.format(self._server.name, exc))
            elif fd == 2:
                self._closed_stderr = True
                logging.debug('stderr pipe to {} closed (exception={})'.format(self._server.name, exc))
            if self._closed_stdout and self._closed_stderr :
                self.remotepid = None;
            self.signal_exit()

        def process_exited(self):
            logging.debug('subprocess with pid={} closed'.format(self._mypid))
            self._exited = True
            self._mypid = None
            self.signal_exit()

    def __init__(self, name='Server', loop=None, user='root', host='localhost', flow=None):
        self.__dict__['flow'] = flow
        self.loop = iperf_flow.loop
        self.name = name
        self.iperf = '/usr/local/bin/iperf'
        self.ssh = '/usr/bin/ssh'
        self.host = host
        self.user = user
        self.flow = flow
        self.opened = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
        self.closed.set()
        self.traffic_event = asyncio.Event(loop=self.loop)
        self._transport = None
        self._protocol = None
        self.time = time

        # ex. Server listening on TCP port 61003 with pid 2565
        self.regex_open_pid = re.compile('^Server listening on {} port {} with pid (?P<pid>\d+)'.format(self.proto, str(self.port)))
        # ex. [  4] 0.00-0.50 sec  657090 Bytes  10513440 bits/sec  449    449:0:0:0:0:0:0:0
        self.regex_traffic = re.compile('\[\s+\d+] (?P<timestamp>.*) sec\s+(?P<bytes>[0-9]+) Bytes\s+(?P<throughput>[0-9]+) bits/sec\s+(?P<reads>[0-9]+)')

    def __getattr__(self, attr):
        return getattr(self.flow, attr)

    async def start(self, time=time):
        if not self.closed.is_set() :
            return

        self.opened.clear()
        self.remotepid = None
        iperftime = time + 30
        self.sshcmd=[self.ssh, self.user + '@' + self.host, self.iperf, '-s', '-p ' + str(self.port), '-e', '-i ' + str(round(self.interval,3)), '-t ' + str(iperftime), '-z', '-fb']
        logging.info('{}'.format(str(self.sshcmd)))
        self._transport, self._protocol = await self.loop.subprocess_exec(lambda: self.IperfServerProtocol(self, self.flow), *self.sshcmd)
        await self.opened.wait()

    async def signal_stop(self):
        if self.remotepid :
            childprocess = await asyncio.create_subprocess_exec(self.ssh, '{}@{}'.format(self.user, self.host), 'kill', '-HUP', '{}'.format(self.remotepid), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, loop=self.loop)
            logging.debug('({}) sending signal HUP to {} (pid={})'.format(self.user, self.host, self.remotepid))
            stdout, _ = await childprocess.communicate()
            if stdout:
                logging.info('{}({}) {}'.format(self.user, self.host, stdout))
            if not self.closed.is_set() :
                await self.closed.wait()

class iperf_client(object):

    # Asycnio protocol for subprocess transport
    class IperfClientProtocol(asyncio.SubprocessProtocol):
        def __init__(self, client, flow):
            self.__dict__['flow'] = flow
            self._exited = False
            self._closed_stdout = False
            self._closed_stderr = False
            self._mypid = None
            self._client = client
            self._stdoutbuffer = ""
            self._stderrbuffer = ""

        def __setattr__(self, attr, value):
            if attr in iperf_flow.flow_scope:
                self.flow.__setattr__(self.flow, attr, value)
            else:
                self.__dict__[attr] = value

        def __getattr__(self, attr):
            if attr in iperf_flow.flow_scope:
                return getattr(self.flow, attr)

        @property
        def finished(self):
            return self._exited and self._closed_stdout and self._closed_stderr

        def signal_exit(self):
            if not self.finished:
                return
            self._client.closed.set()
            self._client.opened.clear()

        def connection_made(self, trans):
            self._client.closed.clear()
            self._mypid = trans.get_pid()
            logging.debug('client connection made pid=({})'.format(self._mypid))

        def pipe_data_received(self, fd, data):
            # logging.debug('{} {}'.format(fd, data))
            data = data.decode("utf-8")
            if fd == 1:
                self._stdoutbuffer += data
                while "\n" in self._stdoutbuffer:
                    line, self._stdoutbuffer = self._stdoutbuffer.split("\n", 1)
                    logging.info('{} {} (stdout,{})'.format(self._client.name, line, self._client.remotepid))
                    if not self._client.opened.is_set() :
                        m = self._client.regex_open_pid.match(line)
                        if m :
                            # logging.debug('remote pid match {}'.format(m.group('pid')))
                            self._client.opened.set()
                            self._client.remotepid = m.group('pid')
                    else :
                        m = self._client.regex_traffic.match(data)
                        if m :
                            timestamp = datetime.now()
                            if not self._client.traffic_event.is_set() :
                                self._client.traffic_event.set()

                            bytes = float(m.group('bytes'))
                            if self.flowstats['current_rxbytes'] :
                                flowrate = round((self.flowstats['current_rxbytes'] / bytes), 2)
                                # *consume* the current *rxbytes* where the server pipe will repopulate on its next sample
                                # do this by setting the value to None
                                self.flowstats['current_rxbytes'] = None
                                # logging.debug('{} flow ratio={:.2f}'.format(self._client.name, flowrate))
                                self.flowstats['flowrate'] = flowrate
                            else :
                                # *produce* the current txbytes so the server pipe can know this event occurred
                                # indicate this by setting the value to value
                                self.flowstats['current_txbytes'] = bytes

                            self.flowstats['txdatetime'].append(timestamp)
                            self.flowstats['txbytes'].append(m.group('bytes'))
                            self.flowstats['txthroughput'].append(m.group('throughput'))
                            self.flowstats['writes'].append(m.group('writes'))
                            self.flowstats['errwrites'].append(m.group('errwrites'))
                            self.flowstats['retry'].append(m.group('retry'))
                            self.flowstats['cwnd'].append(m.group('cwnd'))
                            self.flowstats['rtt'].append(m.group('rtt'))

            elif fd == 2:
                self._stderrbuffer += data
                while "\n" in self._stderrbuffer:
                    line, self._stderrbuffer = self._stderrbuffer.split("\n", 1)
                    logging.info('{} {} (stderr)'.format(self._client.name, line))

        def pipe_connection_lost(self, fd, exc):
            if fd == 1:
                logging.debug('stdout pipe to {} closed (exception={})'.format(self._client.name, exc))
                self._closed_stdout = True
            elif fd == 2:
                logging.debug('stderr pipe to {} closed (exception={})'.format(self._client.name, exc))
                self._closed_stderr = True
            self.signal_exit()

        def process_exited(self,):
            logging.debug('subprocess with pid={} closed'.format(self._mypid))
            self._exited = True
            self._mypid = None
            self.signal_exit()

    def __init__(self, name='Client', loop=None, user='root', host='localhost', flow = None):
        self.__dict__['flow'] = flow
        self.loop = loop
        self.opened = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
        self.closed.set()
        self.traffic_event = asyncio.Event(loop=self.loop)
        self.name = name
        self.iperf = '/usr/local/bin/iperf'
        self.ssh = '/usr/bin/ssh'
        self.host = host
        self.user = user
        self._transport = None
        self._protocol = None
        # Client connecting to 192.168.100.33, TCP port 61009 with pid 1903
        self.regex_open_pid = re.compile('Client connecting to .*, {} port {} with pid (?P<pid>\d+)'.format(self.proto, str(self.port)))
        # traffic ex: [  3] 0.00-0.50 sec  655620 Bytes  10489920 bits/sec  14/211        446      446K/0 us
        self.regex_traffic = re.compile('\[\s+\d+] (?P<timestamp>.*) sec\s+(?P<bytes>\d+) Bytes\s+(?P<throughput>\d+) bits/sec\s+(?P<writes>\d+)/(?P<errwrites>\d+)\s+(?P<retry>\d+)\s+(?P<cwnd>\d+)K/(?P<rtt>\d+) us')

    def __getattr__(self, attr):
        return getattr(self.flow, attr)

    async def start(self, time=time):
        if not self.closed.is_set() :
            return

        self.opened.clear()
        self.remotepid = None
        if time:
            iperftime = time + 30
        else :
            ipertime = self.time + 30
        self.sshcmd=[self.ssh, self.user + '@' + self.host, self.iperf, '-c', self.dst, '-p ' + str(self.port), '-e', '-i ' + str(round(self.interval,3)), '-t ' + str(iperftime), '-b 100M', '-z', '-fb']
        logging.info('{}'.format(str(self.sshcmd)))
        self._transport, self._protocol = await self.loop.subprocess_exec(lambda: self.IperfClientProtocol(self, self.flow), *self.sshcmd)
        await self.opened.wait()

    async def signal_stop(self):
        if self.remotepid :
            childprocess = await asyncio.create_subprocess_exec(self.ssh, '{}@{}'.format(self.user, self.host), 'kill', '-HUP', '{}'.format(self.remotepid), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, loop=self.loop)
            logging.debug('({}) sending signal HUP to {} (pid={})'.format(self.user, self.host, self.remotepid))
            stdout, _ = await childprocess.communicate()
            if stdout:
                logging.info('{}({}) {}'.format(self.user, self.host, stdout))
            if not self.closed.is_set():
                await self.closed.wait()

    async def signal_pause(self):
        if self.remotepid :
            childprocess = await asyncio.create_subprocess_exec(self.ssh, '{}@{}'.format(self.user, self.host), 'kill', '-STOP', '{}'.format(self.remotepid), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, loop=self.loop)
            logging.debug('({}) sending signal STOP to {} (pid={})'.format(self.user, self.host, self.remotepid))
            stdout, _ = await childprocess.communicate()
            if stdout:
                logging.info('{}({}) {}'.format(self.user, self.host, stdout))
            if not self.closed.is_set():
                await self.closed.wait()

    async def signal_resume(self):
        if self.remotepid :
            childprocess = await asyncio.create_subprocess_exec(self.ssh, '{}@{}'.format(self.user, self.host), 'kill', '-CONT', '{}'.format(self.remotepid), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, loop=self.loop)
            logging.debug('({}) sending signal CONT to {} (pid={})'.format(self.user, self.host, self.remotepid))
            stdout, _ = await childprocess.communicate()
            if stdout:
                logging.info('{}({}) {}'.format(self.user, self.host, stdout))
            if not self.closed.is_set():
                await self.closed.wait()
