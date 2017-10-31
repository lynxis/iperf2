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
 * histograms.c
 * Suppport for histograms
 *
 * by Robert J. McMahon (rjmcmahon@rjmcmahon.com, bob.mcmahon@broadcom.com)
 * -------------------------------------------------------------------
 */
#include "headers.h"
#include "histogram.h"


histogram_t *histogram_init(unsigned int bincount, unsigned int binwidth, float offset, char *name) {
    histogram_t this = malloc(sizeof(histogram_t));
    this->mybins = malloc(sizeof(unsigned int) * bincount);
    this->myname = malloc(sizeof(strlen(name)));
    strcpy(this->myname, this->name);
    return this;
}

void histogram_delete(histogram_t h) {
    if (h->mybins) 
	free(h->mybins);
    if (h->myname) 
	free(h->myname);
    free(h);
}

int histogram_insert(histogram_t h, float value) {
    int bin;
    // calculate the bin
    bin = (int) (value - h->offset) / h->binwidth;
    if (bin < 0) {
	h->cntloweroutofbounds++;
	return(-1);
    } else if (bin > (int) h->bincount) {
	h->cntupperoutofbounds++;
	return(-2);
    }
    else {
	h->populationcnt++;
	h->mybins[bin]++;
	return(h->mybins[bin]);
    }
}

int histogram_clear(histogram_t h) {
    int ix;
    for (ix = 0; ix < (int) h->bincount; ix++) {
	h->mybins[ix]=0;
    }
}    

int histogram_add(histogram_t to, histogram_t from) {
    int ix;
    for (ix=0; ix < (int) to->bincount; ix ++) {
	to->mybins[ix] += from->mybins[ix];
    }
}    

void histogram_print(histogram_t h) {
    char *buf = malloc((20*bincount)+strlen(myname));
    int n = 0, ix;
    sprintf(buf, "%s(%d,%d)", h->myname, h->bincount, h->binwidth);
    n = strlen(buf);
    printf("%s\n", buf);
    for (ix = 0; ix < int (h->bincount); ix++) {
	if (h->mybins[ix] > 0) {
	    n += sprintf(buf + n,"%d:%d,", ix, h->mybins[ix]);
	}
    }
    buf[strlen(buf)-1]=0;
    fprintf(stdout, "%s\n", buf);
    free buf;
}

void histogram_print_interval(histogram_t h) {
    char *buf = malloc((20*bincount)+strlen(myname));
    int n = 0, ix;
    sprintf(buf, "%s(%d,%d)", h->myname, h->bincount, h->binwidth);
    n = strlen(buf);
    printf("%s\n", buf);
    for (ix = 0; ix < int (h->bincount); ix++) {
	if (h->mybins[ix] > 0) {
	    n += sprintf(buf + n,"%d:%d,", ix, h->mybins[ix]);
	}
    }
    buf[strlen(buf)-1]=0;
    fprintf(stdout, "%s\n", buf);
    free buf;
}


// int main(void) {
//    Histogram *h;
//    char name[] = "T1";
//    h = new Histogram(100,10,0.0, name);
//    h->insert(2);
//    h->insert(25);
//    h->print();
//}
