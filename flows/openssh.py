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
import time, asyncio, subprocess, sys, logging

class ssh_session:
    def __init__(self):
        self.done = asyncio.Event()
        self.IO_TIMEOUT = 2.0
        self.loop = asyncio.get_event_loop()
        self.ssh = "/usr/bin/ssh"

    async def rexec(self, cmd ="pwd", host="localhost"):
        self.done.clear()
        try:
            self.childprocess = subprocess.Popen([self.ssh, str(host), str(cmd)], bufsize=1, universal_newlines = True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            self.loop.add_reader(self.childprocess.stdout, self.stdout_event)
            self.loop.add_reader(self.childprocess.stderr, self.stderr_event)
            self.iowatchdog = self.loop.call_later(self.IO_TIMEOUT, self.io_timer) 
            await self.done.wait()
            self.iowatchdog.cancel()
            self.loop.remove_reader(self.childprocess.stdout)
            self.loop.remove_reader(self.childprocess.stderr)
        except:
            pass

    def stdout_event(self):
        data = self.childprocess.stdout.readline()
        self.iowatchdog.cancel()
        self.iowatchdog = self.loop.call_later(self.IO_TIMEOUT, self.io_timer) 
        if data :
            print("stdout> {}".format(data),end='')
        else :
            self.childprocess.poll()
            if self.childprocess.returncode is not None :
                self.childprocess.stdout.close()
                self.close_actions(origin="stdout")

    def stderr_event(self):
        data = self.childprocess.stderr.readline()
        self.iowatchdog.cancel()
        self.iowatchdog = self.loop.call_later(self.IO_TIMEOUT, self.io_timer) 
        if data :
            print("stderr> {}".format(data), end='')
        else :
            self.childprocess.poll()
            if self.childprocess.returncode is not None :
                self.childprocess.stderr.close()
                self.close_actions(origin="stderr")

    def close_actions(self,origin):
        self.returncode = self.childprocess.returncode
        if self.childprocess.stdout.closed and self.childprocess.stderr.closed :
            self.done.set()    

    def io_timer(self):
        self.done.set()

        
