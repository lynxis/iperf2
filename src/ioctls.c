/*---------------------------------------------------------------
 * Copyright (c) 2018
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
 * ioctls.c
 *
 * Code to support ioctls to underlying network interface cards
 * by Robert J. McMahon (rjmcmahon@rjmcmahon.com, bob.mcmahon@broadcom.com)
 * -------------------------------------------------------------------
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <linux/sockios.h>
#include <net/if.h>
#include "headers.h"
#include "Settings.hpp"
#include "SocketAddr.h"
#include "ioctls.h"

int open_ioctl_sock(thread_Settings *inSettings) {
    if (inSettings->mSockIoctl <=0) {
	if ((inSettings->mSockIoctl = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
	    fprintf(stderr, "ioctl sock open error\n");
	}
    }
    return ((inSettings->mSockIoctl > 0) ? 1 : 0);
}

void close_ioctl_sock(thread_Settings *inSettings) {
    if (inSettings->mSockIoctl > 0) {
	if (close(inSettings->mSockIoctl) < 0)
	    fprintf(stderr, "ioctl sock close error\n");
    }
    inSettings->mSockIoctl = 0;
}

/*
 *  802.11 TSF are microsecond timers per each BSS that are synchronized in frequency only, i.e. the values
 *  per any running TSF can vary though they are frequency locked.  They are aslo 32bit values.   This code
 *  will syncronize them using the GPS timestamps (which are assumed to be synched via something like PTP.)
 *  This will allow taking usecond measurement across TSF clocks.
 *
 *  Note:  The drift between the GPS clock and the TSF clocks is not currently handled.  If one
 *  needs to measure between these two domains, sychronizing the drift will be required.
 */
u_int32_t read_80211_tsf(thread_Settings *inSettings) {
    u_int32_t tsfnow = 0xFFFFFFFF;
    if (open_ioctl_sock(inSettings)) {
	struct ifreq ifr = {0};
	struct dhd_ioctl {
	    unsigned int cmd;
	    void *buf;
	    unsigned int len;
	    unsigned int set;
	    unsigned int used;
	    unsigned int needed;
	    unsigned int driver;
	};
	struct sdreg {
	    int func;
	    int offset;
	    int value;
	};

	struct dhd_ioctl ioc;
	struct sdreg sbreg;
	if (inSettings->mIfrname == NULL) {
	    SockAddr_Ifrname(inSettings);
	}
	snprintf(ifr.ifr_name, IF_NAMESIZE, inSettings->mIfrname);
	char buf[8+sizeof(struct sdreg)];
	snprintf(buf, 6, "sbreg");
	sbreg.func = 4;
	sbreg.offset = 0x18001180;
	memcpy(&buf[6], &sbreg, sizeof(sbreg));
	ioc.cmd = 2;
	ioc.buf = buf;
	ioc.len = sizeof(buf);
	ioc.set = 0;
	ioc.driver = 0x00444944;
	ifr.ifr_data = (caddr_t)&ioc;

	int ret = ioctl(inSettings->mSockIoctl, SIOCDEVPRIVATE, &ifr);
	if (ret < 0) {
	    fprintf(stderr, "ioctl read tsf error %d\n", ret);
	} else {
	    memcpy(&tsfnow, ioc.buf, 4);
	}
    }
    return(tsfnow);
}

#define BILLION 10000000000
#define MILLION 1000000
#define TSFCARRYSEC (0XFFFFFFFF / MILLION)
#define TSFCARRYUSEC (0XFFFFFFFF % MILLION)
static void tsf2timespec(tsftv_t *tsf, struct timespec *tv) {
    tv->tv_sec = (tsf->raw / MILLION);
    tv->tv_nsec = (tsf->raw % MILLION) * 1000;
    if (tsf->carry) {
	tv->tv_sec += (TSFCARRYSEC * tsf->carry);
	tv->tv_nsec += TSFCARRYUSEC * 1000;
	if (tv->tv_nsec >= BILLION) {
	    tv->tv_sec++;
	    tv->tv_nsec -= BILLION;
	}
    }
}

static void timespec_sub(const struct timespec *start, const struct timespec *stop, struct timespec *result) {
    if ((stop->tv_nsec - start->tv_nsec) < 0) {
        result->tv_sec = stop->tv_sec - start->tv_sec - 1;
        result->tv_nsec = stop->tv_nsec - start->tv_nsec + BILLION;
    } else {
        result->tv_sec = stop->tv_sec - start->tv_sec;
        result->tv_nsec = stop->tv_nsec - start->tv_nsec;
    }
    return;
}

static void timespec_add(const struct timespec *time1, const struct timespec *time2, struct timespec *result) {
    result->tv_sec = time1->tv_sec + time2->tv_sec;
    result->tv_nsec = time1->tv_sec + time2->tv_nsec;
    if (result->tv_nsec > BILLION) {
        result->tv_sec +=1;;
        result->tv_nsec -= BILLION;
    }
    return;
}


// Assumes sequential calls which are monotonic in TSF time
void tsfraw_update(tsftv_t *tsf, u_int32_t rawnow) {
    if (tsf->raw == 0xFFFFFFFF) {
	tsf->carry = 0;
    } else if (tsf->raw > rawnow) {
	tsf->carry++;
    }
    tsf->raw = rawnow;
    if (!tsf->synced) {
	fprintf(stdout,"TSF cannot be synced to GPS time");
        tsf->refnow_gpsdomain.tv_sec=0;
	tsf->refnow_gpsdomain.tv_nsec=0;
    } else {
	struct timespec res;
	tsf2timespec(tsf, &tsf->refnow_refdomain);
	timespec_sub(&tsf->refnow_refdomain, &tsf->gpsref_sync.ref_ts, &res);
	timespec_add(&tsf->gpsref_sync.gps_ts, &res, &tsf->refnow_gpsdomain);
    }
    return;
}

// Apply the syncronization either by a given sync structure
// or by reading the realtime clock and the reference time together
void tsfgps_sync (tsftv_t *tsf,  struct gpsref_sync_t *t, thread_Settings *agent) {
    if (!t) {
	struct timespec t1;
	clock_gettime(CLOCK_REALTIME, &t1);
	tsf->raw = read_80211_tsf(agent);
	tsf2timespec(tsf, &tsf->gpsref_sync.ref_ts);
	tsf->gpsref_sync.gps_ts.tv_sec  = t1.tv_sec;
	tsf->gpsref_sync.gps_ts.tv_nsec  = t1.tv_nsec;
	tsf->raw = 0xFFFFFFFF;
    } else {
	tsf->gpsref_sync.gps_ts.tv_sec  = t->gps_ts.tv_sec;
	tsf->gpsref_sync.gps_ts.tv_nsec  = t->gps_ts.tv_nsec;
	tsf->gpsref_sync.ref_ts.tv_sec  = t->ref_ts.tv_sec;
	tsf->gpsref_sync.ref_ts.tv_nsec  = t->ref_ts.tv_nsec;
	tsf->raw = 0xFFFFFFFF;
    }
    tsf->synced = 1;
}

float tsf_sec_delta(tsftv_t *tsf_a, tsftv_t *tsf_b) {
    struct timespec res;
    timespec_sub(&tsf_b->refnow_gpsdomain, &tsf_a->refnow_gpsdomain, &res);
    return (((float) (res.tv_sec * BILLION) + res.tv_nsec) / BILLION);
}
