#!/usr/bin/env python3.5
#
# Python object to support remote command and remote pipes over openssh with concurrency
#
# Basic use looks something like:
#    sessions = [ssh_session() for i in range(count)]
#    loop = asyncio.get_event_loop()
#    tasks = [asyncio.ensure_future(session.rexec(host=remotehost,cmd=remotecommand)) for session in sessions]
#    loop.run_until_complete(asyncio.wait(tasks))
#    loop.close
#
#
# Author Robert J. McMahon
# Date July 2016
import re
import subprocess
import logging
import asyncio, sys
import time
import locale
import signal
import os, fcntl


logger = logging.getLogger(__name__)

class ssh_session:
    def __init__(self, loop=None, user='root', host='localhost', cmd='pwd'):
        self.IO_TIMEOUT = 2.0
        self.CMD_TIMEOUT = 30
        self.ssh = "/usr/bin/ssh"
        self.host = host
        self.user = user
        self.cmd = cmd
        if loop is not None:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()
        self.done = asyncio.Event(loop=loop)

    async def rexec(self, cmd=None):
        self.done.clear()
        try:
            sshcmd = [self.ssh, self.user + "@" + self.host, self.cmd]
            logging.info('{}({}) {}'.format(self.user, self.host, str(sshcmd)))
            self.childprocess = subprocess.Popen(sshcmd, bufsize=1, universal_newlines = True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            self.loop.add_reader(self.childprocess.stdout, self.stdout_event)
            self.loop.add_reader(self.childprocess.stderr, self.stderr_event)
            self.iowatchdog = self.loop.call_later(self.IO_TIMEOUT, self.io_timer)
            logging.debug('await rexec pid={}'.format(self.childprocess.pid))
            await self.done.wait()
            self.iowatchdog.cancel()
            logging.debug('await rexec done: pid={}'.format(self.childprocess.pid))

        except:
            logging.error("{}({}) {}".format(str(self.host), str(sshcmd)))
            pass

    def stdout_event(self):
        self.iowatchdog.cancel()
        trailer = '{}({})'.format(self.childprocess.pid, self.childprocess.stdout.name)
        while True :
            data = self.childprocess.stdout.readline()
            if data :
                logging.info('{}: {} {}'.format(self.host, str(data).strip('\r\n'), trailer))
                trailer = ''
            else :
                break

        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            logging.debug("{}: stdout closed: pid={}".format(self.host, self.childprocess.pid))
            self.childprocess.stdout.close()
            self.loop.remove_reader(self.childprocess.stdout)
            self.close_actions(origin="stderr")
        else :
            self.iowatchdog = self.loop.call_later(self.IO_TIMEOUT, self.io_timer)

    def stderr_event(self):
        self.iowatchdog.cancel()
        trailer = '{}({})'.format(self.childprocess.pid, self.childprocess.stderr.name)
        while True :
            data = self.childprocess.stderr.readline()
            if data :
                logging.info('{}: {} {}'.format(self.host, str(data).strip('\r\n'), trailer))
                trailer = ''
            else :
                break

        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            logging.debug("{}: stderr closed: pid={}".format(self.host, self.childprocess.pid))
            self.childprocess.stderr.close()
            self.loop.remove_reader(self.childprocess.stderr)
            self.close_actions(origin="stderr")
        else :
            self.iowatchdog = self.loop.call_later(self.IO_TIMEOUT, self.io_timer)

    def close_actions(self,origin):
        self.returncode = self.childprocess.returncode
        if self.childprocess.stdout.closed and self.childprocess.stderr.closed :
            logging.debug("{}: DONE pid={}".format(self.host, self.childprocess.pid))
            self.done.set()

    def io_timer(self):
        logging.debug("{}: IO timeout: pid={}".format(self.host, self.childprocess.pid))
        self.childprocess.send_signal(signal.SIGKILL)
        self.done.set()


