/*
ExoQuant v0.7

Copyright (c) 2004 Dennis Ranke

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

/*
Modified for Shrimp'It (2026):
- allocation failures are reported by exq_failed() instead of crashing;
- the histogram sort is an iterative merge sort that receives its direction as a
  parameter, so independent quantizers can run on several threads at once;
- a node whose colors are all identical no longer gets a NaN split direction;
- exq_map_image() caches the nearest palette entry of colors absent from the histogram;
- exq_map_image_random() is removed: it relied on rand(), which is neither deterministic
  nor thread-safe.
*/

/******************************************************************************
* Usage:
* ------
*
* exq_data *pExq = exq_init(); // init quantizer (per image)
* exq_feed(pExq, <ptr to image>, <num of pixels); // feed pixel data (32bpp)
* exq_quantize(pExq, <num of colors>); // find palette
* exq_get_palette(pExq, <ptr to buffer>, <num of colors>); // get palette
* exq_map_image(pExq, <num of pixels>, <ptr to input>, <ptr to output>);
* or:
* exq_map_image_ordered(pExq, <width>, <height>, <input>, <output>);
*     // map image to palette
* exq_free(pExq); // free memory again
*
* Notes:
* ------
*
* All 32bpp data (input data and palette data) is considered a byte stream
* of the format:
* R0 G0 B0 A0 R1 G1 B1 A1 ...
* If you want to use a different order, the easiest way to do this is to
* change the SCALE_x constants in expquant.h, as those are the only differences
* between the channels.
*
******************************************************************************/

#ifndef __EXOQUANT_H
#define __EXOQUANT_H

#ifdef __cplusplus
extern "C" {
#endif

/* type definitions */
typedef double exq_float;

typedef struct _exq_color
{
	exq_float r, g, b, a;
} exq_color;

typedef struct _exq_histogram
{
	exq_color				color;
	unsigned char			ored, ogreen, oblue, oalpha;
	int						palIndex;
	exq_color				ditherScale;
	int						ditherIndex[4];
	int						num;
	struct _exq_histogram	*pNext;
	struct _exq_histogram	*pNextInHash;
} exq_histogram;

typedef struct _exq_node
{
	exq_color				dir, avg;
	exq_float					vdif;
	exq_float					err;
	int						num;
	exq_histogram			*pHistogram;
	exq_histogram			*pSplit;
} exq_node;

#define EXQ_HASH_BITS			16
#define EXQ_HASH_SIZE			(1 << (EXQ_HASH_BITS))

typedef struct _exq_data
{
	exq_histogram			*pHash[EXQ_HASH_SIZE];
	exq_node				node[256];
	int						numColors;
	int						numBitsPerChannel;
	int						optimized;
	int						transparency;
	int						failed;
} exq_data;

/* interface */

exq_data			*exq_init(void);
int					exq_failed(exq_data *pExq);
void				exq_no_transparency(exq_data *pExq);
void				exq_free(exq_data *pExq);
void				exq_feed(exq_data *pExq, unsigned char *pData,
							 int nPixels);
void				exq_quantize(exq_data *pExq, int nColors);
void				exq_quantize_hq(exq_data *pExq, int nColors);
void				exq_quantize_ex(exq_data *pExq, int nColors, int hq);
exq_float			exq_get_mean_error(exq_data *pExq);
void				exq_get_palette(exq_data *pExq, unsigned char *pPal,
									int nColors);
void				exq_set_palette(exq_data *pExq, unsigned char *pPal,
									int nColors);
void				exq_map_image(exq_data *pExq, int nPixels,
								  unsigned char *pIn, unsigned char *pOut);
void				exq_map_image_ordered(exq_data *pExq, int width,
										  int height, unsigned char *pIn,
										  unsigned char *pOut);

/* internal functions */

void				exq_map_image_dither(exq_data *pExq, int width,
										 int height, unsigned char *pIn,
										 unsigned char *pOut, int ordered);

void				exq_sum_node(exq_node *pNode);
void				exq_optimize_palette(exq_data *pExp, int iter);

unsigned char		exq_find_nearest_color(exq_data *pExp, exq_color *pColor);
exq_histogram		*exq_find_histogram(exq_data *pExp, unsigned char *pCol);

typedef exq_float	(*exq_sort_func)(const exq_histogram *pHist,
								   const exq_color *pDir);

void				exq_sort(exq_histogram **ppHist, exq_sort_func sortfunc,
						 const exq_color *pDir);
exq_float			exq_sort_by_r(const exq_histogram *pHist, const exq_color *pDir);
exq_float			exq_sort_by_g(const exq_histogram *pHist, const exq_color *pDir);
exq_float			exq_sort_by_b(const exq_histogram *pHist, const exq_color *pDir);
exq_float			exq_sort_by_a(const exq_histogram *pHist, const exq_color *pDir);
exq_float			exq_sort_by_dir(const exq_histogram *pHist, const exq_color *pDir);

#ifdef __cplusplus
}
#endif

#endif // __EXOQUANT_H