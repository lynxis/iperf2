#!/usr/bin/env python3.5
#
# Python object to support sending remote commands to a host
#
# Author Robert J. McMahon
# Date April 2018
import re
import subprocess
import logging
import asyncio, sys
import time
import locale
import signal
import os, fcntl
import weakref

logger = logging.getLogger(__name__)

class ssh_node:
    DEFAULT_IO_TIMEOUT = 20.0
    DEFAULT_CMD_TIMEOUT = 30
    DEFAULT_CONNECT_TIMEOUT = 10.0
    rexec_tasks = []

    @classmethod
    def run_all_commands(cls, timeout=None, text=None, stoptext=None) :
        if ssh_node.rexec_tasks :
            loop = asyncio.get_event_loop()
            if text :
                logging.info('Run all tasks: {})'.format(time, text))
            loop.run_until_complete(asyncio.wait(ssh_node.rexec_tasks, timeout=timeout))
        if stoptext :
            logging.info('Sleep done ({})'.format(stoptext))
        ssh_node.rexec_tasks = []

    def __init__(self, loop=None, name=None, ipaddr=None, console=False, device=None):
       self.ipaddr = ipaddr
       self.name = name
       self.loop = asyncio.get_event_loop()
       if console :
           self.console_session = ssh_session(name=name, hostname=self.ipaddr, IO_TIMEOUT=None, CMD_TIMEOUT=None, CONNECT_TIMEOUT=10.0)
       else :
           self.console_session = None
       self.my_tasks = []
       self.device=device

    def __getattr__(self, attr):
        return getattr(self.host, attr)

    def wl (self, cmd, ASYNC=False) :
        if self.device :
            results=self.rexec(cmd='/usr/bin/wl -i {} {}'.format(self.device, cmd), ASYNC=ASYNC)
        else :
            results=self.rexec(cmd='/usr/bin/wl {}'.format(cmd), ASYNC=ASYNC)
        return results

    def rexec(self, cmd='pwd', ASYNC=False, IO_TIMEOUT=DEFAULT_IO_TIMEOUT, CMD_TIMEOUT=DEFAULT_CMD_TIMEOUT, CONNECT_TIMEOUT=DEFAULT_CONNECT_TIMEOUT) :
        io_timer = IO_TIMEOUT
        cmd_timer = CMD_TIMEOUT
        connect_timer = CONNECT_TIMEOUT

        this_session = ssh_session(name=self.name, hostname=self.ipaddr, IO_TIMEOUT=io_timer, CMD_TIMEOUT=cmd_timer, CONNECT_TIMEOUT=connect_timer)
        this_task = asyncio.ensure_future(this_session._schedule_sshcmd(cmd=cmd))
        ssh_node.rexec_tasks.append(this_task)
        self.my_tasks.append(this_task)
        if not ASYNC: 
            try :
                self.loop.run_until_complete(asyncio.wait([this_task], timeout=10, loop=self.loop))
            except asyncio.TimeoutError:
                logging.error('command schedule timed out')
                raise
            finally:
                ssh_node.rexec_tasks.remove(this_task)
                self.my_tasks.remove(this_task)

        return this_task

    def close_session(self) :
        if self.console_session :
            self.console_session.deinit()

class ssh_session:
    class SSHReaderProtocol(asyncio.SubprocessProtocol):
        def __init__(self, session):
            self._exited = False
            self._closed_stdout = False
            self._closed_stderr = False
            self._mypid = None
            self._stdoutbuffer = ""
            self._stderrbuffer = ""
            self.loop = asyncio.get_event_loop()
            self.debug = False
            self._session = session
            if self._session.CONNECT_TIMEOUT is not None :
                self.watchdog = self.loop.call_later(self._session.CONNECT_TIMEOUT, self.watchdog)
            self._session.closed.clear()
            self.timeout_occurred = asyncio.Event(loop=self.loop)
            self.timeout_occurred.clear()

        @property
        def finished(self):
            return self._exited and self._closed_stdout and self._closed_stderr

        def signal_exit(self):
            if not self.finished:
                return
            self._session.closed.set()

        def connection_made(self, trans):
            if self._session.CONNECT_TIMEOUT is not None :
                self.watchdog.cancel()
            self._mypid = trans.get_pid()
            self._transport = trans
            logging.debug('{} ssh node connection made pid=({})'.format(self._session.name, self._mypid))
            self._session.connected.set()
            if self._session.IO_TIMEOUT is not None :
                self.iowatchdog = self.loop.call_later(self._session.IO_TIMEOUT, self.io_timer)
            if self._session.CMD_TIMEOUT is not None :
                self.watchdog = self.loop.call_later(self._session.CMD_TIMEOUT, self.watchdog)

        def connection_lost(self, exc):
            logging.debug('{} node connection lost pid=({})'.format(self._session.name, self._mypid))
            self._session.connected.clear()

        def pipe_data_received(self, fd, data):
            if self._session.IO_TIMEOUT is not None :
                self.iowatchdog.cancel()
            if self.debug :
                logging.debug('{} {}'.format(fd, data))
            self._session.results.extend(data)
            data = data.decode("utf-8")
            if fd == 1:
                self._stdoutbuffer += data
                while "\n" in self._stdoutbuffer:
                    line, self._stdoutbuffer = self._stdoutbuffer.split("\n", 1)
                    logging.info('{} {}'.format(self._session.name, line))

            elif fd == 2:
                self._stderrbuffer += data
                while "\n" in self._stderrbuffer:
                    line, self._stderrbuffer = self._stderrbuffer.split("\n", 1)
                    logging.warning('{} {}'.format(self._session.name, line))

            if self._session.IO_TIMEOUT is not None :
                self.iowatchdog = self.loop.call_later(self._session.IO_TIMEOUT, self.io_timer)

        def pipe_connection_lost(self, fd, exc):
            if self._session.IO_TIMEOUT is not None :
                self.iowatchdog.cancel()
            if fd == 1:
                logging.debug('{} stdout pipe closed (exception={})'.format(self._session.name, exc))
                self._closed_stdout = True
            elif fd == 2:
                logging.debug('{} stderr pipe closed (exception={})'.format(self._session.name, exc))
                self._closed_stderr = True
            self.signal_exit()

        def process_exited(self):
            if self._session.CMD_TIMEOUT is not None :
                self.watchdog.cancel()
            logging.debug('{} subprocess with pid={} closed'.format(self._session.name, self._mypid))
            self._exited = True
            self._mypid = None
            self.signal_exit()

        def watchdog(self, type=None):
            logging.error("{}: timeout: pid={}".format(self._session.name, self._mypid))
 #           self.childprocess.send_signal(signal.SIGKILL)
            self.timeout_occurred.set()
            self.done.set()

        def io_timer(self, type=None):
            logging.error("{} IO timeout: cmd='{}' host(pid)={}({})".format(self._session.name, self._session.cmd, self._session.hostname, self._mypid))
#            self.childprocess.send_signal(signal.SIGKILL)
            self.timeout_occurred.set()
            sshpipe = self._transport.get_extra_info('subprocess')
            sshpipe.terminate()

    def __init__(self, loop=None, user='root', name=None, hostname='localhost', IO_TIMEOUT=None, CMD_TIMEOUT=None, CONNECT_TIMEOUT=None):
        self.ssh = "/usr/bin/ssh"
        self.hostname = hostname
        self.name = name
        self.user = user
        if loop is not None:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()
        self.opened = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
        self.connected = asyncio.Event(loop=self.loop)
        self.closed.set()
        self.opened.clear()
        self.connected.clear()
        self.results = bytearray()
        # self.sshpipe = None
        self.IO_TIMEOUT = IO_TIMEOUT
        self.CMD_TIMEOUT = CMD_TIMEOUT
        self.CONNECT_TIMEOUT = CONNECT_TIMEOUT

    @property
    def is_established(self):
        return self._exited and self._closed_stdout and self._closed_stderr

    def deinit(self) :
        pass
        # self.sshpipe.terminate()

    async def _schedule_sshcmd(self, cmd='pwd') :
        self.opened.clear()
        self.cmd = cmd
        sshcmd = [self.ssh, '{}@{}'.format(self.user, self.hostname), cmd]
        logging.info('{} {}'.format(self.name, sshcmd))
        # self in the ReaderProtocol() is this ssh_session instance
        self._transport, self._protocol = await self.loop.subprocess_exec(lambda: self.SSHReaderProtocol(self), *sshcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=None)
        # self.sshpipe = self._transport.get_extra_info('subprocess')
        # Establish the remote command
        await self.connected.wait()
        # u = '{}\n'.format(cmd)
        # self.sshpipe.stdin.write(u.encode())
        # Wait for the command to complete
        await self.closed.wait()
        return self.results

logfilename='node.log'
print('Writing log to {}'.format(logfilename))
logging.basicConfig(filename=logfilename, level=logging.DEBUG, format='%(asctime)s %(name)s %(module)s %(levelname)-8s %(message)s')
logging.getLogger('asyncio').setLevel(logging.DEBUG)
#loop.set_debug(True)

loop = asyncio.get_event_loop()
duts = [ssh_node(name='4377A', ipaddr='10.19.87.7', device='ap0'), ssh_node(name='4377B', ipaddr='10.19.87.10', device='eth0'), ssh_node(name='4357A', ipaddr='10.19.87.9', device='eth0'), ssh_node(name='4357B', ipaddr='10.19.87.8', device='eth0')]
for dut in duts :
    dut.wl(cmd='status', ASYNC=True)
ssh_node.run_all_commands()
for dut in duts :
    dut.wl(cmd='dump ampdu', ASYNC=False)
ssh_node.run_all_commands()
#print("{}".format(taska.result()))
#print("{}".format(taskb.result()))
loop.close()
