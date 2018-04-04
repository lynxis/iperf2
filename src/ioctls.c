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

#define MILLION 1000000
static void tsf2gps (tsftv_t *tsf) {
    if (!tsf->synced) {
	fprintf(stdout,"TSF not synced to GPS and tsf2gps() called");
    }
    int carry_sec = tsf->tsfcarry * (0xFFFFFFFF / MILLION);
    int carry_usec = (carry_sec ? (0xFFFFFFFF % MILLION) : 0);
    int usec = (tsf->tsfraw % MILLION) + carry_usec + tsf->tsfgps_t0.tv_usec;
    int sec = (tsf->tsfraw / MILLION) + carry_sec + tsf->tsfgps_t0.tv_sec;
    if (usec > MILLION) {
	usec = usec - MILLION;
	sec++;
    }
    tsf->tsfgps_now.tv_sec = sec;
    tsf->tsfgps_now.tv_usec = usec;
}

// Assumes sequential calls which are monotonic in TSF time
void tsfraw_update(tsftv_t *tsf, u_int32_t tsfrawnow) {
    if (tsf->tsfraw > tsfrawnow) {
	tsf->tsfcarry++;
    }
    tsf->tsfraw = tsfrawnow;
    tsf2gps(tsf);
    return;
}

void tsfgps_sync (tsftv_t *tsf,  struct tsfgps_sync_t *t, thread_Settings *agent) {
    if (!t) {
	struct timespec t1;
	clock_gettime(CLOCK_REALTIME, &t1);
	tsf->tsfgpssync.gps_ts.tv_sec  = t1.tv_sec;
	tsf->tsfgpssync.gps_ts.tv_usec  = t1.tv_nsec / 1000;
	tsf->tsfgpssync.tsf_ts = read_80211_tsf(agent);
    } else {
	tsf->tsfgpssync.gps_ts.tv_sec  = t->gps_ts.tv_sec;
	tsf->tsfgpssync.gps_ts.tv_usec  = t->gps_ts.tv_usec;
	tsf->tsfgpssync.tsf_ts = t->tsf_ts;
    }
    u_int32_t usec = tsf->tsfgpssync.tsf_ts % MILLION;
    if (usec > tsf->tsfgpssync.gps_ts.tv_usec) {
	tsf->tsfgps_t0.tv_usec = tsf->tsfgpssync.gps_ts.tv_usec + MILLION - usec;
	tsf->tsfgps_t0.tv_sec = tsf->tsfgpssync.gps_ts.tv_sec - (tsf->tsfgpssync.tsf_ts / MILLION) - 1;
    } else {
	tsf->tsfgps_t0.tv_usec = tsf->tsfgpssync.gps_ts.tv_usec - usec;
	tsf->tsfgps_t0.tv_sec = tsf->tsfgpssync.gps_ts.tv_sec - (tsf->tsfgpssync.tsf_ts / MILLION);
    }
    tsf->synced = 1;
}


u_int32_t tsf_usec_delta(tsftv_t *tsf_a, tsftv_t *tsf_b) {
    return ((tsf_a->tsfgps_now.tv_sec  - tsf_b->tsfgps_now.tv_sec) * MILLION) + (tsf_a->tsfgps_now.tv_usec - tsf_b->tsfgps_now.tv_usec);
}

float tsf_sec_delta(tsftv_t *tsf_a, tsftv_t *tsf_b) {
    return (((float) ((tsf_a->tsfgps_now.tv_sec  - tsf_b->tsfgps_now.tv_sec) * MILLION) + (tsf_a->tsfgps_now.tv_usec - tsf_b->tsfgps_now.tv_usec)) / 1e6);
}
