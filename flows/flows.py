#!/usr/bin/env python3.5
#
# Author Robert J. McMahon
# Date April 2016

import re
import subprocess
import logging
import asyncio, sys
import time
import locale
import signal
import os, fcntl
import openssh
import weakref

from openssh import *
from fcntl import fcntl, F_GETFL, F_SETFL
from os import O_NONBLOCK

logger = logging.getLogger(__name__)


class iperf_flow(object):
    port = 61000
    iperf = '/usr/bin/iperf'
    instances = weakref.WeakSet()
    loop = None
    flowinfo = ("flowstats")

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
    def run(cls, time=None, flows='all') :
        if flows == 'all' :
            flows = iperf_flow.get_instances()
        if not flows:
            logging.warn('flow run method called with no flows instantiated')
            return

        tasks = [asyncio.ensure_future(flow.rx.start(), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow server start timeout')
            raise
        tasks = [asyncio.ensure_future(flow.tx.start(), loop=iperf_flow.loop) for flow in flows]
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

        iperf_flow.sleep(time=time, text="Running traffic start", stoptext="Traffic stopped")

        # Signal the remote iperf sessions to stop them
        tasks = [asyncio.ensure_future(session.rexec(host=flow.tx.host, cmd='kill -{} {}'.format('HUP', flow.tx.remotepid))) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow tx stop timeout')
            raise

        tasks = [asyncio.ensure_future(session.rexec(host=flow.rx.host, cmd='kill -{} {}'.format('HUP', flow.rx.remotepid))) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=10, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow rx stop timeout')
            raise
        iperf_flow.sleep(time=1, text="Stopping traffic")

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
    def cleanup(cls, hosts=None) :
        if hosts :
            iperf_flow.set_loop()
            sessions = [ssh_session(host=host, loop=iperf_flow.loop) for host in hosts]
            tasks = [asyncio.ensure_future(session.rexec(cmd=['/usr/bin/pkill iperf'])) for session in sessions]
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks))


    def __init__(self, name='iperf', server='localhost', client = 'localhost', user = 'root', proto = 'TCP', dst = '127.0.0.1', interval = 0.5, remotetime=10):
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
        self.flowstats = {'current_rxbytes' : None , 'current_txbytes' : None , 'rxtx_byteperc' : None}
        self.remotetime = remotetime
        # use python composition for the server and client
        # i.e. a flow has a server and a client
        self.rx = iperf_server(name='{}->RX({})'.format(name, str(self.server)), loop=self.loop, user=self.user, host=self.server, flow=self)
        self.tx = iperf_client(name='{}->TX({})'.format(name, str(self.client)), loop=self.loop, user=self.user, host=self.client, flow=self)


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
            self._server = server
            self._stdoutbuffer = ""
            self._stderrbuffer = ""

        def __setattr__(self, attr, value):
            if attr in iperf_flow.flowinfo:
                self.flow.__setattr__(self.flow, attr, value)
            else:
                self.__dict__[attr] = value

        # methods and attributes not here are handled by the flow object,
        # aka, the flow object delegates to this object per composition
        def __getattr__(self, attr):
            if attr in iperf_flow.flowinfo:
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
            logging.debug('connection made {}'.format(trans))

        def pipe_data_received(self, fd, data):
            # logging.debug('{} {}'.format(fd, data))
            data = data.decode("utf-8")
            if fd == 1:
                self._stdoutbuffer += data
                while "\n" in self._stdoutbuffer:
                    line, self._stdoutbuffer = self._stdoutbuffer.split("\n", 1)
                    logging.info('{} {} (stdout)'.format(self._server.name, line))
                    if not self._server.opened.is_set() :
                        m = self._server.regex_open_pid.match(line)
                        if m :
                            logging.debug('remote pid match {}'.format(m.group('pid')))
                            self._server.remotepid = m.group('pid')
                            self._server.opened.set()
                            self._server.closed.clear()
                    else :
                        m = self._server.regex_traffic.match(line)
                        if m :
                            if not self._server.traffic_event.is_set() :
                                self._server.traffic_event.set()

                            bytes = float(m.group('bytes'))
                            if self.flowstats['current_txbytes'] :
                                rxtx_byteperc = round((bytes / self.flowstats['current_txbytes']), 2)
                                # *consume* the current *txbytes* where the client pipe will repopulate on its next sample
                                # do this by setting the value to None
                                self.flowstats['current_txbytes'] = None
                                logging.debug('{} flow  ratio={:.2f}'.format(self._server.name, rxtx_byteperc))
                                self.flowstats['rxtx_byteperc'] = rxtx_byteperc
                            else :
                                # *produce* the current *rxbytes* so the client pipe can know this event occurred
                                # indicate this by setting the value to value
                                self.flowstats['current_rxbytes'] = bytes


            elif fd == 2:
                self._stderrbuffer += data
                while "\n" in self._stderrbuffer:
                    line, self._stderrbuffer = self._stderrbuffer.split("\n", 1)
                    logging.info('{} {} (stderr)'.format(self._server.name, line))


        def pipe_connection_lost(self, fd, exc):
            logging.debug('lost {} {}'.format(fd, exc))
            if fd == 1:
                self._closed_stdout = True
            elif fd == 2:
                self._closed_stderr = True
            if self._closed_stdout and self._closed_stderr :
                self.remotepid = None;
            self.signal_exit()

        def process_exited(self):
            logging.debug('process exit')
            self._exited = True
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
        self.traffic_event = asyncio.Event(loop=self.loop)
        self._transport = None
        self._protocol = None
        self.time = time

        # ex. Server listening on TCP port 61003 with pid 2565
        self.regex_open_pid = re.compile('^Server listening on {} port {} with pid (?P<pid>\d+)'.format(self.proto, str(self.port)))
        # ex. [  4] 0.00-0.50 sec  657090 Bytes  10513440 bits/sec  449    449:0:0:0:0:0:0:0
        self.regex_traffic = re.compile('\[\s+\d+] (?P<timestamp>.*) sec\s+(?P<bytes>[0-9]+) Bytes\s+(?P<throughput>[0-9]+) bits/sec\s+(?P<reads>[0-9]+)')

        # self.sshcmd=[self.ssh, self.user + '@' + self.host, '/usr/local/src/timestamp', '-c 180', '-n 3', '-d 1']

    def __getattr__(self, attr):
        return getattr(self.flow, attr)

    async def start(self):
        if self.opened.is_set() :
            return

        self.remotepid = None
        self.sshcmd=[self.ssh, self.user + '@' + self.host, self.iperf, '-s', '-p ' + str(self.port), '-e', '-i ' + str(round(self.interval,3)), '-t' + str(self.remotetime), '-z', '-fb']
        logging.info('{}'.format(str(self.sshcmd)))
        self._transport, self._protocol = await self.loop.subprocess_exec(lambda: self.IperfServerProtocol(self, self.flow), *self.sshcmd)
        await self.opened.wait()

    def stop(self):
        if self.remotepid :
            logging.info('{} Sending signal {} to {} on host {}'.format(self.name, signal, self.remotepid, self.host))
            session = ssh_session(host=self.host)

        if self.childprocess :
            logging.info('{} {} {}'.format(self.name, 'SIGINT', self.childprocess.pid))
            self.childprocess.send_signal(signal.SIGHUP)

    def pause(self) :
        self.childprocess.send_signal(signal.SIGSTOP)

    def resume(self) :
        self.childprocess.send_signal(signal.SIGCONT)

    def stop(self):
        if self.remotepid :
            self.remotesignal(signal=INT)

        if self.childprocess :
            self.childprocess.send_signal(signal.SIGHUP)

        if self.remotepid is None :
            return



class iperf_client(object):

    # Asycnio protocol for subprocess transport
    class IperfClientProtocol(asyncio.SubprocessProtocol):
        def __init__(self, client, flow):
            self.__dict__['flow'] = flow
            self._exited = False
            self._closed_stdout = False
            self._closed_stderr = False
            self._client = client
            self._stdoutbuffer = ""
            self._stderrbuffer = ""

        def __setattr__(self, attr, value):
            if attr in iperf_flow.flowinfo:
                self.flow.__setattr__(self.flow, attr, value)
            else:
                self.__dict__[attr] = value

        def __getattr__(self, attr):
            if attr in iperf_flow.flowinfo:
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
            logging.debug('connection made {}'.format(trans))

        def pipe_data_received(self, fd, data):
            # logging.debug('{} {}'.format(fd, data))
            data = data.decode("utf-8")
            if fd == 1:
                self._stdoutbuffer += data
                while "\n" in self._stdoutbuffer:
                    line, self._stdoutbuffer = self._stdoutbuffer.split("\n", 1)
                    logging.info('{} {} (stdout)'.format(self._client.name, line))
                    if not self._client.opened.is_set() :
                        m = self._client.regex_open_pid.match(line)
                        if m :
                            logging.debug('remote pid match {}'.format(m.group('pid')))
                            self._client.opened.set()
                            self._client.remotepid = m.group('pid')
                    else :
                        m = self._client.regex_traffic.match(data)
                        if m :
                            if not self._client.traffic_event.is_set() :
                                self._client.traffic_event.set()

                            bytes = float(m.group('bytes'))
                            if self.flowstats['current_rxbytes'] :
                                rxtx_byteperc = round((self.flowstats['current_rxbytes'] / bytes), 2)
                                # *consume* the current *rxbytes* where the server pipe will repopulate on its next sample
                                # do this by setting the value to None
                                self.flowstats['current_rxbytes'] = None
                                logging.debug('{} flow ratio={:.2f}'.format(self._client.name, rxtx_byteperc))
                                self.flowstats['rxtx_byteperc'] = rxtx_byteperc
                            else :
                                # *produce* the current txbytes so the server pipe can know this event occurred
                                # indicate this by setting the value to value
                                self.flowstats['current_txbytes'] = bytes

            elif fd == 2:
                self._stderrbuffer += data
                while "\n" in self._stderrbuffer:
                    line, self._stderrbuffer = self._stderrbuffer.split("\n", 1)
                    logging.info('{} {} (stderr)'.format(self._client.name, line))


        def pipe_connection_lost(self, fd, exc):
            logging.debug('lost {} {}'.format(fd, exc))
            if fd == 1:
                self._closed_stdout = True
            elif fd == 2:
                self._closed_stderr = True
            self.signal_exit()

        def process_exited(self):
            logging.debug('process exit')
            self._exited = True
            self.signal_exit()

    def __init__(self, name='Client', loop=None, user='root', host='localhost', flow = None):
        self.__dict__['flow'] = flow
        self.loop = loop
        self.opened = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
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

    async def start(self):
        if self.opened.is_set() :
            return

        self.remotepid = None
        self.sshcmd=[self.ssh, self.user + '@' + self.host, self.iperf, '-c', self.dst, '-p ' + str(self.port), '-e', '-i ' + str(round(self.interval,3)), '-t' + str(self.remotetime), '-b 100M', '-z', '-fb']
        logging.info('{}'.format(str(self.sshcmd)))
        self._transport, self._protocol = await self.loop.subprocess_exec(lambda: self.IperfClientProtocol(self, self.flow), *self.sshcmd)
        await self.opened.wait()
        self.closed.clear()

    def stop(self):
        if self.remotepid and self.opened.is_set() :
            self.remotesignal(signal='HUP')

        if self.childprocess :
            logging.info('{} {} {}'.format(self.name, 'SIGINT', self.childprocess.pid))
            self.childprocess.send_signal(signal.SIGHUP)

    def pause(self) :
        self.childprocess.send_signal(signal.SIGSTOP)

    def resume(self) :
        self.childprocess.send_signal(signal.SIGCONT)


    def remotesignal(self, signal='INT') :
        if self.remotepid :
            logging.info('{} Sending signal {} to {} on host {}'.format(self.name, signal, self.remotepid, self.host))
            loop = asyncio.get_event_loop()
            session = ssh_session(host=self.host)
            loop.run_until_complete(session.rexec(cmd='kill -{} {}'.format(signal, self.remotepid)))
