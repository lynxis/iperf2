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

logging.basicConfig(filename='flowtest.log', level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)-8s %(message)s')

class iperf_flow:
    port = 61000
    iperf = "/usr/bin/iperf"
    
    def __init__(self, name="iperf"):
        mystate = "INIT"
        self.name = name
        self.logger = logging.getLogger('')
        iperf_flow.port += 1
        self.rx = iperf_server(name=name + '->RX')
        self.tx = iperf_client(name=name + '->TX')
        self.rx.peer = self.tx
        self.tx.peer = self.rx
        self.rx.flow = self
        self.tx.flow = self
        self.rx.port = iperf_flow.port
        self.tx.port = iperf_flow.port

    def start(self):
        logging.info(self.name + " " + "Start")
        self.rx.start()
        self.tx.start()
        
    def stop(self):
        logging.info(self.name + " " + "Stop")
        self.rx.stop()
        self.tx.stop()

    def stats(self):
        self.logging.info("stats")

class iperf_server():
    def __init__(self, name="Server"):
        mystate = "INIT"
        self.name = name
        
    def __getattribute__(self, attr):
        try:
            return object.__getattribute__(self, attr)
        except AttributeError:
            return getattr(iperf_flow, attr)
        
    def start(self):
        logging.info(self.name + " " + "Start")
        self.childprocess = subprocess.Popen([self.iperf, "-s", "-p" + str(self.port), "-e", "-i 0.5" , "-t 3600"], bufsize=1, universal_newlines = True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        print("server start pid=%d" % self.childprocess.pid)
        loop = asyncio.get_event_loop()
        loop.add_reader(self.childprocess.stdout, self.server_stdout_event)
        loop.add_reader(self.childprocess.stderr, self.server_stderr_event)

    def stop(self):
        logging.info(self.name + " " + "Stop")
        self.childprocess.kill()
        
    def server_stdout_event(self):
        data = self.childprocess.stdout.readline()
        if data is not None :
            print("{} {}".format(self.name, data))
        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            loop.remove_reader(self.childprocess.stdout)
            print("{} stdout> Finished".format(self.name))

    def server_stderr_event(self):
        data = self.childprocess.stderr.readline()
        if data :
            print("{} stdout> {}".format(self.name, data))
        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            loop.remove_reader(self.childprocess.stderr)
            print("{} stdout> Finished".format(self.name))
        
class iperf_client():
    def __init__(self, name="Client"):
        mystate = "INIT"
        self.name = name

    def __getattribute__(self, attr):
        try:
            return object.__getattribute__(self, attr)
        except AttributeError:
            return getattr(iperf_flow, attr)
        
    def start(self):
        logging.info(self.name + " " + "Start")
        logging.info("TX Start")
        self.childprocess = subprocess.Popen([self.iperf, "-c", "localhost", "-p" + str(self.port), "-e", "-i 0.5", "-t 3600"], bufsize=1, universal_newlines = True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        print("client start pid=%d" % self.childprocess.pid)
        loop = asyncio.get_event_loop()
        loop.add_reader(self.childprocess.stdout, self.client_stdout_event)
        loop.add_reader(self.childprocess.stderr, self.client_stderr_event) 

    def stop(self):
        logging.info(self.name + " " + "Stop")
        self.childprocess.send_signal(signal.SIGINT)
        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            self.childprocess.kill()

    def pause(self) :
        self.childprocess.send_signal(signal.SIGSTOP)
        
    def resume(self) :
        self.childprocess.send_signal(signal.SIGCONT)
        
    def client_stdout_event(self):
        data = self.childprocess.stdout.readline()
        if data :
            print("{} stdout> {}".format(self.name, data))
        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            loop.remove_reader(self.childprocess.stdout)
            print("{} stdout> Finished".format(self.name))
            self.peer.stop()
            
    def client_stderr_event(self):
        data = self.childprocess.stderr.readline()
        if data :
            print("{} stderr> {}".format(self.name, data))
        self.childprocess.poll()
        if self.childprocess.returncode is not None :
            loop.remove_reader(self.childprocess.stderr)
            print("{} stderr> Finished".format(self.name))
            self.peer.stop()
            
