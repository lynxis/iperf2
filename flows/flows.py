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

    @classmethod
    async def sleep(cls, time) :
        await asyncio.sleep(time)

    @classmethod
    def get_instances(cls):
        return list(iperf_flow.instances)

    @classmethod
    def set_loop(cls, loop=None):
        if loop :
            iperf_flow.loop = loop
        else:
            iperf_flow.loop = asyncio.get_event_loop()

    @classmethod
    def run(cls, time=None, flows='all', loop=None) :
        if flows == 'all' :
            flows = iperf_flow.get_instances()
        iperf_flow.set_loop(loop=loop)
        tasks = [asyncio.ensure_future(flow.rx.start(), loop=iperf_flow.loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=2, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow server start timeout')
            raise
        tasks = [asyncio.ensure_future(flow.tx.start(), loop=loop) for flow in flows]
        try :
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks, timeout=2, loop=iperf_flow.loop))
        except asyncio.TimeoutError:
            logging.error('flow client start timeout')
            raise

        if time :
            #self.iowatchdog = loop.call_later(self.IO_TIMEOUT, self.io_timer)
            try :
                iperf_flow.loop.run_until_complete(iperf_flow.sleep(time))
            except asyncio.TimeoutError:
                pass
        else :
            iperf_flow.loop.run_forever()

    @classmethod
    def cleanup(cls, hosts=None, loop=None) :
        if hosts :
            iperf_flow.set_loop(loop=loop)
            sessions = [ssh_session(host=host, loop=iperf_flow.loop) for host in hosts]
            tasks = [asyncio.ensure_future(session.rexec(cmd=['/usr/bin/pkill iperf'])) for session in sessions]
            iperf_flow.loop.run_until_complete(asyncio.wait(tasks))
            
    def __init__(self, name='iperf', server='localhost', client = 'localhost', user = 'root', proto = 'TCP', dst = '127.0.0.1', interval = '0.5', loop=None):
        iperf_flow.instances.add(self)
        if not iperf_flow.loop :
            iperf_flow.set_loop()
        self.loop = iperf_flow.loop
        self.name = name
        iperf_flow.port += 1
        self.port = iperf_flow.port
        self.server = server
        self.client = client
        self.user = user
        self.proto = proto
        self.dst = dst
        self.interval = interval
        self.rx = iperf_server(name='{}->RX({})'.format(name, str(self.server)), loop=self.loop, user=self.user, host=self.server, flow=self)
        self.tx = iperf_client(name='{}->TX({})'.format(name, str(self.client)), loop=self.loop, user=self.user, host=self.client, flow=self)

    def destroy(self) :
        iperf_flow.instances.remove(self)
    
    async def start(self):
        await self.rx.start()
        await self.tx.start()

    async def stop(self):
        self.tx.stop()
        self.rx.stop()

    def stats(self):
        logging.info('stats')

    def remotesignal(self, signal='INT') :
        if self.remotepid :
            logging.info('{} Sending signal {} to {} on host {}'.format(self.name, signal, self.remotepid, self.host))
            loop = asyncio.get_event_loop()
            session = ssh_session(host=self.host)
            loop.run_until_complete(session.rexec(cmd='kill -{} {}'.format(signal, self.remotepid)))

        
class iperf_server(iperf_flow):
    def __init__(self, name='Server', loop=None, user='root', host='localhost', flow=None):
        if loop is not None:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()

        self.opened = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
        self.name = name
        self.iperf = '/usr/local/bin/iperf'
        self.ssh = '/usr/bin/ssh'
        self.host = host
        self.user = user
        self.flow = flow
        # ex. Server listening on TCP port 61003 with pid 2565
        self.regex_open_pid = re.compile('Server listening on {} port {} with pid (?P<pid>\d+)'.format(self.proto, str(self.port)))
        # ex. [  4] 0.00-0.50 sec  657090 Bytes  10513440 bits/sec  449    449:0:0:0:0:0:0:0
        self.regex_traffic = re.compile('\[\s+\d+] (?P<timestamp>.*) sec\s+(?P<bytes>[0-9]+) Bytes\s+(?P<throughput>[0-9]+) bits/sec\s+(?P<reads>[0-9]+)')

    def __getattr__(self, attr):
        return getattr(self.flow, attr)
        
    async def start(self):
        if self.opened.is_set() :
            return

        self.remotepid = None
        sshcmd=[self.ssh, self.user + '@' + self.host, self.iperf, '-s', '-p ' + str(self.port), '-e', '-i ' + self.interval, '-t 6', '-z', '-fb']
        logging.info('{}({}) {}'.format(self.name, self.host, str(sshcmd)))
        self.childprocess = subprocess.Popen(sshcmd, bufsize=1, universal_newlines = True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        if self.childprocess :
            flags = fcntl(self.childprocess.stdout, F_GETFL)
            fcntl(self.childprocess.stdout, F_SETFL, flags | O_NONBLOCK)
            logging.debug('stdout add_reader {}({}.0x{:X})'.format(self.childprocess.pid, self.childprocess.stdout.name, (flags | O_NONBLOCK)))
            self.loop.add_reader(self.childprocess.stdout, self.server_stdout_event)
            flags = fcntl(self.childprocess.stderr, F_GETFL)
            fcntl(self.childprocess.stderr, F_SETFL, flags | O_NONBLOCK)
            logging.debug('stdout add_reader {}({}.0x{:X})'.format(self.childprocess.pid, self.childprocess.stderr.name, (flags | O_NONBLOCK)))
            self.loop.add_reader(self.childprocess.stderr, self.server_stderr_event)
            logging.debug('await pipes: server start pid={}'.format(self.childprocess.pid))
            await self.opened.wait()
            logging.debug('await done: server start pid={} rpid={}'.format(self.childprocess.pid, self.remotepid))
        else :
            logging.error('Failed: server start')

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

    def stop(self):
        if self.remotepid :
            self.remotesignal(signal=INT)

        if self.childprocess :
            self.childprocess.send_signal(signal.SIGHUP)

        if self.remotepid is None :
            return
        
    def server_stdout_event(self) :
        trailer = '{}({})'.format(self.childprocess.pid, self.childprocess.stdout.name)
        while True :
            data = self.childprocess.stdout.readline()
            if data :
                logging.info('{} {} {}'.format(self.name, str(data).strip('\r\n'), trailer))
                trailer = ''
                if not self.opened.is_set() :
                    m = self.regex_open_pid.match(data)
                    if m :
                        logging.debug('remote pid match {}'.format(m.group('pid')))
                        self.opened.set()
                        self.remotepid = m.group('pid')
                    else :
                        pass
                else :
                    m = self.regex_traffic.match(data)
                    #store time series data using panda
            else :
                break

        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            logging.debug('{} closed: pid={}'.format(self.name, self.childprocess.pid))
            self.loop.remove_reader(self.childprocess.stdout)
            self.closed.set()


    def server_stderr_event(self):
        trailer = '{}({})'.format(self.childprocess.pid, self.childprocess.stdout.name)
        while True :
            data = self.childprocess.stderr.readline()
            if data :
                logging.info('{} {}'.format(str(data).strip('\r\n'), trailer))
            else :
                break

        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            logging.debug('closed: pid={}'.format(self.childprocess.pid))
            self.loop.remove_reader(self.childprocess.stdout)
            self.closed.set()

                
class iperf_client(iperf_flow):
    def __init__(self, name='Client', loop=None, user='root', host='localhost', flow = None):
        self.loop = loop
        self.opened = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
        self.name = name
        self.iperf = '/usr/local/bin/iperf'
        self.ssh = '/usr/bin/ssh'
        self.host = host
        self.user = user
        self.flow = flow
        # Client connecting to 192.168.100.33, TCP port 61009 with pid 1903
        self.regex_open_pid = re.compile('Client connecting to .*, {} port {} with pid (?P<pid>\d+)'.format(self.proto, str(self.port)))
        # traffic ex: [  3] 0.00-0.50 sec  655620 Bytes  10489920 bits/sec  14/211        446      446K/0 us
        self.regex_traffic = re.compile('\[\s+\d+] (?P<timestamp>.*) sec\s+(?P<bytes>\d+) Bytes\s+(?P<throughput>\d+) bits/sec\s+(?P<writes>\d+)/(?P<errwrites>\d+)\s+(?P<retry>\d+)\s+(?P<cwnd>\d+)K/(?P<rtt>\d+) us')
        
    def __getattr__(self, attr):
        return getattr(self.flow, attr)

    async def start(self):
        if self.opened.is_set() :
            return

        sshcmd=[self.ssh, self.user + '@' + self.host, self.iperf, '-c', self.dst, '-p ' + str(self.port), '-e', '-i ' + self.interval, '-t 5', '-b 10M', '-z', '-fb']
        logging.info('{}({}) {}'.format(self.name, self.host, str(sshcmd)))
        self.childprocess = subprocess.Popen(sshcmd, bufsize=1, universal_newlines = True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        flags = fcntl(self.childprocess.stdout, F_GETFL)
        fcntl(self.childprocess.stdout, F_SETFL, flags | O_NONBLOCK)
        self.loop.add_reader(self.childprocess.stdout, self.client_stdout_event)
        logging.debug('stdout add_reader {}({}.0x{:X})'.format(self.childprocess.pid, self.childprocess.stdout.name, (flags | O_NONBLOCK)))
        flags = fcntl(self.childprocess.stderr, F_GETFL)
        fcntl(self.childprocess.stderr, F_SETFL, flags | O_NONBLOCK)
        self.loop.add_reader(self.childprocess.stderr, self.client_stderr_event)
        logging.debug('stdout add_reader {}({}.0x{:X})'.format(self.childprocess.pid, self.childprocess.stderr.name, (flags | O_NONBLOCK)))
        logging.debug('await pipes: client start pid={}'.format(self.childprocess.pid))
        await self.opened.wait()
        logging.debug('await done: client start pid={} rpid={}'.format(self.childprocess.pid, self.remotepid))

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

    def client_stdout_event(self):
        trailer = '{}({})'.format(self.childprocess.pid, self.childprocess.stdout.name)
        while True :
            data = self.childprocess.stdout.readline()
            if data :
                logging.info('{} {} {}'.format(self.name, str(data).strip('\r\n'), trailer))
                trailer = ''
                if not self.opened.is_set() :
                    m = self.regex_open_pid.match(data)
                    if m :
                        logging.debug('remote pid match {}'.format(m.group('pid')))
                        self.opened.set()
                        self.remotepid = m.group('pid')
                    else :
                        pass
                else :
                    m = self.regex_traffic.match(data)
            else :
                break

        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            logging.debug('{} closed: pid={}'.format(self.name, self.childprocess.pid))
            self.loop.remove_reader(self.childprocess.stdout)
            self.closed.set()

    def client_stderr_event(self):
        data = self.childprocess.stderr.readline()
        if data :
            logging.info(str(data).strip('\r\n'))
            if not self.opened.is_set() :
                self.opened.set()
            else :
                pass

        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            self.loop.remove_reader(self.childprocess.stderr)
            self.closed.set()

    def remotesignal(self, signal='INT') :
        if self.remotepid :
            logging.info('{} Sending signal {} to {} on host {}'.format(self.name, signal, self.remotepid, self.host))
            loop = asyncio.get_event_loop()
            session = ssh_session(host=self.host)
            loop.run_until_complete(session.rexec(cmd='kill -{} {}'.format(signal, self.remotepid)))
