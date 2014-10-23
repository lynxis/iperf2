/*--------------------------------------------------------------- 
 * Copyright (c) 2014                              
 * Broadcom Corporation           
 * All Rights Reserved.                                           
 *--------------------------------------------------------------- 
 * Permission is hereby granted, free of charge, to any person    
 * obtaining a copy of this software and associated       
 * documentation files (the "Software"), to deal in the Software  
 * without restriction, including without limitation the          
 * rights to use, copy, modify, merge, publish, distribute,        
 * sublicense, and/or sell copies of the Software, and to permit     
 * persons to whom the Software is furnished to do
 * so, subject to the following conditions: 
 *
 *     
 * Redistributions of source code must retain the above 
 * copyright notice, this list of conditions and 
 * the following disclaimers. 
 *
 *     
 * Redistributions in binary form must reproduce the above 
 * copyright notice, this list of conditions and the following 
 * disclaimers in the documentation and/or other materials 
 * provided with the distribution. 
 * 
 *     
 * Neither the name of Broadcom Coporation, 
 * nor the names of its contributors may be used to endorse 
 * or promote products derived from this Software without
 * specific prior written permission. 
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, 
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES 
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND 
 * NONINFRINGEMENT. IN NO EVENT SHALL THE CONTIBUTORS OR COPYRIGHT 
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, 
 * ARISING FROM, OUT OF OR IN CONNECTION WITH THE
 * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. 
 * ________________________________________________________________
 *
 * checkdelay.c
 * Simple tool to measure mean/min/max of nanosleep
 * by Robert J. McMahon (rjmcmahon@rjmcmahon.com, rmcmahon@broadcom.com)
 * ------------------------------------------------------------------- */
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <sched.h>
#include <error.h>
#include <time.h>
#include <sys/mman.h>
#include <ctype.h>
#include <unistd.h>

void delay_loop( unsigned long usecs );

int main (int argc, char **argv) {
    struct timespec tsp0, tsp1, dummy;
    double sum=0;
    long delta, max=0, min=-1,t1, t0;
    int ix, jx=0, delay=1,loopcount=1000000;
    int c;
    int realtime = 0;
    int affinity = 0;
    int clockgettime = 0;
    struct sched_param sp;
    
    while ((c=getopt(argc, argv, "a:cd:i:r")) != -1) 
	switch (c) {
	case 'a':
	    affinity=atoi(optarg);
	    break;
	case 'c':
	    clockgettime = 1;
	    break;
	case 'd':
	    delay = atoi(optarg);
	    break;
	case 'i':
	    loopcount = atoi(optarg);
	    break;
	case 'r':
	    realtime = 1;
	    break;
	case '?':
	    fprintf(stderr,"Usage -a affinity, -d usec delay, -i iterations, -r realtime\n");
	    return 1;
	default:
	    abort();
	}
    
    if (realtime) {
	fprintf(stdout,"Setting scheduler to realtime via SCHED_RR\n", affinity);
	// SCHED_OTHER, SCHED_FIFO, SCHED_RR
	sp.sched_priority = sched_get_priority_max(SCHED_RR); 
	if (sched_setscheduler(0, SCHED_RR, &sp) < 0) 
	    perror("Client set scheduler");
	// lock the threads memory
	if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0)
	    perror ("mlockall");
    }
    if (affinity) {
	fprintf(stdout,"CPU affinity set to %d\n", affinity);
	cpu_set_t myset;
	CPU_ZERO(&myset);
	CPU_SET(affinity,&myset);
    }
    if (clockgettime) 
	if (loopcount > 1000) 
	    fprintf(stdout,"Measuring clock_gettime syscall over %.0e iterations using %d usec delay\n", (double) loopcount, delay);
	else 
	    fprintf(stdout,"Measuring clock_gettime syscall over %d iterations using %d usec delay\n", loopcount, delay);
    else 
	if (loopcount > 1000) 
	    fprintf(stdout,"Measuring nanosleep syscall over %.0e iterations using %d usec delay\n", (double) loopcount, delay);
	else 
	    fprintf(stdout,"Measuring nanosleep syscall over %d iterations using %d usec delay\n", loopcount, delay);
    for (ix=0; ix < loopcount; ix++) {
	// Find the max jitter for delay call
	clock_gettime(CLOCK_REALTIME, &tsp0);
	if (clockgettime) 
	    clock_gettime(CLOCK_REALTIME, &dummy);
	else 
	    delay_loop(delay); 
	clock_gettime(CLOCK_REALTIME, &tsp1);
	if (tsp0.tv_sec == tsp1.tv_sec) {
	    delta = (tsp1.tv_nsec - tsp0.tv_nsec);
	    if (delta > max) {
		max = delta;
	    }
	    if (delta < min || min == -1) {
		min = delta;
	    }
	    sum += (double) delta;
	    jx++;
	}
    }
    fprintf(stdout,"delay=%.0f/%ld/%ld ns (mean/min/max)\n", (sum / jx), min, max);
}

void delay_loop(unsigned long usec) {
    struct timespec requested, remaining;

    requested.tv_sec  = 0;
    requested.tv_nsec = usec * 1000L;

    if (nanosleep(&requested, &remaining) < 0) {
	fprintf(stderr,"Nanosleep failed\n");
	exit(-1);
    }
}



