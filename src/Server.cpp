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
 * Server.cpp
 * by Mark Gates <mgates@nlanr.net>
 *     Ajay Tirumala (tirumala@ncsa.uiuc.edu>.
 * -------------------------------------------------------------------
 * A server thread is initiated for each connection accept() returns.
 * Handles sending and receiving data, and then closes socket.
 * Changes to this version : The server can be run as a daemon
 * ------------------------------------------------------------------- */

#define HEADERS()

#include "headers.h"
#include "Server.hpp"
#include "List.h"
#include "Extractor.h"
#include "Reporter.h"
#include "Locale.h"
#include "delay.h"
#ifdef HAVE_SCHED_SETSCHEDULER
#include <sched.h>
#endif
#ifdef HAVE_MLOCKALL
#include <sys/mman.h>
#endif

/* -------------------------------------------------------------------
 * Stores connected socket and socket info.
 * ------------------------------------------------------------------- */

Server::Server( thread_Settings *inSettings ) {
    mSettings = inSettings;
    mBuf = NULL;

#ifdef HAVE_AF_PACKET
    if (isL2LengthCheck(mSettings) || isL2MACHash(mSettings) ||  isL2FrameHash(mSettings)) {
	// For L2 UDP make sure we can receive a full ethernet packet plus a bit more
	if (mSettings->mBufLen < (2 * ETHER_MAX_LEN)) {
	    mSettings->mBufLen = (2 * ETHER_MAX_LEN);
	}
    }
#endif
    // initialize buffer, length checking done by the Listener
    mBuf = new char[((mSettings->mBufLen > SIZEOF_MAXHDRMSG) ? mSettings->mBufLen : SIZEOF_MAXHDRMSG)];
    FAIL_errno( mBuf == NULL, "No memory for buffer\n", mSettings );
}

/* -------------------------------------------------------------------
 * Destructor close socket.
 * ------------------------------------------------------------------- */

Server::~Server() {
    if ( mSettings->mSock != INVALID_SOCKET ) {
        int rc = close( mSettings->mSock );
        WARN_errno( rc == SOCKET_ERROR, "close" );
        mSettings->mSock = INVALID_SOCKET;
    }
    if ( mSettings->mSockDrop != INVALID_SOCKET ) {
	int rc = close( mSettings->mSockDrop );
        WARN_errno( rc == SOCKET_ERROR, "close" );
        mSettings->mSockDrop = INVALID_SOCKET;
    }
    // RJM, fix this, decrement the fanout packet group
    DELETE_ARRAY( mBuf );
}

#ifdef HAVE_AF_PACKET
uint32_t Server::murmur3_32(uint32_t len, uint32_t seed) {
    static const uint32_t c1 = 0xcc9e2d51;
    static const uint32_t c2 = 0x1b873593;
    static const uint32_t r1 = 15;
    static const uint32_t r2 = 13;
    static const uint32_t m = 5;
    static const uint32_t n = 0xe6546b64;

    uint32_t hash = seed;

    const int nblocks = len / 4;
    const uint32_t *blocks = (const uint32_t *) mBuf;
    int i;
    for (i = 0; i < nblocks; i++) {
        uint32_t k = blocks[i];
        k *= c1;
        k = (k << r1) | (k >> (32 - r1));
        k *= c2;

        hash ^= k;
        hash = ((hash << r2) | (hash >> (32 - r2))) * m + n;
    }

    const uint8_t *tail = (const uint8_t *) (mBuf + nblocks * 4);
    uint32_t k1 = 0;

    switch (len & 3) {
    case 3:
        k1 ^= tail[2] << 16;
    case 2:
        k1 ^= tail[1] << 8;
    case 1:
        k1 ^= tail[0];

        k1 *= c1;
        k1 = (k1 << r1) | (k1 >> (32 - r1));
        k1 *= c2;
        hash ^= k1;
    }

    hash ^= len;
    hash ^= (hash >> 16);
    hash *= 0x85ebca6b;
    hash ^= (hash >> 13);
    hash *= 0xc2b2ae35;
    hash ^= (hash >> 16);

    return hash;
}
#endif

void Server::SetScheduler(void) {
#ifdef HAVE_SCHED_SETSCHEDULER
    if ( isRealtime( mSettings ) ) {
	struct sched_param sp;
	sp.sched_priority = sched_get_priority_max(SCHED_RR);
	// SCHED_OTHER, SCHED_FIFO, SCHED_RR
	if (sched_setscheduler(0, SCHED_RR, &sp) < 0)  {
	    perror("Client set scheduler");
#ifdef HAVE_MLOCKALL
	} else if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0) {
	    // lock the threads memory
	    perror ("mlockall");
#endif // MLOCK
	}
    }
#endif // SCHED
}

void Server::Sig_Int( int inSigno ) {
}
/* -------------------------------------------------------------------
 * Receive TCP data from the (connected) socket.
 * Sends termination flag several times at the end.
 * Does not close the socket.
 * ------------------------------------------------------------------- */
void Server::RunTCP( void ) {
    long currLen;
    max_size_t totLen = 0;
    ReportStruct *reportstruct = NULL;
    int running;
    bool mMode_Time = isServerModeTime( mSettings );
    Timestamp time1, time2, rxtime;
    double tokens=0.000004;

    reportstruct = new ReportStruct;
    if ( reportstruct != NULL ) {
        reportstruct->packetID = 0;
        mSettings->reporthdr = InitReport( mSettings );
	running=1;
	// setup termination variables
	if ( mMode_Time ) {
	    mEndTime.setnow();
	    mEndTime.add( mSettings->mAmount / 100.0 );
	}
        do {
	    reportstruct->emptyreport=0;
	    // perform read
	    if (isBWSet(mSettings)) {
		time2.setnow();
		tokens += time2.subSec(time1) * (mSettings->mUDPRate / 8.0);
		time1 = time2;
	    }
	    if (tokens >= 0.0) {
		currLen = recv( mSettings->mSock, mBuf, mSettings->mBufLen, 0 );
		rxtime.setnow();
		reportstruct->packetTime.tv_sec = rxtime.getSecs();
		reportstruct->packetTime.tv_usec = rxtime.getUsecs();
		if (currLen <= 0) {
		    reportstruct->emptyreport=1;
		    // End loop on 0 read or socket error
		    // except for socket read timeout
		    if (currLen == 0 ||
#ifdef WIN32
			(WSAGetLastError() != WSAEWOULDBLOCK)
#else
			(errno != EAGAIN && errno != EWOULDBLOCK)
#endif // WIN32
			) {
			running = 0;
		    }
		    currLen = 0;
		}
		totLen += currLen;
		if (isBWSet(mSettings))
		    tokens -= currLen;
		reportstruct->packetLen = currLen;
		if (mMode_Time && mEndTime.before( reportstruct->packetTime)) {
		    running = 0;
		}
		ReportPacket( mSettings->reporthdr, reportstruct );
	    } else {
		// Use a 4 usec delay to fill tokens
		delay_loop(4);
	    }

        } while (running);

        // stop timing
	rxtime.setnow();
	reportstruct->packetTime.tv_sec = rxtime.getSecs();
	reportstruct->packetTime.tv_usec = rxtime.getUsecs();

	if(0.0 == mSettings->mInterval) {
	    reportstruct->packetLen = totLen;
        }
	ReportPacket( mSettings->reporthdr, reportstruct );
        CloseReport( mSettings->reporthdr, reportstruct );
    } else {
        FAIL(1, "Out of memory! Closing server thread\n", mSettings);
    }

    Mutex_Lock( &clients_mutex );
    Iperf_delete( &(mSettings->peer), &clients );
    Mutex_Unlock( &clients_mutex );

    DELETE_PTR( reportstruct );
    EndReport( mSettings->reporthdr );
}

void Server::InitTimeStamping (void) {
#ifdef HAVE_DECL_SO_TIMESTAMP
    iov[0].iov_base=mBuf;
    iov[0].iov_len=mSettings->mBufLen;

    message.msg_iov=iov;
    message.msg_iovlen=1;
    message.msg_name=&srcaddr;
    message.msg_namelen=sizeof(srcaddr);

    message.msg_control = (char *) ctrl;
    message.msg_controllen = sizeof(ctrl);

    int timestampOn = 1;
    if (setsockopt(mSettings->mSock, SOL_SOCKET, SO_TIMESTAMP, (int *) &timestampOn, sizeof(timestampOn)) < 0) {
	WARN_errno( mSettings->mSock == SO_TIMESTAMP, "socket" );
    }
#endif
}

void Server::InitTrafficLoop (void) {
    reportstruct = new ReportStruct;
    FAIL(reportstruct == NULL, "Out of memory! Closing server thread\n", mSettings);
    mSettings->reporthdr = InitReport( mSettings );
    reportstruct->packetID = 0;
    reportstruct->l2len = 0;
    if (mSettings->mBufLen < (int) sizeof( UDP_datagram ) ) {
	mSettings->mBufLen = sizeof( UDP_datagram );
	fprintf( stderr, warn_buffer_too_small, mSettings->mBufLen );
    }

    InitTimeStamping();

    int sorcvtimer = 0;
    // sorcvtimer units microseconds convert to that
    // minterval double, units seconds
    // mAmount integer, units 10 milliseconds
    // divide by two so timeout is 1/2 the interval
    if (mSettings->mInterval) {
	sorcvtimer = (int) (mSettings->mInterval * 1e6) / 2;
    } else if (isModeTime(mSettings)) {
	sorcvtimer = (mSettings->mAmount * 1000) / 2;
    }
    if (sorcvtimer > 0) {
#ifdef WIN32
	// Windows SO_RCVTIMEO uses ms
	DWORD timeout = (double) sorcvtimer / 1e3;
#else
	struct timeval timeout;
	timeout.tv_sec = sorcvtimer / 1000000;
	timeout.tv_usec = sorcvtimer % 1000000;
#endif
	if (setsockopt( mSettings->mSock, SOL_SOCKET, SO_RCVTIMEO, (char *)&timeout, sizeof(timeout)) < 0 ) {
	    WARN_errno( mSettings->mSock == SO_RCVTIMEO, "socket" );
	}
    }
}

int Server::ReadWithRxTimestamp (int *readerr) {
    reportstruct->emptyreport=0;
    long currLen;
    int tsdone = 0;

#ifdef HAVE_DECL_SO_TIMESTAMP
    cmsg = (struct cmsghdr *) &ctrl;
    currLen = recvmsg( mSettings->mSock, &message, 0 );
    if (currLen > 0) {
	if (cmsg->cmsg_level == SOL_SOCKET &&
	    cmsg->cmsg_type  == SCM_TIMESTAMP &&
	    cmsg->cmsg_len   == CMSG_LEN(sizeof(struct timeval))) {
	    memcpy(&(reportstruct->packetTime), CMSG_DATA(cmsg), sizeof(struct timeval));
	    tsdone = 1;
	}
    }
#else
    currLen = recv( mSettings->mSock, mBuf, mSettings->mBufLen, 0 );
#endif
    if (currLen <=0) {
	// Socket read timeout or read error
	reportstruct->emptyreport=1;
	// End loop on 0 read or socket error
	// except for socket read timeout
	if (currLen == 0 ||
#ifdef WIN32
	    (WSAGetLastError() != WSAEWOULDBLOCK)
#else
	    (errno != EAGAIN && errno != EWOULDBLOCK)
#endif
	    ) {
	    WARN_errno( currLen, "recvmsg");
	    *readerr = 1;
	}
	currLen= 0;
    }

    if (!tsdone) {
	Timestamp rxtime;
	reportstruct->packetTime.tv_sec = rxtime.getSecs();
	reportstruct->packetTime.tv_usec = rxtime.getUsecs();
    }
    return currLen;
}

int Server::ReadPacketID (void) {
    int terminate = 0;
    // Adjust the mbuf start pointer to reflect the L2 payload
    int offset = 0;
#ifdef HAVE_AF_PACKET
    if (isL2LengthCheck(mSettings) || isL2MACHash(mSettings) ||  isL2FrameHash(mSettings)) {
#  ifdef HAVE_IPV6
	if (isIPV6(mSettings)) {
	    offset = sizeof(struct udphdr) + IPV6HDRLEN + sizeof(struct ether_header);
	} else
#  endif
        {
	    offset = sizeof(struct udphdr) + sizeof(struct iphdr) + sizeof(struct ether_header);
	}
    }
#endif
    struct UDP_datagram* mBuf_UDP  = (struct UDP_datagram*) (mBuf + offset);

    // terminate when datagram begins with negative index
    // the datagram ID should be correct, just negated
    if (isSeqNo64b(mSettings)) {
	reportstruct->packetID = (((max_size_t) (ntohl(mBuf_UDP->id2)) << 32) | ntohl(mBuf_UDP->id));
	if (reportstruct->packetID & 0x8000000000000000LL) {
	    reportstruct->packetID = (reportstruct->packetID & 0x7FFFFFFFFFFFFFFFLL);
	    terminate = 1;
	}
    } else {
	reportstruct->packetID = ntohl(mBuf_UDP->id);
	if (reportstruct->packetID & 0x80000000L) {
	    reportstruct->packetID = (reportstruct->packetID & 0x7FFFFFFFL);
	    terminate = 1;
	}
    }

    // read the sent timestamp from the rx packet
    reportstruct->sentTime.tv_sec = ntohl( mBuf_UDP->tv_sec  );
    reportstruct->sentTime.tv_usec = ntohl( mBuf_UDP->tv_usec );

    return terminate;
}

void Server::L2_processing (void) {
#ifdef HAVE_AF_PACKET
    eth_hdr = (struct ether_header *) mBuf;
    ip_hdr = (struct iphdr *) (mBuf + sizeof(struct ether_header));
#  ifdef HAVE_IPV6
    if (isIPV6(mSettings)) {
	udp_hdr = (struct udphdr *) (mBuf + IPV6HDRLEN + sizeof(struct ether_header));
    } else  
#  endif // V6
    {
	udp_hdr = (struct udphdr *) (mBuf + sizeof(struct iphdr) + sizeof(struct ether_header));
    }
    //  uint32_t l2mac_hash = murmur3_32(sizeof(struct ether_header), 0xDEADBEEF);
    // Read the packet to get the UDP length
    reportstruct->packetLen = ntohs(udp_hdr->len);
#  ifdef HAVE_IPV6
    if (isIPV6(mSettings)) {
	reportstruct->expected_l2len = reportstruct->packetLen + IPV6HDRLEN + sizeof(struct ether_header);
    } else  
#  endif  // V6
    {
	reportstruct->expected_l2len = reportstruct->packetLen + sizeof(struct iphdr) + sizeof(struct ether_header);
    }
    // reportstruct->m3hash = murmur3_32(rxlen, l2mac_hash);
#endif // HAVE_AF_PACKET
}

void Server::Isoch_processing (void) {
#ifdef HAVE_ISOCHRONOUS
    struct UDP_isoch_payload* mBuf_isoch = (struct UDP_isoch_payload*) (mBuf + sizeof(struct UDP_datagram));
    reportstruct->frameID = ntohl(mBuf_isoch->frameid);
    reportstruct->prevframeID = ntohl(mBuf_isoch->prevframeid);
    reportstruct->burstsize = ntohl(mBuf_isoch->burstsize);
    reportstruct->remaining = ntohl(mBuf_isoch->remaining);
#endif
}

/* -------------------------------------------------------------------
 * Receive UDP data from the (connected) socket.
 * Sends termination flag several times at the end.
 * Does not close the socket.
 * ------------------------------------------------------------------- */
void Server::RunUDP( void ) {
    int done;
    bool mMode_Time = isServerModeTime( mSettings );
    int rxlen;
    int readerr = 0;

    InitTrafficLoop();

    // setup termination variables
    if ( mMode_Time ) {
	mEndTime.setnow();
	mEndTime.add( mSettings->mAmount / 100.0 );
    }
    done=0;

    // Exit loop on three conditions
    // 1) Fatal read error
    // 2) Last packet of traffic flow sent by client
    // 3) -t timer expires
    do {
	// read the next packet with timestamp
	rxlen=ReadWithRxTimestamp(&readerr);
	if (!readerr) {
	    done = ReadPacketID();
	    // Above returns true if this is the last UDP packet sent by the client
	    if (isL2LengthCheck(mSettings) || isL2MACHash(mSettings) ||  isL2FrameHash(mSettings)) {
		reportstruct->l2len = rxlen;
		// L2 processing will set the reportstruct packet length with the length found in the udp header
		L2_processing();
	    } else {
		// Set the packet length to the socket received length
		reportstruct->packetLen = rxlen;
	    }
	    if (isIsochronous(mSettings)) {
		Isoch_processing();
	    }
	} else {
	    done = 1;
	}
	if (mMode_Time && mEndTime.before( reportstruct->packetTime)) {
	    done = 1;
	}
	ReportPacket(mSettings->reporthdr, reportstruct);
    } while (!done);

    CloseReport( mSettings->reporthdr, reportstruct );

    // send a acknowledgement back only if we're NOT receiving multicast
    if (!isMulticast( mSettings ) ) {
	// send back an acknowledgement of the terminating datagram
	write_UDP_AckFIN( );
    }

    Mutex_Lock( &clients_mutex );
    Iperf_delete( &(mSettings->peer), &clients );
    Mutex_Unlock( &clients_mutex );

    DELETE_PTR( reportstruct );
    EndReport( mSettings->reporthdr );
}
// end Recv

/* -------------------------------------------------------------------
 * Send an AckFIN (a datagram acknowledging a FIN) on the socket,
 * then select on the socket for some time. If additional datagrams
 * come in, probably our AckFIN was lost and they are re-transmitted
 * termination datagrams, so re-transmit our AckFIN.
 * ------------------------------------------------------------------- */

void Server::write_UDP_AckFIN( ) {

    int rc;

    fd_set readSet;
    FD_ZERO( &readSet );

    struct timeval timeout;

    int count = 0;
    while ( count < 10 ) {
        count++;

        UDP_datagram *UDP_Hdr;
        server_hdr *hdr;

        UDP_Hdr = (UDP_datagram*) mBuf;

        if (mSettings->mBufLen > (int) (sizeof(UDP_datagram) + sizeof(server_hdr))) {
	    int flags = (!isEnhanced(mSettings) ? HEADER_VERSION1 : (HEADER_VERSION1 | HEADER_EXTEND));
            Transfer_Info *stats = GetReport( mSettings->reporthdr );
            hdr = (server_hdr*) (UDP_Hdr+1);
	    hdr->base.flags        = htonl((long) flags);
#ifdef HAVE_QUAD_SUPPORT
            hdr->base.total_len1   = htonl( (long) (stats->TotalLen >> 32) );
#else
            hdr->base.total_len1   = htonl(0x0);
#endif
            hdr->base.total_len2   = htonl( (long) (stats->TotalLen & 0xFFFFFFFF) );
            hdr->base.stop_sec     = htonl( (long) stats->endTime );
            hdr->base.stop_usec    = htonl( (long)((stats->endTime - (long)stats->endTime) * rMillion));
            hdr->base.error_cnt    = htonl( stats->cntError );
            hdr->base.outorder_cnt = htonl( stats->cntOutofOrder );
#ifndef HAVE_SEQNO64b
            hdr->base.datagrams    = htonl( stats->cntDatagrams );
#else
  #ifdef HAVE_QUAD_SUPPORT
	    hdr->base.datagrams2   = htonl( (long) (stats->cntDatagrams >> 32) );
  #else
            hdr->base.datagrams2   = htonl(0x0);
  #endif
            hdr->base.datagrams    = htonl( (long) (stats->cntDatagrams & 0xFFFFFFFF) );
#endif
            hdr->base.jitter1      = htonl( (long) stats->jitter );
            hdr->base.jitter2      = htonl( (long) ((stats->jitter - (long)stats->jitter) * rMillion) );
	    if (flags & HEADER_EXTEND) {
		hdr->extend.minTransit1  = htonl( (long) stats->transit.totminTransit );
		hdr->extend.minTransit2  = htonl( (long) ((stats->transit.totminTransit - (long)stats->transit.totminTransit) * rMillion) );
		hdr->extend.maxTransit1  = htonl( (long) stats->transit.totmaxTransit );
		hdr->extend.maxTransit2  = htonl( (long) ((stats->transit.totmaxTransit - (long)stats->transit.totmaxTransit) * rMillion) );
		hdr->extend.sumTransit1  = htonl( (long) stats->transit.totsumTransit );
		hdr->extend.sumTransit2  = htonl( (long) ((stats->transit.totsumTransit - (long)stats->transit.totsumTransit) * rMillion) );
		hdr->extend.meanTransit1  = htonl( (long) stats->transit.totmeanTransit );
		hdr->extend.meanTransit2  = htonl( (long) ((stats->transit.totmeanTransit - (long)stats->transit.totmeanTransit) * rMillion) );
		hdr->extend.m2Transit1  = htonl( (long) stats->transit.totm2Transit );
		hdr->extend.m2Transit2  = htonl( (long) ((stats->transit.totm2Transit - (long)stats->transit.totm2Transit) * rMillion) );
		hdr->extend.vdTransit1  = htonl( (long) stats->transit.totvdTransit );
		hdr->extend.vdTransit2  = htonl( (long) ((stats->transit.totvdTransit - (long)stats->transit.totvdTransit) * rMillion) );
		hdr->extend.cntTransit   = htonl( stats->transit.totcntTransit );
		hdr->extend.IPGcnt = htonl( (long) (stats->cntDatagrams / (stats->endTime - stats->startTime)));
		hdr->extend.IPGsum = htonl(1);
	    }
        }

        // write data
        write( mSettings->mSock, mBuf, mSettings->mBufLen );

        // wait until the socket is readable, or our timeout expires
        FD_SET( mSettings->mSock, &readSet );
        timeout.tv_sec  = 1;
        timeout.tv_usec = 0;

        rc = select( mSettings->mSock+1, &readSet, NULL, NULL, &timeout );
        FAIL_errno( rc == SOCKET_ERROR, "select", mSettings );

        if ( rc == 0 ) {
            // select timed out
            return;
        } else {
            // socket ready to read
            rc = read( mSettings->mSock, mBuf, mSettings->mBufLen );
            WARN_errno( rc < 0, "read" );
            if ( rc <= 0 ) {
                // Connection closed or errored
                // Stop using it.
                return;
            }
        }
    }

    fprintf( stderr, warn_ack_failed, mSettings->mSock, count );
}
// end write_UDP_AckFIN
