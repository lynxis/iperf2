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
 * ioctls.h
 * Suppport for driver/device ioctls
 *
 * by Robert J. McMahon (rjmcmahon@rjmcmahon.com, bob.mcmahon@broadcom.com)
 * -------------------------------------------------------------------
 */
#ifndef IOCTLSC_H
#define IOCTLSC_H

#include "Settings.hpp"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct tsfgps_sync_t {
    u_int32_t tsf_ts;
    struct timeval gps_ts;
} tsfgps_sync_t;

typedef struct tsftv_t {
    int synced;
    u_int32_t tsfcarry;
    u_int32_t tsfraw;
    struct tsfgps_sync_t tsfgpssync;
    struct timeval tsfgps_t0;
    float tsfgps_now;
} tsftv_t;

extern int open_ioctl_sock(struct thread_Settings *inSettings);
extern void close_ioctl_sock(struct thread_Settings *inSettings);
extern u_int32_t read_80211_tsf(struct thread_Settings *inSettings);
extern void tsfraw_update(tsftv_t *tsf, u_int32_t tsfrawnow);
extern void tsfgps_sync (tsftv_t *tsf_a,  struct tsfgps_sync_t *t, struct thread_Settings *agent);
extern float tsf_usec_delta(tsftv_t *tsf_a, tsftv_t *tsf_b);
extern float tsf_sec_delta(tsftv_t *tsf_a, tsftv_t *tsf_b);

#ifdef __cplusplus
} /* end extern "C" */
#endif

#endif // IOCTLS
