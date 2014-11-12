/*--------------------------------------------------------------- 
 * Copyright (c) 1999,2000,2001,2002,2003                              
 * The Board of Trustees of the University of Illinois            
 * All Rights Reserved.                                           
 *--------------------------------------------------------------- 
 * Permission is hereby granted, free of charge, to any person    
 * obtaining a copy of this software (Iperf) and associated       
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
 * Neither the names of the University of Illinois, NCSA, 
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
 * National Laboratory for Applied Network Research 
 * National Center for Supercomputing Applications 
 * University of Illinois at Urbana-Champaign 
 * http://www.ncsa.uiuc.edu
 * ________________________________________________________________ 
 *
 * delay.c
 * by Mark Gates <mgates@nlanr.net>
 * updates 
 * by Robert J. McMahon <rmcmahon@broadcom.com> <rjmcmahon@rjmcmahon.com>
 * -------------------------------------------------------------------
 * attempts at accurate microsecond delays
 * ------------------------------------------------------------------- */

#include "Timestamp.hpp"
#include "util.h"
#include "delay.hpp"

#define MILLION 1000000.0
#define BILLION 1000000000.0

/* -------------------------------------------------------------------
 * A micro-second delay function
 * o Use a busy loop or nanosleep
 * 
 * Some notes:
 * o clock_gettime() (if available) is preferred over gettimeofday() 
 *   becausethere are no time adjustments (e.g. ntp) and clock_getttime() 
 *   support nanosecond resolution vs microsecond for gettimeofday()
 * o Not using Timestamp object here as the goal of these functions is
 *   accurate delays (vs accurate timestamps.)
 * o The syscalls such as nanosleep guarantee at least the request time
 *   and can delay longer, particularly due to things like context 
 *   switching, causing the delay to lose accuracy
 * o Kalman filtering is used for to predict delay error which in turn
 *   is used to adjust the delay, mitigating the described above.  
 *   Note:  This can cause the delay to return faster than the request,
 *   i.e. the *at least* guarantee is not preserved for the kalman
 *   adjused delay calls.
 * o Remember, the Client is keeping a running average delay for the 
 *   thread so errors in delay will also be adjusted there. (Assuming 
 *   it's possible.  It's not really possible at top line link rates 
 *   because lost time can't be made up for by speeding up the transmits.  
 *   Hence, don't lose time with delay calls which error on the side of 
 *   taking too long.  Kalman should help much here.)
 * 
 * POSIX nanosleep(). This allowss a higher timing resolution 
 * (under Linux e.g. it uses hrtimers), does not affect any signals, 
 * and will use up remaining time when interrupted.
 * ------------------------------------------------------------------- */
void delay_loop(unsigned long usec)
{
#ifdef HAVE_KALMAN
    delay_kalman(usec);
#else
#ifdef HAVE_NANOSLEEP
    delay_nanosleep(usec);
#else
    delay_busyloop(usec);
#endif
#endif
}

// A cpu busy loop
void delay_busyloop (unsigned long usec) {
#ifdef HAVE_CLOCK_GETTIME
    struct timespec t1, t2; 
    double time1, time2, sec;

    sec = usec / MILLION;
    clock_gettime(CLOCK_REALTIME, &t1);
    time1 = t1.tv_sec + (t1.tv_nsec / BILLION);
    while (1) {
	clock_gettime(CLOCK_REALTIME, &t2);
	time2 = t2.tv_sec + (t2.tv_nsec / BILLION);
	if ((time2 - time1) >= sec) {
	    break;
	}
    }
#else
    struct timeval t1, t2;
    double time1, time2, sec;

    sec = usec / MILLION;
    gettimeofday( &t1, NULL );
    time1 = t1.tv_sec + (t1.tv_usec / MILLION);
    while (1) {
	gettimeofday( &t2, NULL );
	time2 = t2.tv_sec + (t2.tv_usec / MILLION);
	if ((time2 - time1) >= sec) 
	    break;
    }
#endif
}

#ifdef HAVE_NANOSLEEP
// Use the nanosleep syscall
void delay_nanosleep (unsigned long usec) {
    if (usec < 1000) {
        // Don't call nanosleep for values less than 1 microsecond
        // the syscall is too expensive.  Let the busy loop
        // provide the delay.
        delay_busyloop(usec);
    } else {
        struct timespec requested, remaining;

        requested.tv_sec  = 0;
        requested.tv_nsec = usec * 1000L;

	if (nanosleep(&requested, &remaining) < 0) {
	    fprintf(stderr,"Nanosleep failed\n");
	    exit(-1);
	}
    }
}
#endif
// Kalman versions below that should support accuracy
// over a minimum guaranteed delay.  The preferred function
// to use for accurate delay is delay_nanosleep_kalman()
void kalman_update (kalman_state *state, double measurement) {
    //prediction update
    state->p = state->p + state->q;
    //measurement update
    state->k = state->p / (state->p + state->r);
    state->x = state->x + (state->k * (measurement - state->x));
    state->p = (1 - state->k) * state->p; 
}

void delay_kalman (unsigned long usec) {
#ifdef HAVE_NANOSLEEP
    struct timespec requested, remaining;
#endif
#ifdef HAVE_CLOCK_GETTIME
    struct timespec t1, t2;
#else
    struct timeval t1, t2;
#endif
    double time1, time2, sec, err;
    static kalman_state kalmanerr={
	0.00001, //q process noise covariance
	0.1, //r measurement noise covariance
	0.0, //x value
	1, //p estimation error covariance
	1 //k kalman gain
    };
    sec = (usec / MILLION) - kalmanerr.x;
#ifdef HAVE_NANOSLEEP
    if (sec > 0) {
	requested.tv_sec  = (long) sec;
	requested.tv_nsec = (sec - requested.tv_sec) * 1e9;
    } else {
	sec = 0.0;
    }
#endif
#ifdef HAVE_CLOCK_GETTIME
    clock_gettime(CLOCK_REALTIME, &t1);
    time1 = t1.tv_sec + (t1.tv_nsec / BILLION);
#else
    gettimeofday( &t1, NULL );
    time1 = t1.tv_sec + (t1.tv_usec / MILLION);
#endif
    // Don't call nanosleep for values less than 1 microsecond
    // the syscall is too expensive.  Let the busy loop
    // provide the delay.
#ifdef HAVE_NANOSLEEP
    if (sec > (1 / MILLION)) {
	if (nanosleep(&requested, &remaining) < 0) {
	    fprintf(stderr,"Nanosleep failed\n");
	    exit(-1);
	}
    }
#endif
    while (1) {
#ifdef HAVE_CLOCK_GETTIME
	clock_gettime(CLOCK_REALTIME, &t2);
	time2 = t2.tv_sec + (t2.tv_nsec / BILLION);
#else
	gettimeofday( &t2, NULL );
	time2 = t2.tv_sec + (t2.tv_usec / MILLION);
#endif
	if ((time2 - time1) >= sec) {
	    break;
	}
    }
    err = (time2 - time1) - sec;
    kalman_update(&kalmanerr, err);
}

