#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <xcb/xcb.h>
#include <xcb/xcb_ewmh.h>
#include <xcb/damage.h>
#include <xcb/xcb_keysyms.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------ */
/* Global state                                                       */
/* ------------------------------------------------------------------ */

static xcb_connection_t    *g_dpy   = NULL;
static xcb_screen_t       *g_screen  = NULL;
static xcb_ewmh_connection_t  g_ewmh;
static int                 g_ewmh_ok  = 0;
static xcb_key_symbols_t  *g_keysyms = NULL;
static xcb_keycode_t       g_hotkey_keycodes[8];
static int                 g_hotkey_ncodes = 0;

/* Per-depth pixmap format cache, populated from xcb_setup_pixmap_formats.
 *
 * The wire layout of an xcb_get_image ZPixmap reply is defined per-depth by
 * the server (xcb_format_t: bits_per_pixel + scanline_pad), NOT by the depth
 * field alone. A depth-N image is not necessarily ceil(N/8) bytes/pixel on the
 * wire — e.g. depth-24 TrueColor is almost always 32 bits/pixel (BGRX), and
 * depth-16 is exactly 16 bits/pixel. We cache the server-reported table once
 * per connection and consult it for every capture. */
#define MAX_PIXMAP_FORMATS 32
static struct {
    uint8_t depth;
    uint8_t bits_per_pixel;
    uint8_t scanline_pad;
} g_pixmap_formats[MAX_PIXMAP_FORMATS];
static int g_n_pixmap_formats = 0;

/* ------------------------------------------------------------------ */
/* Forward declarations                                               */
/* ------------------------------------------------------------------ */

static PyObject *py_connect(PyObject *self, PyObject *args, PyObject *kw);
static PyObject *py_disconnect(PyObject *self, PyObject *args);
static PyObject *py_list_windows(PyObject *self, PyObject *args);
static PyObject *py_capture(PyObject *self, PyObject *args);
static PyObject *py_capture_pixmap(PyObject *self, PyObject *args);
static PyObject *py_capture_window_direct(PyObject *self, PyObject *args);
static PyObject *py_capture_sc(PyObject *self, PyObject *args);
static PyObject *py_invalidate_capture_cache(PyObject *self, PyObject *args);
static PyObject *py_focus_window(PyObject *self, PyObject *args);
static PyObject *py_minimize_window(PyObject *self, PyObject *args);
static PyObject *py_move_resize(PyObject *self, PyObject *args);
static PyObject *py_set_always_on_top(PyObject *self, PyObject *args);
static PyObject *py_hide_caption(PyObject *self, PyObject *args);
static PyObject *py_get_geometry(PyObject *self, PyObject *args);
static PyObject *py_get_window_level(PyObject *self, PyObject *args);
static PyObject *py_create_damage(PyObject *self, PyObject *args);
static PyObject *py_destroy_damage(PyObject *self, PyObject *args);
static PyObject *py_poll_event(PyObject *self, PyObject *args);
static PyObject *py_register_hotkey(PyObject *self, PyObject *args);
static PyObject *py_hotkey_triggered(PyObject *self, PyObject *args);
static PyObject *py_is_app_frontmost(PyObject *self, PyObject *args);
static PyObject *py_frontmost_pid(PyObject *self, PyObject *args);
static PyObject *py_get_window_title(PyObject *self, PyObject *args);
static PyObject *py_get_active_window(PyObject *self, PyObject *args);
static PyObject *py_set_process_name(PyObject *self, PyObject *args);
static PyObject *py_is_accessibility_trusted(PyObject *self, PyObject *args);

/* ------------------------------------------------------------------ */
/* Stub implementations                                               */
/* ------------------------------------------------------------------ */

static void init_ewmh(void) {
    if (g_ewmh_ok) return;
    xcb_intern_atom_cookie_t *cookies = xcb_ewmh_init_atoms(g_dpy, &g_ewmh);
    int rc = xcb_ewmh_init_atoms_replies(&g_ewmh, cookies, NULL);
    g_ewmh_ok = (rc == 1);
}

/* Walk xcb_setup_pixmap_formats and cache the (depth, bpp, scanline_pad)
 * triples reported by this server. Servers typically report only a handful
 * of formats (one per supported depth). Safe to call repeatedly — always
 * resets the cache first. */
static void init_pixmap_formats(void) {
    g_n_pixmap_formats = 0;
    if (!g_dpy) return;
    xcb_format_iterator_t it =
        xcb_setup_pixmap_formats_iterator(xcb_get_setup(g_dpy));
    for (; it.rem && g_n_pixmap_formats < MAX_PIXMAP_FORMATS;
         xcb_format_next(&it)) {
        g_pixmap_formats[g_n_pixmap_formats].depth =
            it.data->depth;
        g_pixmap_formats[g_n_pixmap_formats].bits_per_pixel =
            it.data->bits_per_pixel;
        g_pixmap_formats[g_n_pixmap_formats].scanline_pad =
            it.data->scanline_pad;
        g_n_pixmap_formats++;
    }
}

/* Helper: decode a C string to a Python unicode object.
 * Tries UTF-8 first (for _NET_WM_NAME), falls back to Latin-1
 * (for WM_NAME / WM_CLASS which use the X11 STRING atom = ISO-8859-1).
 * Never fails — every byte maps to a codepoint. */
static PyObject *str_to_pyunicode(const char *s) {
    if (!s || !s[0]) return PyUnicode_FromString("");
    size_t len = strlen(s);
    PyObject *obj = PyUnicode_Decode(s, len, "utf-8", "strict");
    if (!obj) {
        PyErr_Clear();
        obj = PyUnicode_Decode(s, len, "latin-1", NULL);
    }
    return obj;
}

/* Helper: set dict key and DECREF value. */
static void dict_put(PyObject *d, const char *key, PyObject *v) {
    if (v) {
        PyDict_SetItemString(d, key, v);
        Py_DECREF(v);
    }
}

/* Helper: get PID for a window via _NET_WM_PID. */
static pid_t wid_pid(xcb_window_t w) {
    xcb_get_property_cookie_t c = xcb_get_property_unchecked(
        g_dpy, 0, w, g_ewmh._NET_WM_PID, XCB_ATOM_CARDINAL, 0, sizeof(pid_t));
    xcb_generic_error_t *e = NULL;
    xcb_get_property_reply_t *r = xcb_get_property_reply(g_dpy, c, &e);
    if (!r || e) { free(r); free(e); return -1; }
    pid_t p = 0;
    if (r->value_len > 0) {
        memcpy(&p, xcb_get_property_value(r), sizeof(pid_t));
    }
    free(r);
    return p;
}

/* Helper: get WM_CLASS for a window. */
static void wid_wmclass(xcb_window_t w, char *buf, size_t bufsz) {
    buf[0] = '\0';
    xcb_get_property_cookie_t c = xcb_get_property_unchecked(
        g_dpy, 0, w, XCB_ATOM_WM_CLASS, XCB_ATOM_STRING, 0, 256);
    xcb_generic_error_t *e = NULL;
    xcb_get_property_reply_t *r = xcb_get_property_reply(g_dpy, c, &e);
    if (!r || e) { free(r); free(e); return; }
    unsigned char *val = (unsigned char *)xcb_get_property_value(r);
    if (val && r->value_len > 1) {
        size_t inst_len = strnlen((char *)val, bufsz);
        if (inst_len < r->value_len - 1) {
            size_t cl = r->value_len - inst_len - 1;
            if (cl > 0 && cl < bufsz) {
                memcpy(buf, val + inst_len + 1, cl);
                buf[cl] = '\0';
            } else if (bufsz > 0) {
                strncpy(buf, (char *)(val + inst_len + 1), bufsz - 1);
                buf[bufsz - 1] = '\0';
            }
        }
    }
    free(r);
}

/* Helper: strip trailing control/garbage bytes from a C string. */
static void strip_trailing_noise(char *s) {
    if (!s) return;
    size_t len = strlen(s);
    while (len > 0) {
        unsigned char c = (unsigned char)s[len - 1];
        /* Remove trailing whitespace and control characters. */
        if (c == '\t' || c == '\n' || c == '\r') {
            s[--len] = '\0';
        } else break;
    }
}

/* Helper: get UTF-8 title via _NET_WM_NAME, fallback WM_NAME. */
static char *wid_title(xcb_window_t w) {
    static char tmp[2048];
    memset(tmp, 0, sizeof(tmp));
    if (g_ewmh_ok) {
        xcb_ewmh_get_utf8_strings_reply_t rep;
        uint8_t s = xcb_ewmh_get_wm_name_reply(
            &g_ewmh,
            xcb_ewmh_get_wm_name_unchecked(&g_ewmh, w),
            &rep, NULL);
        if (s == 1 && rep.strings_len > 0 && rep.strings) {
            /* Use strings_len to bound the copy so we don't read past a
             * non-null-terminated property (happens with Wine/Proton). */
            size_t cl = rep.strings_len;
            if (cl >= sizeof(tmp)) cl = sizeof(tmp) - 1;
            memcpy(tmp, rep.strings, cl);
            tmp[cl] = '\0';
            strip_trailing_noise(tmp);
        }
        xcb_ewmh_get_utf8_strings_reply_wipe(&rep);
    }
    if (tmp[0] == '\0') {
        xcb_get_property_cookie_t c = xcb_get_property_unchecked(
            g_dpy, 0, w, XCB_ATOM_WM_NAME, XCB_ATOM_ANY, 0, 1024);
        xcb_generic_error_t *e = NULL;
        xcb_get_property_reply_t *r = xcb_get_property_reply(g_dpy, c, &e);
        if (r && !e && r->value_len > 0) {
            size_t l = r->value_len;
            if (l >= sizeof(tmp)) l = sizeof(tmp) - 1;
            memcpy(tmp, xcb_get_property_value(r), l);
            tmp[l] = '\0';
            strip_trailing_noise(tmp);
        }
        free(r);
        free(e);
    }
    return tmp;
}

static PyObject *py_connect(PyObject *self, PyObject *args, PyObject *kw) {
    (void)self;
    const char *display = NULL;
    static char *kwnames[] = {"display", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kw, "|z", kwnames, &display))
        return NULL;

    if (g_dpy) {
        g_ewmh_ok = 0;
        g_n_pixmap_formats = 0;
        xcb_ewmh_connection_wipe(&g_ewmh);
        xcb_disconnect(g_dpy);
        g_dpy = NULL;
        g_screen = NULL;
    }

    g_dpy = xcb_connect(display, NULL);
    if (xcb_connection_has_error(g_dpy)) {
        g_dpy = NULL;
        PyErr_SetString(PyExc_RuntimeError, "xcb_connect failed");
        return NULL;
    }

    xcb_screen_iterator_t si = xcb_setup_roots_iterator(xcb_get_setup(g_dpy));
    if (!si.rem) {
        xcb_disconnect(g_dpy);
        g_dpy = NULL;
        PyErr_SetString(PyExc_RuntimeError, "no screens available");
        return NULL;
    }

    g_screen = si.data;
    init_ewmh();
    init_pixmap_formats();
    g_keysyms = xcb_key_symbols_alloc(g_dpy);

    Py_RETURN_TRUE;
}

static PyObject *py_disconnect(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    if (!g_dpy) Py_RETURN_NONE;

    if (g_keysyms) {
        xcb_key_symbols_free(g_keysyms);
        g_keysyms = NULL;
    }
    g_ewmh_ok = 0;
    g_n_pixmap_formats = 0;
    xcb_ewmh_connection_wipe(&g_ewmh);
    xcb_disconnect(g_dpy);
    g_dpy = NULL;
    g_screen = NULL;
    g_hotkey_ncodes = 0;

    Py_RETURN_NONE;
}

static PyObject *py_list_windows(PyObject *self, PyObject *args) {
    (void)self;
    const char *filter = NULL;
    int only_eve = 0;
    if (!PyArg_ParseTuple(args, "|zp", &filter, &only_eve))
        return NULL;

    if (!g_dpy || !g_ewmh_ok || !g_screen) {
        return PyList_New(0);
    }

    PyObject *result = PyList_New(0);
    xcb_ewmh_get_windows_reply_t winlist;
    uint8_t s = xcb_ewmh_get_client_list_reply(
        &g_ewmh,
        xcb_ewmh_get_client_list_unchecked(&g_ewmh, 0),
        &winlist, NULL);

    if (s == 1) {
        unsigned int i;
        for (i = 0; i < winlist.windows_len; i++) {
            xcb_window_t wid = winlist.windows[i];

            char wclass_buf[256];
            memset(wclass_buf, 0, sizeof(wclass_buf));
            wid_wmclass(wid, wclass_buf, sizeof(wclass_buf));

            /* Use a local title buffer to work around the static in wid_title. */
            char *title_str = wid_title(wid);

            int match = 1;
            if (filter && filter[0]) {
                size_t flen = strlen(filter);
                int title_match = (title_str[0] != '\0' &&
                    strncasecmp(title_str, filter, flen) == 0);
                int class_match = (wclass_buf[0] != '\0' &&
                    strncasecmp(wclass_buf, filter, flen) == 0);
                /* Also do a substring match against title for partial filters. */
                if (!title_match && title_str[0] != '\0') {
                    char *p = title_str;
                    while ((p = strcasestr(p, filter)) != NULL) {
                        title_match = 1; break;
                    }
                }
                if (!class_match && wclass_buf[0] != '\0') {
                    char *p = wclass_buf;
                    while ((p = strcasestr(p, filter)) != NULL) {
                        class_match = 1; break;
                    }
                }
                match = title_match || class_match;
            }

            if (match && only_eve) {
                int is_eve = 0;
                if (title_str[0] != '\0' && strcasestr(title_str, "EVE") != NULL)
                    is_eve = 1;
                else if (wclass_buf[0] != '\0' && strcasestr(wclass_buf, "eve") != NULL)
                    is_eve = 1;
                match = is_eve;
            }

            if (match) {
                pid_t pp = wid_pid(wid);
                PyObject *d = PyDict_New();
                dict_put(d, "id",   PyLong_FromUnsignedLong((unsigned long)wid));
                dict_put(d, "title", str_to_pyunicode(title_str));
                dict_put(d, "pid", PyLong_FromLong(pp < 0 ? 0 : pp));
                dict_put(d, "wm_class", str_to_pyunicode(wclass_buf));
                PyList_Append(result, d);
                Py_DECREF(d);
            }
        }
    }

    xcb_ewmh_get_windows_reply_wipe(&winlist);
    return result;
}

/* ------------------------------------------------------------------ */
/* Capture helpers                                                    */
/* ------------------------------------------------------------------ */

/* Nearest-neighbor downscale: src (RGBA, sw*4 stride) -> dst (RGBA, dw*4). */
static void rgba_scale(const uint8_t *src, int sw, int sh,
                       uint8_t *dst, int dw, int dh) {
    int y;
    for (y = 0; y < dh; y++) {
        int sy = (int)((long)y * sh / dh);
        uint8_t *row = dst + (size_t)y * (size_t)dw * 4;
        int x;
        for (x = 0; x < dw; x++) {
            int sx = (int)((long)x * sw / dw);
            const uint8_t *p = src + (size_t)(sy * sw + sx) * 4;
            unsigned int idx = (unsigned int)x * 4;
            row[idx+0] = p[0];
            row[idx+1] = p[1];
            row[idx+2] = p[2];
            row[idx+3] = p[3];
        }
    }
}

/* Compute target dimensions preserving aspect ratio. */
static void compute_target_size(int sw, int sh, int max_w, int max_h,
                                 int *dw, int *dh) {
    *dw = sw;
    *dh = sh;
    if (max_w > 0 && max_h > 0) {
        double rx = (double)max_w / (double)sw;
        double ry = (double)max_h / (double)sh;
        double r  = (rx < ry) ? rx : ry;
        if (r > 1.0) r = 1.0;
        *dw = (int)(sw * r + 0.5);
        *dh = (int)(sh * r + 0.5);
        if (*dw <= 0) *dw = 1;
        if (*dh <= 0) *dh = 1;
    }
}

/* Look up the real bits-per-pixel for a depth from the cached server
 * pixmap-format table. */
static int bpp_for_depth(int depth) {
    int i;
    for (i = 0; i < g_n_pixmap_formats; i++) {
        if (g_pixmap_formats[i].depth == depth)
            return g_pixmap_formats[i].bits_per_pixel;
    }
    /* Defensive fallback only: the X protocol does not fix a depth→bpp
     * mapping, so this is hit only if the server failed to report a format
     * for this depth (which would normally mean we never should have received
     * image data at this depth in the first place). These are the de facto
     * values used by every mainstream X server for the common depths. */
    if (depth == 32) return 32;
    if (depth == 24) return 32;
    if (depth == 16) return 16;
    if (depth == 15) return 16;
    if (depth == 8)  return 8;
    return (depth + 7) & ~7;
}

/* Look up the scanline pad (in bits) for a depth from the cached table. */
static int scanline_pad_for_depth(int depth) {
    int i;
    for (i = 0; i < g_n_pixmap_formats; i++) {
        if (g_pixmap_formats[i].depth == depth)
            return g_pixmap_formats[i].scanline_pad;
    }
    return 32;  /* defensive fallback; 32 covers every depth we care about */
}

/* Real per-row stride (in bytes) for a ZPixmap image of the given depth and
 * width. The X server pads each scanline so its bit length is a multiple of
 * scanline_pad, so the row stride is (width*bpp) rounded up to the next
 * multiple of scanline_pad, then divided by 8. This is NOT in general equal
 * to width * bytes_per_pixel — naively assuming that produces sheared or
 * drift-corrupted captures whenever the pad does not happen to match. */
static size_t image_stride(int depth, int width) {
    int bpp = bpp_for_depth(depth);
    int pad = scanline_pad_for_depth(depth);
    if (pad <= 0) pad = 8;
    long row_bits = (long)width * (long)bpp;
    long padded = ((row_bits + pad - 1) / pad) * pad;
    return (size_t)(padded / 8);
}

/* Convert xcb_get_image_reply_t to a Python (bytes, w, h, "RGBA") tuple.
 * Takes ownership of img (frees it). */
static PyObject *image_reply_to_pytuple(xcb_get_image_reply_t *img,
                                          int sw, int sh, int dw, int dh) {
    if (!img) Py_RETURN_NONE;

    int data_len = xcb_get_image_data_length(img);
    uint8_t *raw = xcb_get_image_data(img);
    if (!raw || data_len == 0) { free(img); Py_RETURN_NONE; }

    int depth = img->depth;
    if (depth == 0) depth = 24;
    int bpp = bpp_for_depth(depth);
    size_t pixel_bytes = ((size_t)bpp + 7) / 8;
    size_t stride = image_stride(depth, sw);
    if (stride == 0) stride = pixel_bytes * (size_t)sw;  /* defensive */

    /* ZPixmap byte order is the server's image_byte_order (not the host's). */
    int lsb_first = (xcb_get_setup(g_dpy)->image_byte_order ==
                     XCB_IMAGE_ORDER_LSB_FIRST);

    /* Convert raw pixels to RGBA. calloc so any pixel we fail to fill
     * (e.g. truncated reply) reads back as transparent black, not garbage. */
    size_t rgba_sz = (size_t)sw * (size_t)sh * 4;
    uint8_t *rgba = (uint8_t *)calloc(rgba_sz, 1);
    if (!rgba) { free(img); Py_RETURN_NONE; }

    int y, x;
    for (y = 0; y < sh; y++) {
        size_t row_off = (size_t)y * stride;
        if (row_off >= (size_t)data_len) break;          /* whole row missing */
        for (x = 0; x < sw; x++) {
            size_t src_off = row_off + x * pixel_bytes;
            size_t dst_off = ((size_t)y * sw + x) * 4;

            /* Safety net: keep this bounds check even though stride now
             * accounts for pad, so a malformed/truncated reply cannot read
             * past the end of the wire data. */
            if (src_off + pixel_bytes > (size_t)data_len) goto convert_done;

            switch (bpp) {
            case 32:
                /* 32bpp ZPixmap: pixel = 0x??RRGGBB on the wire, laid out
                 * as B,G,R,X on LSB; X,R,G,B on MSB. Preserves the existing
                 * behaviour (alpha copied from the server's pad byte) which
                 * is what worked for depth-24 desktops before this fix. */
                if (lsb_first) {
                    rgba[dst_off+0] = raw[src_off+2];
                    rgba[dst_off+1] = raw[src_off+1];
                    rgba[dst_off+2] = raw[src_off+0];
                    rgba[dst_off+3] = raw[src_off+3];
                } else {
                    rgba[dst_off+0] = raw[src_off+1];
                    rgba[dst_off+1] = raw[src_off+2];
                    rgba[dst_off+2] = raw[src_off+3];
                    rgba[dst_off+3] = raw[src_off+0];
                }
                break;
            case 24:
                /* 3-byte packed BGR (LSB) / RGB (MSB); force opaque alpha. */
                if (lsb_first) {
                    rgba[dst_off+0] = raw[src_off+2];
                    rgba[dst_off+1] = raw[src_off+1];
                    rgba[dst_off+2] = raw[src_off+0];
                } else {
                    rgba[dst_off+0] = raw[src_off+0];
                    rgba[dst_off+1] = raw[src_off+1];
                    rgba[dst_off+2] = raw[src_off+2];
                }
                rgba[dst_off+3] = 0xFF;
                break;
            case 16: {
                /* 16bpp: depth 16 → RGB565, depth 15 → RGB555. A 16bpp pixel
                 * is NOT three separate R/G/B bytes — decode it explicitly
                 * rather than falling through to the 3-byte branch. */
                uint16_t pix;
                if (lsb_first)
                    pix = (uint16_t)raw[src_off+0]
                        | ((uint16_t)raw[src_off+1] << 8);
                else
                    pix = (uint16_t)raw[src_off+1]
                        | ((uint16_t)raw[src_off+0] << 8);
                unsigned r, g, b;
                if (depth >= 16) {            /* RGB565: 5/6/5 */
                    r = (pix >> 11) & 0x1F;
                    g = (pix >> 5)  & 0x3F;
                    b =  pix        & 0x1F;
                    rgba[dst_off+0] = (uint8_t)((r << 3) | (r >> 2));
                    rgba[dst_off+1] = (uint8_t)((g << 2) | (g >> 4));
                    rgba[dst_off+2] = (uint8_t)((b << 3) | (b >> 2));
                } else {                      /* RGB555: 5/5/5 */
                    r = (pix >> 10) & 0x1F;
                    g = (pix >> 5)  & 0x1F;
                    b =  pix        & 0x1F;
                    rgba[dst_off+0] = (uint8_t)((r << 3) | (r >> 2));
                    rgba[dst_off+1] = (uint8_t)((g << 3) | (g >> 2));
                    rgba[dst_off+2] = (uint8_t)((b << 3) | (b >> 2));
                }
                rgba[dst_off+3] = 0xFF;
                break;
            }
            case 8:
                /* 8bpp paletted — we don't have the server's colormap here,
                 * so map the index to grayscale as a defensive fallback. */
                rgba[dst_off+0] = raw[src_off+0];
                rgba[dst_off+1] = raw[src_off+0];
                rgba[dst_off+2] = raw[src_off+0];
                rgba[dst_off+3] = 0xFF;
                break;
            default:
                /* 1/4bpp packed-bit formats are unsupported for thumbnails;
                 * leave the dst pixel as zeroed (transparent black). */
                break;
            }
        }
    }
convert_done:

    free(img);

    /* Downscale if needed. */
    if (sw != dw || sh != dh) {
        uint8_t *scaled = (uint8_t *)malloc((size_t)dw * (size_t)dh * 4);
        if (scaled) {
            rgba_scale(rgba, sw, sh, scaled, dw, dh);
            free(rgba);
            rgba = scaled;
        } else {
            dw = sw;
            dh = sh;
        }
    }

    /* Build Python (bytes, w, h, "RGBA") tuple. */
    Py_ssize_t bsz = (Py_ssize_t)(dw * dh * 4);
    PyObject *b = PyBytes_FromStringAndSize((const char *)rgba, bsz);
    free(rgba);
    if (!b) Py_RETURN_NONE;

    PyObject *fmt = PyUnicode_FromString("RGBA");
    PyObject *t = Py_BuildValue("(NiiN)", b, dw, dh, fmt);
    return t ? t : Py_None;
}

/* Capture from the window drawable directly. Works for non-GPU windows. */
static PyObject *do_capture_window(uint32_t wid, int max_w, int max_h) {
    if (!g_dpy) Py_RETURN_NONE;

    xcb_generic_error_t *e = NULL;
    xcb_get_geometry_reply_t *gr = xcb_get_geometry_reply(g_dpy,
        xcb_get_geometry_unchecked(g_dpy, wid), &e);
    if (!gr || e) { free(gr); free(e); Py_RETURN_NONE; }

    int sw = gr->width;
    int sh = gr->height;
    free(gr);
    if (sw == 0 || sh == 0) Py_RETURN_NONE;

    int dw, dh;
    compute_target_size(sw, sh, max_w, max_h, &dw, &dh);

    xcb_get_image_reply_t *img = xcb_get_image_reply(g_dpy,
        xcb_get_image(g_dpy, XCB_IMAGE_FORMAT_Z_PIXMAP,
                      (xcb_drawable_t)wid, 0, 0,
                      (uint16_t)sw, (uint16_t)sh, 0xFFFFFFFF),
        &e);
    if (!img || e) { free(img); free(e); Py_RETURN_NONE; }

    return image_reply_to_pytuple(img, sw, sh, dw, dh);
}

/* Capture from the root window at the target window's screen coordinates.
 * This works for GPU-accelerated windows (Proton/Wine/DXVK/Vulkan) whose
 * content is rendered directly to the screen buffer and cannot be read
 * via xcb_get_image on the window drawable. */
static PyObject *do_capture_root(uint32_t wid, int max_w, int max_h) {
    if (!g_dpy || !g_screen) Py_RETURN_NONE;

    /* Step 1: get window geometry (width, height, border_width). */
    xcb_generic_error_t *e = NULL;
    xcb_get_geometry_reply_t *gr = xcb_get_geometry_reply(g_dpy,
        xcb_get_geometry_unchecked(g_dpy, wid), &e);
    if (!gr || e) { free(gr); free(e); Py_RETURN_NONE; }

    int sw = gr->width;
    int sh = gr->height;
    int bw = gr->border_width;
    free(gr);
    if (sw == 0 || sh == 0) Py_RETURN_NONE;

    /* Step 2: translate window origin to root coordinates. */
    e = NULL;
    xcb_translate_coordinates_reply_t *tr = xcb_translate_coordinates_reply(g_dpy,
        xcb_translate_coordinates(g_dpy, wid, g_screen->root, 0, 0), &e);
    if (!tr || e) { free(tr); free(e); Py_RETURN_NONE; }

    /* Content area starts inside the border. */
    int rx = tr->dst_x + bw;
    int ry = tr->dst_y + bw;
    free(tr);

    /* Step 3: clip to screen bounds. */
    int cw = sw, ch = sh;
    if (rx < 0) { cw += rx; rx = 0; }
    if (ry < 0) { ch += ry; ry = 0; }
    if (rx + cw > (int)g_screen->width_in_pixels)
        cw = (int)g_screen->width_in_pixels - rx;
    if (ry + ch > (int)g_screen->height_in_pixels)
        ch = (int)g_screen->height_in_pixels - ry;
    if (cw <= 0 || ch <= 0) Py_RETURN_NONE;

    int dw, dh;
    compute_target_size(cw, ch, max_w, max_h, &dw, &dh);

    /* Step 4: GetImage from root window at the window's coordinates. */
    e = NULL;
    xcb_get_image_reply_t *img = xcb_get_image_reply(g_dpy,
        xcb_get_image(g_dpy, XCB_IMAGE_FORMAT_Z_PIXMAP,
                      (xcb_drawable_t)g_screen->root,
                      rx, ry, (uint16_t)cw, (uint16_t)ch, 0xFFFFFFFF),
        &e);
    if (!img || e) { free(img); free(e); Py_RETURN_NONE; }

    return image_reply_to_pytuple(img, cw, ch, dw, dh);
}

/* Try window-drawable capture first, fall back to root-window capture
 * for GPU-accelerated windows where xcb_get_image on the drawable fails. */
static PyObject *do_capture(uint32_t wid, int max_w, int max_h) {
    PyObject *result = do_capture_window(wid, max_w, max_h);
    if (result && result != Py_None)
        return result;
    Py_XDECREF(result);
    return do_capture_root(wid, max_w, max_h);
}

/* Capture wrappers. All four resolve to the same XCB path. */
static PyObject *py_capture(PyObject *self, PyObject *args) {
    uint32_t wid;
    int timeout_secs = 5, mw = 0, mh = 0;
    if (!PyArg_ParseTuple(args, "I|iii", &wid, &timeout_secs, &mw, &mh))
        return NULL;
    (void)timeout_secs;
    return do_capture(wid, mw, mh);
}

static PyObject *py_capture_pixmap(PyObject *self, PyObject *args) {
    uint32_t wid;
    int mw = 0, mh = 0;
    if (!PyArg_ParseTuple(args, "I|ii", &wid, &mw, &mh))
        return NULL;
    return do_capture(wid, mw, mh);
}

static PyObject *py_capture_window_direct(PyObject *self, PyObject *args) {
    uint32_t wid;
    int mw = 0, mh = 0;
    if (!PyArg_ParseTuple(args, "I|ii", &wid, &mw, &mh))
        return NULL;
    return do_capture(wid, mw, mh);
}

static PyObject *py_capture_sc(PyObject *self, PyObject *args) {
    uint32_t wid;
    int mw = 0, mh = 0;
    if (!PyArg_ParseTuple(args, "I|ii", &wid, &mw, &mh))
        return NULL;
    return do_capture(wid, mw, mh);
}

static PyObject *py_invalidate_capture_cache(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    Py_RETURN_NONE;
}

/* ------------------------------------------------------------------ */
/* Window management                                                   */
/* ------------------------------------------------------------------ */

static PyObject *py_focus_window(PyObject *self, PyObject *args) {
    (void)self;
    uint32_t wid = 0;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    if (!g_dpy || !g_screen) Py_RETURN_FALSE;

    /* 1. Send EWMH _NET_ACTIVE_WINDOW ClientMessage to root window.
     *    This is the correct way to ask an EWMH-compliant WM (like qtile)
     *    to activate a window. xcb_ewmh_set_active_window would instead
     *    write directly to the root property, which the WM ignores/overrides. */
    if (g_ewmh_ok) {
        xcb_void_cookie_t vc = xcb_ewmh_request_change_active_window(
            &g_ewmh, 0, wid,
            XCB_EWMH_CLIENT_SOURCE_TYPE_OTHER,
            XCB_CURRENT_TIME, XCB_NONE);
        xcb_generic_error_t *e = xcb_request_check(g_dpy, vc);
        free(e);
    }

    /* 2. Raise the window above siblings. */
    uint32_t stack_values[1] = { XCB_STACK_MODE_ABOVE };
    xcb_configure_window(g_dpy, wid, XCB_CONFIG_WINDOW_STACK_MODE, stack_values);

    /* 3. Set input focus as a fallback for non-EWMH WMs. */
    xcb_set_input_focus(g_dpy, XCB_INPUT_FOCUS_POINTER_ROOT,
                        wid, XCB_CURRENT_TIME);

    /* 4. Flush to ensure the requests are sent immediately. */
    xcb_flush(g_dpy);

    Py_RETURN_TRUE;
}

static PyObject *py_minimize_window(PyObject *self, PyObject *args) {
    (void)self;
    uint32_t wid = 0;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    if (!g_dpy || !g_screen) Py_RETURN_FALSE;

    xcb_void_cookie_t vc = xcb_ewmh_request_change_wm_state(
        &g_ewmh, 0, wid,
        XCB_EWMH_WM_STATE_ADD,
        g_ewmh._NET_WM_STATE_HIDDEN,
        0,
        XCB_EWMH_CLIENT_SOURCE_TYPE_NORMAL);
    xcb_generic_error_t *e = xcb_request_check(g_dpy, vc);
    free(e);

    Py_RETURN_TRUE;
}

static PyObject *py_move_resize(PyObject *self, PyObject *args) {
    uint32_t wid;
    int xx, yy, ww, hh;
    if (!PyArg_ParseTuple(args, "Iiiii", &wid, &xx, &yy, &ww, &hh))
        return NULL;

    if (!g_dpy) Py_RETURN_FALSE;

    uint32_t values[4] = {(uint32_t)xx, (uint32_t)yy, (uint32_t)ww, (uint32_t)hh};
    xcb_void_cookie_t vc = xcb_configure_window(g_dpy, wid,
        XCB_CONFIG_WINDOW_X | XCB_CONFIG_WINDOW_Y |
        XCB_CONFIG_WINDOW_WIDTH | XCB_CONFIG_WINDOW_HEIGHT,
        values);
    xcb_generic_error_t *e = xcb_request_check(g_dpy, vc);
    if (e) { free(e); Py_RETURN_FALSE; }

    Py_RETURN_TRUE;
}

static PyObject *py_set_always_on_top(PyObject *self, PyObject *args) {
    uint32_t wid;
    int flag;
    if (!PyArg_ParseTuple(args, "Ii", &wid, &flag))
        return NULL;

    if (!g_dpy || !g_ewmh_ok) Py_RETURN_FALSE;

    xcb_ewmh_wm_state_action_t action = flag
        ? XCB_EWMH_WM_STATE_ADD
        : XCB_EWMH_WM_STATE_REMOVE;

    xcb_void_cookie_t vc = xcb_ewmh_request_change_wm_state(
        &g_ewmh, 0, wid,
        action,
        g_ewmh._NET_WM_STATE_ABOVE,
        0,
        XCB_EWMH_CLIENT_SOURCE_TYPE_NORMAL);
    xcb_generic_error_t *e = xcb_request_check(g_dpy, vc);
    free(e);

    Py_RETURN_TRUE;
}

static PyObject *py_hide_caption(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    Py_RETURN_TRUE;
}

static PyObject *py_get_geometry(PyObject *self, PyObject *args) {
    uint32_t wid = 0;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    if (!g_dpy) Py_RETURN_NONE;

    xcb_generic_error_t *e = NULL;
    xcb_get_geometry_reply_t *gr = xcb_get_geometry_reply(g_dpy,
        xcb_get_geometry_unchecked(g_dpy, wid), &e);
    if (!gr || e) { free(gr); free(e); Py_RETURN_NONE; }

    PyObject *d = PyDict_New();
    dict_put(d, "x",      PyLong_FromLong((long)gr->x));
    dict_put(d, "y",      PyLong_FromLong((long)gr->y));
    dict_put(d, "width",  PyLong_FromLong((long)gr->width));
    dict_put(d, "height", PyLong_FromLong((long)gr->height));
    dict_put(d, "depth",  PyLong_FromLong((long)gr->depth));

    free(gr);
    return d;
}

static PyObject *py_get_window_level(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    return PyLong_FromLong(-1);
}

static PyObject *py_create_damage(PyObject *self, PyObject *args) {
    uint32_t wid = 0;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    if (!g_dpy) return PyLong_FromLong(-1);

    /* Generate a damage ID. Use a simple incrementing counter. */
    static uint32_t damage_counter = 1000;
    xcb_damage_damage_t did = damage_counter++;

    xcb_void_cookie_t vc = xcb_damage_create(g_dpy, did, wid,
        XCB_DAMAGE_REPORT_LEVEL_DELTA_RECTANGLES);
    xcb_generic_error_t *e = xcb_request_check(g_dpy, vc);
    if (e) { free(e); return PyLong_FromLong(-1); }

    return PyLong_FromUnsignedLong((unsigned long)did);
}

static PyObject *py_destroy_damage(PyObject *self, PyObject *args) {
    long did = -1;
    if (!PyArg_ParseTuple(args, "l", &did))
        return NULL;

    if (g_dpy && did > 0) {
        xcb_damage_destroy(g_dpy, (xcb_damage_damage_t)did);
    }

    Py_RETURN_NONE;
}

static PyObject *py_poll_event(PyObject *self, PyObject *args) {
    (void)self; (void)args;

    if (!g_dpy) Py_RETURN_NONE;

    xcb_generic_event_t *ev = xcb_poll_for_event(g_dpy);
    if (!ev) Py_RETURN_NONE;

    int type = ev->response_type & 0x7F;
    free(ev);

    /* Return a simple event dict for the event types Python cares about. */
    PyObject *d = PyDict_New();
    dict_put(d, "type", PyLong_FromLong(type));
    return d;
}

static PyObject *py_register_hotkey(PyObject *self, PyObject *args) {
    int keysym = 0;
    int mod_mask = 0;
    if (!PyArg_ParseTuple(args, "ii", &keysym, &mod_mask))
        return NULL;

    if (!g_dpy || !g_screen || !g_keysyms) Py_RETURN_FALSE;

    /* Ungrab any previously grabbed keys. */
    if (g_hotkey_ncodes > 0) {
        for (int i = 0; i < g_hotkey_ncodes; i++) {
            xcb_ungrab_key(g_dpy, g_hotkey_keycodes[i], g_screen->root,
                           XCB_MOD_MASK_ANY);
        }
        g_hotkey_ncodes = 0;
    }

    /* Convert keysym → keycode(s) via the XCB key symbols table.
     * A keysym can map to multiple keycodes (different keyboard groups). */
    xcb_keycode_t *keycodes = xcb_key_symbols_get_keycode(g_keysyms, keysym);
    if (!keycodes) Py_RETURN_FALSE;

    int count = 0;
    for (int i = 0; keycodes[i] != 0 && count < 8; i++) {
        xcb_void_cookie_t vc = xcb_grab_key(g_dpy, 1, g_screen->root,
            (uint16_t)mod_mask, keycodes[i],
            XCB_GRAB_MODE_ASYNC, XCB_GRAB_MODE_ASYNC);
        xcb_generic_error_t *e = xcb_request_check(g_dpy, vc);
        if (e) {
            free(e);
        } else {
            g_hotkey_keycodes[count++] = keycodes[i];
        }
    }
    free(keycodes);

    g_hotkey_ncodes = count;
    if (count == 0) Py_RETURN_FALSE;
    Py_RETURN_TRUE;
}

static PyObject *py_hotkey_triggered(PyObject *self, PyObject *args) {
    (void)self; (void)args;

    if (!g_dpy || g_hotkey_ncodes == 0) Py_RETURN_FALSE;

    /* Drain all pending events, looking for KeyPress events whose keycode
     * matches one of our grabbed keycodes. Non-matching events (Damage,
     * Configure, etc.) are discarded so they don't block the queue. */
    int triggered = 0;
    for (;;) {
        xcb_generic_event_t *ev = xcb_poll_for_event(g_dpy);
        if (!ev) break;

        int type = ev->response_type & 0x7F;
        if (type == XCB_KEY_PRESS) {
            xcb_key_press_event_t *ke = (xcb_key_press_event_t *)ev;
            for (int i = 0; i < g_hotkey_ncodes; i++) {
                if (ke->detail == g_hotkey_keycodes[i]) {
                    triggered = 1;
                    break;
                }
            }
        }
        free(ev);
        if (triggered) break;
    }

    if (triggered) Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *py_is_app_frontmost(PyObject *self, PyObject *args) {
    long pid_l = 0;
    if (!PyArg_ParseTuple(args, "l", &pid_l))
        return NULL;

    if (!g_dpy || !g_ewmh_ok || !g_screen) Py_RETURN_FALSE;

    xcb_window_t w = 0;
    uint8_t s = xcb_ewmh_get_window_reply(&g_ewmh,
        xcb_ewmh_get_active_window_unchecked(&g_ewmh, 0),
        &w, NULL);
    if (s == 0 || w == 0) Py_RETURN_FALSE;

    pid_t p = wid_pid(w);
    if (p == (pid_t)pid_l) Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *py_frontmost_pid(PyObject *self, PyObject *args) {
    (void)self; (void)args;

    if (!g_dpy || !g_ewmh_ok || !g_screen) Py_RETURN_NONE;

    xcb_window_t w = 0;
    uint8_t s = xcb_ewmh_get_window_reply(&g_ewmh,
        xcb_ewmh_get_active_window_unchecked(&g_ewmh, 0),
        &w, NULL);
    if (s == 0 || w == 0) Py_RETURN_NONE;

    pid_t p = wid_pid(w);
    if (p < 0) Py_RETURN_NONE;
    return PyLong_FromLong((long)p);
}

static PyObject *py_get_window_title(PyObject *self, PyObject *args) {
    uint32_t wid = 0;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    if (!g_dpy) Py_RETURN_NONE;

    char *t = wid_title(wid);
    if (t[0] == '\0') return PyUnicode_FromString("");
    return str_to_pyunicode(t);
}

static PyObject *py_get_active_window(PyObject *self, PyObject *args) {
    (void)self; (void)args;

    if (!g_dpy || !g_ewmh_ok || !g_screen) Py_RETURN_NONE;

    xcb_window_t w = 0;
    uint8_t s = xcb_ewmh_get_window_reply(&g_ewmh,
        xcb_ewmh_get_active_window_unchecked(&g_ewmh, 0),
        &w, NULL);
    if (s == 0 || w == 0) Py_RETURN_NONE;

    return PyLong_FromUnsignedLong((unsigned long)w);
}

static PyObject *py_set_process_name(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    Py_RETURN_TRUE;
}

static PyObject *py_is_accessibility_trusted(PyObject *self, PyObject *args) {
    (void)self; (void)args;
    Py_RETURN_TRUE;
}

/* ------------------------------------------------------------------ */
/* Module definition                                                  */
/* ------------------------------------------------------------------ */

static PyMethodDef module_methods[] = {
    {"connect",                  (PyCFunction)py_connect,                  METH_VARARGS | METH_KEYWORDS, "Connect to X display"},
    {"disconnect",               py_disconnect,               METH_NOARGS, "Disconnect from X display"},
    {"list_windows",             py_list_windows,             METH_VARARGS, "List windows matching pattern"},
    {"capture",                  py_capture,                  METH_VARARGS, "Capture window screenshot"},
    {"capture_pixmap",           py_capture_pixmap,           METH_VARARGS, "Capture via pixmap"},
    {"capture_window_direct",    py_capture_window_direct,    METH_VARARGS, "Direct window capture"},
    {"capture_sc",               py_capture_sc,               METH_VARARGS, "Screenshot capture"},
    {"invalidate_capture_cache", py_invalidate_capture_cache, METH_NOARGS,  "Invalidate cache"},
    {"focus_window",             py_focus_window,             METH_VARARGS, "Focus a window"},
    {"minimize_window",          py_minimize_window,          METH_VARARGS, "Minimize a window"},
    {"move_resize",              py_move_resize,              METH_VARARGS, "Move and resize window"},
    {"set_always_on_top",        py_set_always_on_top,        METH_VARARGS, "Set always-on-top flag"},
    {"hide_caption",             py_hide_caption,             METH_VARARGS, "Hide window caption"},
    {"get_geometry",             py_get_geometry,             METH_VARARGS, "Get window geometry"},
    {"get_window_level",         py_get_window_level,         METH_VARARGS, "Get window level"},
    {"create_damage",            py_create_damage,            METH_VARARGS, "Create damage region"},
    {"destroy_damage",           py_destroy_damage,           METH_VARARGS, "Destroy damage region"},
    {"poll_event",               py_poll_event,               METH_NOARGS,  "Poll for events"},
    {"register_hotkey",          py_register_hotkey,          METH_VARARGS, "Register global hotkey"},
    {"hotkey_triggered",         py_hotkey_triggered,         METH_NOARGS,  "Check if hotkey was pressed"},
    {"is_app_frontmost",         py_is_app_frontmost,         METH_VARARGS, "Check if app is frontmost"},
    {"frontmost_pid",            py_frontmost_pid,            METH_NOARGS,  "Get frontmost process PID"},
    {"get_window_title",         py_get_window_title,         METH_VARARGS, "Get window title"},
    {"get_active_window",        py_get_active_window,        METH_NOARGS,  "Get active window ID"},
    {"set_process_name",         py_set_process_name,         METH_VARARGS, "Set process name"},
    {"is_accessibility_trusted", py_is_accessibility_trusted, METH_NOARGS,  "Check accessibility trust"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "XCB native backend for Linux",
    -1,
    module_methods
};

PyMODINIT_FUNC PyInit__native(void) {
    return PyModule_Create(&moduledef);
}
