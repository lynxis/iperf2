/*---------------------------------------------------------------
 * Copyright (c) 2017
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
 * checkisoch.cpp
 *
 * Test routine to test the isochronous functions
 *
 * by Robert J. McMahon (rjmcmahon@rjmcmahon.com, bob.mcmahon@broadcom.com)
 * ------------------------------------------------------------------- */

/* Produce normal and log normal
 *
 * Implements the Polar form of the Box-Muller Transformation
 *
 *
*/
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <errno.h>
#include <string.h>
#include "headers.h"
#include "isochronous.hpp"
#include  "delay.h"

static void posttimestamp(int);

int main (int argc, char **argv) {
    int c, count=61, frequency=60;

    Isochronous::FrameCounter *fc = NULL;
    
    while ((c = getopt(argc, argv, "c:f:")) != -1) {
        switch (c) {
        case 'c':
            count = atoi(optarg);
            break;
        case 'f':
	    frequency = atoi(optarg);
            break;
        case '?':
            fprintf (stderr, "usage: -c <count> -f <frames per second> \n");
            return 1;
        default:
            abort ();
        }
    }
    fc = new Isochronous::FrameCounter(frequency);

    fprintf(stdout,"Timestamping %d times at %d fps\n", count, frequency);
    fflush(stdout);
    while (count-- > 0) {
	if (count == 8) {
	    delay_loop (1000000/frequency + 10);
	}
	fc->wait_tick();
	posttimestamp(count);
	if (fc->slip) {
	    fprintf(stdout,"Slip occurred\n");
	    fc->slip = 0;
	}
    }
}

void posttimestamp (int count) {
    struct timespec t1;
    double timestamp;
    int err;

    err = clock_gettime(CLOCK_REALTIME, &t1);
    if (err < 0) {
        perror("clock_getttime");
    } else {
        timestamp = t1.tv_sec + (t1.tv_nsec / 1000000000.0);
        fprintf(stdout,"%f counter(%d)\n", timestamp, count);
    }
    fflush(stdout);
}
