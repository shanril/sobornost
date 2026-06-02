#define PY_SSIZE_T_CLEAN
#import <Python.h>
#import <CoreGraphics/CoreGraphics.h>
#import <ApplicationServices/ApplicationServices.h>
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <math.h>
#import <strings.h>

// Private CoreGraphics SPI for window level and ordering
extern int CGSMainConnectionID(void);
extern CGError CGSSetWindowLevel(int cid, CGWindowID wid, CGWindowLevel level);


static pid_t _get_pid_for_wid(uint32_t wid) {
    CFArrayRef windows = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid);
    if (!windows || CFArrayGetCount(windows) == 0) {
        if (windows) CFRelease(windows);
        return -1;
    }
    CFDictionaryRef info = CFArrayGetValueAtIndex(windows, 0);
    CFNumberRef pid_num = CFDictionaryGetValue(info, kCGWindowOwnerPID);
    pid_t pid = -1;
    if (pid_num) CFNumberGetValue(pid_num, kCFNumberSInt32Type, &pid);
    CFRelease(windows);
    return pid;
}

static PyObject *py_connect(PyObject *self, PyObject *args) {
    char *display = NULL;
    if (!PyArg_ParseTuple(args, "|z", &display))
        return NULL;
    Py_RETURN_TRUE;
}

static PyObject *py_disconnect(PyObject *self, PyObject *args) {
    Py_RETURN_NONE;
}

static PyObject *py_list_windows(PyObject *self, PyObject *args) {
    char *filter = NULL;
    int only_eve = 0;
    if (!PyArg_ParseTuple(args, "|zp", &filter, &only_eve))
        return NULL;

    @autoreleasepool {
        CFArrayRef windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        );
        if (!windows) {
            return PyList_New(0);
        }

        PyObject *result = PyList_New(0);
        CFIndex count = CFArrayGetCount(windows);

        for (CFIndex i = 0; i < count; i++) {
            CFDictionaryRef info = CFArrayGetValueAtIndex(windows, i);

            CFNumberRef wid_num = CFDictionaryGetValue(info, kCGWindowNumber);
            if (!wid_num) continue;

            CFStringRef owner = CFDictionaryGetValue(info, kCGWindowOwnerName);
            if (!owner) continue;

            CFStringRef title = CFDictionaryGetValue(info, kCGWindowName);

            char owner_buf[256] = {0};
            CFStringGetCString(owner, owner_buf, sizeof(owner_buf), kCFStringEncodingUTF8);

            char title_buf[1024] = {0};
            if (title && CFStringGetLength(title) > 0) {
                CFStringGetCString(title, title_buf, sizeof(title_buf), kCFStringEncodingUTF8);
            }

            // Match: filter against title OR owner name
            int match = 1;
            if (filter && filter[0]) {
                match = (title_buf[0] && strcasestr(title_buf, filter) != NULL) ||
                        (strcasestr(owner_buf, filter) != NULL);
            }
            if (match && only_eve) {
                match = (title_buf[0] && strcasestr(title_buf, "EVE") != NULL) ||
                        (strcasestr(owner_buf, "EVE") != NULL);
            }
            if (!match) continue;

            uint32_t wid = 0;
            CFNumberGetValue(wid_num, kCFNumberSInt32Type, &wid);

            CFNumberRef pid_num = CFDictionaryGetValue(info, kCGWindowOwnerPID);
            int pid = 0;
            if (pid_num) CFNumberGetValue(pid_num, kCFNumberSInt32Type, &pid);

            CGRect bounds = CGRectNull;
            CFDictionaryRef bounds_dict = CFDictionaryGetValue(info, kCGWindowBounds);
            if (bounds_dict) {
                CGRectMakeWithDictionaryRepresentation(bounds_dict, &bounds);
            }

            PyObject *d = PyDict_New();
            PyDict_SetItemString(d, "id", PyLong_FromUnsignedLong(wid));
            PyDict_SetItemString(d, "title", PyUnicode_FromString(title_buf));
            PyDict_SetItemString(d, "pid", PyLong_FromLong(pid));
            PyDict_SetItemString(d, "wm_class", PyUnicode_FromString(owner_buf));
            PyDict_SetItemString(d, "x", PyLong_FromLong((long)bounds.origin.x));
            PyDict_SetItemString(d, "y", PyLong_FromLong((long)bounds.origin.y));
            PyDict_SetItemString(d, "width", PyLong_FromLong((long)bounds.size.width));
            PyDict_SetItemString(d, "height", PyLong_FromLong((long)bounds.size.height));
            PyList_Append(result, d);
            Py_DECREF(d);
        }

        CFRelease(windows);
        return result;
    }
}

static PyObject *py_capture_inner(uint32_t wid, int timeout_secs) {
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block CGImageRef image = NULL;

    dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{
        image = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            wid,
            kCGWindowImageBoundsIgnoreFraming | kCGWindowImageShouldBeOpaque
        );
        dispatch_semaphore_signal(sem);
    });

    long wait_result = dispatch_semaphore_wait(
        sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)timeout_secs * NSEC_PER_SEC)
    );

    if (wait_result != 0) {
        // Timeout — GPU-accelerated window, background block still running; image owned by block
        return NULL;
    }

    if (!image) { return NULL; }

    size_t w = CGImageGetWidth(image);
    size_t h = CGImageGetHeight(image);
    if (w == 0 || h == 0) {
        CGImageRelease(image);
        return NULL;
    }

    size_t bpr = w * 4;
    uint8_t *raw = malloc(bpr * h);
    CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(
        raw, w, h, 8, bpr, cs,
        kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Host
    );
    CGColorSpaceRelease(cs);

    if (!ctx) {
        free(raw);
        CGImageRelease(image);
        return NULL;
    }

    CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), image);
    CGContextRelease(ctx);
    CGImageRelease(image);

    // On little-endian host (ARM64/x86_64), CGImage data is ABGR → bytes: B, G, R, A
    // Output: RGBA → bytes: R, G, B, A
    PyObject *py_bytes = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)(w * h * 4));
    uint8_t *dst = (uint8_t *)PyBytes_AS_STRING(py_bytes);
    for (size_t i = 0; i < w * h; i++) {
        dst[i*4+0] = raw[i*4+2];
        dst[i*4+1] = raw[i*4+1];
        dst[i*4+2] = raw[i*4+0];
        dst[i*4+3] = raw[i*4+3];
    }

    free(raw);
    PyObject *fmt = PyUnicode_FromString("RGBA");
    return Py_BuildValue("(NiiO)", py_bytes, (int)w, (int)h, fmt);
}

static PyObject *py_capture(PyObject *self, PyObject *args) {
    uint32_t wid;
    int timeout_secs = 5;
    if (!PyArg_ParseTuple(args, "I|i", &wid, &timeout_secs))
        return NULL;
    @autoreleasepool {
        PyObject *result = py_capture_inner(wid, timeout_secs);
        if (result) return result;
        Py_RETURN_NONE;
    }
}

// Keep old names as aliases for compatibility
static PyObject *py_capture_pixmap(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;
    @autoreleasepool {
        PyObject *result = py_capture_inner(wid, 5);
        if (result) return result;
        Py_RETURN_NONE;
    }
}

static PyObject *py_capture_window_direct(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;
    @autoreleasepool {
        PyObject *result = py_capture_inner(wid, 5);
        if (result) return result;
        Py_RETURN_NONE;
    }
}

// Helper: capture a window using SCContentFilter (display+window filter)
// This is the per-window Metal-capable capture path.
static CGImageRef capture_sc_with_filter(uint32_t wid, SCShareableContent *content) {
    SCWindow *targetWindow = nil;
    for (SCWindow *win in content.windows) {
        if (win.windowID == wid) {
            targetWindow = win;
            break;
        }
    }
    if (!targetWindow) return NULL;

    SCDisplay *targetDisplay = nil;
    CGRect wf = targetWindow.frame;
    for (SCDisplay *dpy in content.displays) {
        if (CGRectIntersectsRect(wf, dpy.frame)) {
            targetDisplay = dpy;
            break;
        }
    }
    if (!targetDisplay) return NULL;

    SCContentFilter *filter = [[SCContentFilter alloc] initWithDisplay:targetDisplay
                                                       includingWindows:@[targetWindow]];
    if (!filter) return NULL;

    SCStreamConfiguration *config = [[SCStreamConfiguration alloc] init];
    config.width = (NSInteger)targetWindow.frame.size.width;
    config.height = (NSInteger)targetWindow.frame.size.height;

    __block CGImageRef capturedImage = NULL;
    __block BOOL captureDone = NO;

    [SCScreenshotManager captureImageWithFilter:filter
                                  configuration:config
                              completionHandler:^(CGImageRef _Nullable image, NSError * _Nullable err) {
        if (image) {
            capturedImage = CGImageRetain(image);
        }
        captureDone = YES;
    }];

    NSDate *capTimeout = [NSDate dateWithTimeIntervalSinceNow:10.0];
    while (!captureDone && [capTimeout timeIntervalSinceNow] > 0) {
        [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                                 beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    }
    return capturedImage;
}

static PyObject *py_capture_sc(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    @autoreleasepool {
        if (@available(macOS 14.0, *)) {
            // Try per-window capture via SCContentFilter first
            __block SCShareableContent *shareableContent = nil;
            __block BOOL contentDone = NO;

            [SCShareableContent getShareableContentExcludingDesktopWindows:NO
                                                       onScreenWindowsOnly:YES
                                                         completionHandler:^(SCShareableContent * _Nullable content, NSError * _Nullable error) {
                if (error) {
                    fprintf(stderr, "[sobornost C] SCShareableContent error: %s\n",
                            [[error localizedDescription] UTF8String]);
                }
                shareableContent = content;
                if (content) {
                    CFRetain((__bridge CFTypeRef)content);
                }
                contentDone = YES;
            }];

            NSDate *contentTimeout = [NSDate dateWithTimeIntervalSinceNow:10.0];
            while (!contentDone && [contentTimeout timeIntervalSinceNow] > 0) {
                [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                                         beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            }
            if (!shareableContent) {
                fprintf(stderr, "[sobornost C] shareableContent is nil (SC not available)\n");
                // Fall through to fallback
            } else {
                CGImageRef scImage = capture_sc_with_filter(wid, shareableContent);
                CFRelease((__bridge CFTypeRef)shareableContent);
                if (scImage) {
                    size_t w = CGImageGetWidth(scImage);
                    size_t h = CGImageGetHeight(scImage);
                    if (w > 0 && h > 0) {
                        size_t bpr = w * 4;
                        uint8_t *raw = malloc(bpr * h);
                        CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
                        CGContextRef ctx = CGBitmapContextCreate(
                            raw, w, h, 8, bpr, cs,
                            kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Host
                        );
                        CGColorSpaceRelease(cs);
                        if (ctx) {
                            CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), scImage);
                            CGContextRelease(ctx);
                        }
                        CGImageRelease(scImage);
                        if (raw) {
                            PyObject *py_bytes = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)(w * h * 4));
                            uint8_t *dst = (uint8_t *)PyBytes_AS_STRING(py_bytes);
                            for (size_t i = 0; i < w * h; i++) {
                                dst[i*4+0] = raw[i*4+2];
                                dst[i*4+1] = raw[i*4+1];
                                dst[i*4+2] = raw[i*4+0];
                                dst[i*4+3] = raw[i*4+3];
                            }
                            free(raw);
                            PyObject *fmt = PyUnicode_FromString("RGBA");
                            return Py_BuildValue("(NiiO)", py_bytes, (int)w, (int)h, fmt);
                        }
                        free(raw);
                    } else {
                        CGImageRelease(scImage);
                    }
                }
                // Filter-based capture failed; fall through to captureImageInRect:
            }

            // Fallback: captureImageInRect: (works on macOS 15.2+, but captures
            // screen region, not per-window content — so overlapping full-screen
            // windows will show the same content).
            // Get the window frame from CGWindowList
            CGRect windowFrame = CGRectNull;
            CFArrayRef cgWindows = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid);
            if (cgWindows && CFArrayGetCount(cgWindows) > 0) {
                CFDictionaryRef info = CFArrayGetValueAtIndex(cgWindows, 0);
                CFDictionaryRef bounds = CFDictionaryGetValue(info, kCGWindowBounds);
                if (bounds) {
                    CGRectMakeWithDictionaryRepresentation(bounds, &windowFrame);
                }
                CFRelease(cgWindows);
            }
            if (CGRectIsNull(windowFrame)) {
                Py_RETURN_NONE;
            }

            __block CGImageRef capturedImage = NULL;
            __block BOOL captureDone = NO;

            [SCScreenshotManager captureImageInRect:windowFrame
                                  completionHandler:^(CGImageRef _Nullable image, NSError * _Nullable error) {
                if (image) {
                    capturedImage = CGImageRetain(image);
                }
                if (error) {
                    fprintf(stderr, "[sobornost C] captureImageInRect error: %s\n",
                            [[error localizedDescription] UTF8String]);
                }
                captureDone = YES;
            }];

            NSDate *capTimeout = [NSDate dateWithTimeIntervalSinceNow:10.0];
            while (!captureDone && [capTimeout timeIntervalSinceNow] > 0) {
                [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                                         beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            }
            if (!capturedImage) {
                Py_RETURN_NONE;
            }

            size_t w = CGImageGetWidth(capturedImage);
            size_t h = CGImageGetHeight(capturedImage);
            if (w == 0 || h == 0) {
                CGImageRelease(capturedImage);
                Py_RETURN_NONE;
            }

            size_t bpr = w * 4;
            uint8_t *raw = malloc(bpr * h);
            CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
            CGContextRef ctx = CGBitmapContextCreate(
                raw, w, h, 8, bpr, cs,
                kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Host
            );
            CGColorSpaceRelease(cs);

            if (!ctx) {
                free(raw);
                CGImageRelease(capturedImage);
                Py_RETURN_NONE;
            }

            CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), capturedImage);
            CGContextRelease(ctx);
            CGImageRelease(capturedImage);

            PyObject *py_bytes = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)(w * h * 4));
            uint8_t *dst = (uint8_t *)PyBytes_AS_STRING(py_bytes);
            for (size_t i = 0; i < w * h; i++) {
                dst[i*4+0] = raw[i*4+2];
                dst[i*4+1] = raw[i*4+1];
                dst[i*4+2] = raw[i*4+0];
                dst[i*4+3] = raw[i*4+3];
            }

            free(raw);
            PyObject *fmt = PyUnicode_FromString("RGBA");
            return Py_BuildValue("(NiiO)", py_bytes, (int)w, (int)h, fmt);
        }

        Py_RETURN_NONE;
    }
}
// Find the AX window matching the given CGWindowID by comparing
// position and size with the CGWindow frame.
static AXUIElementRef _find_ax_window(pid_t pid, uint32_t wid) {
    // Get the window's frame from CGWindowList
    CGRect target = CGRectNull;
    CFArrayRef cgWindows = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid);
    if (cgWindows && CFArrayGetCount(cgWindows) > 0) {
        CFDictionaryRef info = CFArrayGetValueAtIndex(cgWindows, 0);
        CFDictionaryRef bounds = CFDictionaryGetValue(info, kCGWindowBounds);
        if (bounds) CGRectMakeWithDictionaryRepresentation(bounds, &target);
        CFRelease(cgWindows);
    }
    if (CGRectIsNull(target)) return NULL;

    AXUIElementRef app_ax = AXUIElementCreateApplication(pid);
    if (!app_ax) return NULL;

    CFArrayRef ax_windows = NULL;
    AXError err = AXUIElementCopyAttributeValue(app_ax, kAXWindowsAttribute, (CFTypeRef *)&ax_windows);
    if (err != kAXErrorSuccess || !ax_windows) {
        CFRelease(app_ax);
        return NULL;
    }

    AXUIElementRef found = NULL;
    CFIndex n = CFArrayGetCount(ax_windows);
    for (CFIndex i = 0; i < n; i++) {
        AXUIElementRef win = CFArrayGetValueAtIndex(ax_windows, i);
        if (!win) continue;

        CFTypeRef pos_val = NULL, sz_val = NULL;
        AXUIElementCopyAttributeValue(win, kAXPositionAttribute, &pos_val);
        AXUIElementCopyAttributeValue(win, kAXSizeAttribute, &sz_val);

        if (pos_val && sz_val) {
            CGPoint pt; CGSize sz;
            AXValueGetValue((AXValueRef)pos_val, kAXValueCGPointType, &pt);
            AXValueGetValue((AXValueRef)sz_val, kAXValueCGSizeType, &sz);
            if (fabs(pt.x - target.origin.x) < 1 &&
                fabs(pt.y - target.origin.y) < 1 &&
                fabs(sz.width - target.size.width) < 1 &&
                fabs(sz.height - target.size.height) < 1) {
                found = win;
                CFRetain(found);
            }
        }
        if (pos_val) CFRelease(pos_val);
        if (sz_val) CFRelease(sz_val);
        if (found) break;
    }

    CFRelease(ax_windows);
    CFRelease(app_ax);
    return found;
}

static PyObject *py_is_app_frontmost(PyObject *self, PyObject *args) {
    uint32_t pid;
    if (!PyArg_ParseTuple(args, "I", &pid))
        return NULL;
    @autoreleasepool {
        if ([[NSWorkspace sharedWorkspace] frontmostApplication].processIdentifier == (pid_t)pid)
            Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject *py_focus_window(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    @autoreleasepool {
        pid_t pid = _get_pid_for_wid(wid);
        if (pid < 0) {
            Py_RETURN_FALSE;
        }

        // Use AX API to bring the target window forward.
        // kAXRaiseAction brings the AX window to front (z-order).
        // kAXFrontmostAttribute makes the app frontmost.
        // Both return 0 (kAXErrorSuccess) on macOS 26 without Accessibility.
        AXUIElementRef app_ax = AXUIElementCreateApplication(pid);
        if (app_ax) {
            AXUIElementRef ax_win = _find_ax_window(pid, wid);
            if (ax_win) {
                AXUIElementPerformAction(ax_win, kAXRaiseAction);
                AXUIElementSetAttributeValue(ax_win, kAXFocusedAttribute, kCFBooleanTrue);
                AXUIElementSetAttributeValue(ax_win, kAXMainAttribute, kCFBooleanTrue);
                CFRelease(ax_win);
            }
            AXUIElementSetAttributeValue(app_ax, kAXFrontmostAttribute, kCFBooleanTrue);
            CFRelease(app_ax);
        }

        Py_RETURN_TRUE;
    }
}

static PyObject *py_minimize_window(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    @autoreleasepool {
        pid_t pid = _get_pid_for_wid(wid);
        if (pid < 0) Py_RETURN_FALSE;

        AXUIElementRef ax_win = _find_ax_window(pid, wid);
        if (!ax_win) Py_RETURN_FALSE;

        AXError err = AXUIElementSetAttributeValue(ax_win, kAXMinimizedAttribute, kCFBooleanTrue);
        CFRelease(ax_win);
        if (err == kAXErrorSuccess) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }
}

static PyObject *py_move_resize(PyObject *self, PyObject *args) {
    uint32_t wid;
    int x, y, w, h;
    if (!PyArg_ParseTuple(args, "Iiiii", &wid, &x, &y, &w, &h))
        return NULL;

    @autoreleasepool {
        pid_t pid = _get_pid_for_wid(wid);
        if (pid < 0) Py_RETURN_FALSE;

        AXUIElementRef ax_win = _find_ax_window(pid, wid);
        if (!ax_win) Py_RETURN_FALSE;

        CGPoint pt = { (CGFloat)x, (CGFloat)y };
        AXValueRef position = AXValueCreate(kAXValueCGPointType, (const void *)&pt);
        if (position) {
            AXUIElementSetAttributeValue(ax_win, kAXPositionAttribute, position);
            CFRelease(position);
        }

        CGSize sz = { (CGFloat)w, (CGFloat)h };
        AXValueRef size = AXValueCreate(kAXValueCGSizeType, (const void *)&sz);
        if (size) {
            AXUIElementSetAttributeValue(ax_win, kAXSizeAttribute, size);
            CFRelease(size);
        }

        CFRelease(ax_win);
        Py_RETURN_TRUE;
    }
}

static PyObject *py_set_always_on_top(PyObject *self, PyObject *args) {
    const char *title;
    int flag;
    if (!PyArg_ParseTuple(args, "sp", &title, &flag))
        return NULL;

    @autoreleasepool {
        CGWindowLevel level = flag
            ? CGWindowLevelForKey(kCGMaximumWindowLevelKey)
            : NSNormalWindowLevel;
        int found = 0;
        int cid = CGSMainConnectionID();
        NSString *titlePrefix = [NSString stringWithUTF8String: title ?: ""];

        // Strategy: try title match first, then fall back to borderless
        // style-mask match.  Both use [NSApp windows].
        for (NSWindow *win in [NSApp windows]) {
            BOOL match = NO;
            if ([win.title hasPrefix: titlePrefix]) {
                match = YES;                // exact title match
            } else if (win.styleMask == NSWindowStyleMaskBorderless &&
                       win.windowNumber > 0) {
                // Borderless window that isn't the title match — likely a
                // Tk thumbnail created before the title was set.
                // Accept it as a last resort.
                match = YES;
            }
            if (!match) continue;

            found++;
            CGWindowID cgWid = (CGWindowID)win.windowNumber;
            if (flag) {
                // Set level via both Cocoa API (public) and CGS SPI (private,
                // at window server level).  The Cocoa level may be overridden
                // by Tk or macOS, so the CGS call provides a backup.
                win.level = level;
                win.collectionBehavior =
                    NSWindowCollectionBehaviorCanJoinAllSpaces |
                    NSWindowCollectionBehaviorFullScreenAuxiliary |
                    NSWindowCollectionBehaviorStationary |
                    NSWindowCollectionBehaviorIgnoresCycle;
                win.canHide = NO;
                [win orderFrontRegardless];
                if (cgWid > 0) {
                    CGError err = CGSSetWindowLevel(cid, cgWid, level);
                    if (err != kCGErrorSuccess) {
                        fprintf(stderr, "[sobornost C] CGSSetWindowLevel failed: %d\n", err);
                    }
                }
            } else {
                win.level = level;
                win.collectionBehavior = NSWindowCollectionBehaviorDefault;
                if (cgWid > 0) {
                    CGError err = CGSSetWindowLevel(cid, cgWid, level);
                    if (err != kCGErrorSuccess)
                        fprintf(stderr, "[sobornost C] CGSSetWindowLevel failed: %d\n", err);
                }
            }
        }

        // Extra fallback: use CGWindowListCopyWindowInfo with
        // kCGWindowListOptionAll (not just on-screen) by PID + title.
        if (found == 0) {
            pid_t our_pid = getpid();
            CFArrayRef windows = CGWindowListCopyWindowInfo(
                kCGWindowListOptionAll,
                kCGNullWindowID
            );
            if (windows) {
                CFIndex count = CFArrayGetCount(windows);
                for (CFIndex i = 0; i < count && !found; i++) {
                    CFDictionaryRef info = CFArrayGetValueAtIndex(windows, i);
                    CFNumberRef pid_num = CFDictionaryGetValue(info, kCGWindowOwnerPID);
                    if (!pid_num) continue;
                    pid_t pid = 0;
                    CFNumberGetValue(pid_num, kCFNumberSInt32Type, &pid);
                    if (pid != our_pid) continue;
                    NSString *name = (__bridge NSString *)
                        CFDictionaryGetValue(info, kCGWindowName);
                    if ([name hasPrefix: titlePrefix]) {
                        CFNumberRef wid_num = CFDictionaryGetValue(info, kCGWindowNumber);
                        if (wid_num) {
                            uint32_t cgWid = 0;
                            CFNumberGetValue(wid_num, kCFNumberSInt32Type, &cgWid);
                            CGError err = CGSSetWindowLevel(cid, cgWid, level);
                            if (err != kCGErrorSuccess)
                                fprintf(stderr, "[sobornost C] CGSSetWindowLevel (fallback) failed: %d\n", err);
                            found++;
                        }
                    }
                }
                CFRelease(windows);
            }
        }

        if (found == 0) {
            // Debug: dump NSApp.windows to stderr so we can see what's available
            fprintf(stderr, "[sobornost C] NSApp.windows count: %lu\n",
                    (unsigned long)[NSApp windows].count);
            for (NSWindow *win in [NSApp windows]) {
                fprintf(stderr, "[sobornost C]   NSApp win: wNum=%ld style=0x%lx title=\"%s\"\n",
                        (long)win.windowNumber,
                        (unsigned long)win.styleMask,
                        [win.title UTF8String] ?: "(nil)");
            }
            // Also dump our windows from CGWindowList
            pid_t our_pid = getpid();
            CFArrayRef cgWins = CGWindowListCopyWindowInfo(
                kCGWindowListOptionAll, kCGNullWindowID);
            if (cgWins) {
                CFIndex cnt = CFArrayGetCount(cgWins);
                fprintf(stderr, "[sobornost C] CGWindowList (all) count: %ld\n", (long)cnt);
                for (CFIndex i = 0; i < cnt; i++) {
                    CFDictionaryRef info = CFArrayGetValueAtIndex(cgWins, i);
                    CFNumberRef pid_num = CFDictionaryGetValue(info, kCGWindowOwnerPID);
                    if (!pid_num) continue;
                    pid_t pid = 0;
                    CFNumberGetValue(pid_num, kCFNumberSInt32Type, &pid);
                    if (pid != our_pid) continue;
                    uint32_t cgw = 0;
                    CFNumberRef wnum = CFDictionaryGetValue(info, kCGWindowNumber);
                    if (wnum) CFNumberGetValue(wnum, kCFNumberSInt32Type, &cgw);
                    NSString *nm = (__bridge NSString *)CFDictionaryGetValue(info, kCGWindowName);
                    fprintf(stderr, "[sobornost C]   CG win: wNum=%u title=\"%s\"\n",
                            cgw, [nm UTF8String] ?: "(nil)");
                }
                CFRelease(cgWins);
            }
            Py_RETURN_FALSE;
        }
        if (flag) {
            return PyLong_FromLong((long)level);
        }
        Py_RETURN_TRUE;
    }
}

static PyObject *py_hide_caption(PyObject *self, PyObject *args) {
    // Tk's overrideredirect(True) already removes window decorations on macOS.
    Py_RETURN_TRUE;
}

static PyObject *py_get_geometry(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    @autoreleasepool {
        CFArrayRef windows = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid);
        if (!windows || CFArrayGetCount(windows) == 0) {
            if (windows) CFRelease(windows);
            Py_RETURN_NONE;
        }

        CFDictionaryRef info = CFArrayGetValueAtIndex(windows, 0);
        CGRect bounds = CGRectNull;
        CFDictionaryRef bounds_dict = CFDictionaryGetValue(info, kCGWindowBounds);
        if (!bounds_dict || !CGRectMakeWithDictionaryRepresentation(bounds_dict, &bounds)) {
            CFRelease(windows);
            Py_RETURN_NONE;
        }

        PyObject *d = PyDict_New();
        PyDict_SetItemString(d, "x", PyLong_FromLong((long)bounds.origin.x));
        PyDict_SetItemString(d, "y", PyLong_FromLong((long)bounds.origin.y));
        PyDict_SetItemString(d, "width", PyLong_FromLong((long)bounds.size.width));
        PyDict_SetItemString(d, "height", PyLong_FromLong((long)bounds.size.height));
        PyDict_SetItemString(d, "depth", PyLong_FromLong(32));
        CFRelease(windows);
        return d;
    }
}

static PyObject *py_create_damage(PyObject *self, PyObject *args) {
    return PyLong_FromLong(-1);
}

static PyObject *py_destroy_damage(PyObject *self, PyObject *args) {
    Py_RETURN_NONE;
}

static PyObject *py_poll_event(PyObject *self, PyObject *args) {
    Py_RETURN_NONE;
}

// Global hotkey via Carbon RegisterEventHotKey (works without Accessibility).
#import <Carbon/Carbon.h>

static EventHotKeyRef s_hotkey_ref = NULL;
static bool s_hotkey_triggered = false;

static OSStatus _hotkey_handler(EventHandlerCallRef nextHandler, EventRef event, void *userData) {
    s_hotkey_triggered = true;
    return noErr;
}

static PyObject *py_hotkey_triggered(PyObject *self, PyObject *args) {
    if (s_hotkey_triggered) {
        s_hotkey_triggered = false;
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject *py_register_hotkey(PyObject *self, PyObject *args) {
    int keycode, flags;
    if (!PyArg_ParseTuple(args, "ii", &keycode, &flags))
        return NULL;

    // Unregister previous
    if (s_hotkey_ref) {
        UnregisterEventHotKey(s_hotkey_ref);
        s_hotkey_ref = NULL;
    }

    // Convert NSEventModifierFlags → Carbon modifiers
    // NSEventModifierFlagControl = 1<<18, NSEventModifierFlagShift = 1<<17,
    // NSEventModifierFlagOption = 1<<19, NSEventModifierFlagCommand = 1<<20
    UInt32 carbonMods = 0;
    if (flags & (1 << 18)) carbonMods |= controlKey;   // 0x1000
    if (flags & (1 << 17)) carbonMods |= shiftKey;     // 0x0200
    if (flags & (1 << 19)) carbonMods |= optionKey;    // 0x0800
    if (flags & (1 << 20)) carbonMods |= cmdKey;        // 0x0100

    EventHotKeyID hotkeyID;
    hotkeyID.signature = 'sobo';
    hotkeyID.id = 1;
    EventTypeSpec eventSpec = {kEventClassKeyboard, kEventHotKeyPressed};

    InstallEventHandler(GetApplicationEventTarget(),
                        _hotkey_handler,
                        1, &eventSpec, NULL, NULL);

    OSStatus err = RegisterEventHotKey((UInt32)keycode, carbonMods,
                                        hotkeyID,
                                        GetApplicationEventTarget(),
                                        0, &s_hotkey_ref);
    if (err != noErr) {
        fprintf(stderr, "[sobornost C] RegisterEventHotKey failed: %d\n", (int)err);
        Py_RETURN_FALSE;
    }
    fprintf(stderr, "[sobornost C] Hotkey registered (Carbon): keyCode=%d flags=%d\n",
            keycode, flags);
    Py_RETURN_TRUE;
}

static PyObject *py_get_window_title(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;

    @autoreleasepool {
        CFArrayRef windows = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid);
        if (!windows || CFArrayGetCount(windows) == 0) {
            if (windows) CFRelease(windows);
            Py_RETURN_NONE;
        }

        CFDictionaryRef info = CFArrayGetValueAtIndex(windows, 0);
        CFStringRef title = CFDictionaryGetValue(info, kCGWindowName);
        if (!title) {
            CFRelease(windows);
            Py_RETURN_NONE;
        }

        char buf[1024] = {0};
        CFStringGetCString(title, buf, sizeof(buf), kCFStringEncodingUTF8);
        CFRelease(windows);
        return PyUnicode_FromString(buf);
    }
}

static PyObject *py_get_window_level(PyObject *self, PyObject *args) {
    uint32_t wid;
    if (!PyArg_ParseTuple(args, "I", &wid))
        return NULL;
    @autoreleasepool {
        CFArrayRef windows = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid);
        if (!windows || CFArrayGetCount(windows) == 0) {
            if (windows) CFRelease(windows);
            Py_RETURN_NONE;
        }
        CFDictionaryRef info = CFArrayGetValueAtIndex(windows, 0);
        CFNumberRef layerNum = CFDictionaryGetValue(info, kCGWindowLayer);
        if (!layerNum) {
            CFRelease(windows);
            Py_RETURN_NONE;
        }
        int32_t layer = 0;
        CFNumberGetValue(layerNum, kCFNumberSInt32Type, &layer);
        CFRelease(windows);
        return PyLong_FromLong(layer);
    }
}

static PyObject *py_get_active_window(PyObject *self, PyObject *args) {
    @autoreleasepool {
        NSRunningApplication *frontApp = [[NSWorkspace sharedWorkspace] frontmostApplication];
        if (!frontApp) Py_RETURN_NONE;
        pid_t frontPid = [frontApp processIdentifier];

        CFArrayRef windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        );
        if (!windows) Py_RETURN_NONE;

        PyObject *result = Py_None;
        CFIndex count = CFArrayGetCount(windows);
        for (CFIndex i = 0; i < count; i++) {
            CFDictionaryRef info = CFArrayGetValueAtIndex(windows, i);
            CFNumberRef pidNum = CFDictionaryGetValue(info, kCGWindowOwnerPID);
            if (!pidNum) continue;
            pid_t pid = 0;
            CFNumberGetValue(pidNum, kCFNumberSInt32Type, &pid);
            if (pid != frontPid) continue;

            CFNumberRef widNum = CFDictionaryGetValue(info, kCGWindowNumber);
            if (!widNum) continue;
            uint32_t wid = 0;
            CFNumberGetValue(widNum, kCFNumberSInt32Type, &wid);
            result = PyLong_FromUnsignedLong(wid);
            break;
        }

        CFRelease(windows);
        if (result == Py_None) Py_RETURN_NONE;
        return result;
    }
}

static PyObject *py_is_accessibility_trusted(PyObject *self, PyObject *args) {
    NSDictionary *opts = @{(id)kAXTrustedCheckOptionPrompt: @YES};
    return AXIsProcessTrustedWithOptions((CFDictionaryRef)opts) ? Py_True : Py_False;
}

static PyObject *py_set_process_name(PyObject *self, PyObject *args) {
    const char *name;
    if (!PyArg_ParseTuple(args, "s", &name)) return NULL;

    NSString *nsName = [NSString stringWithUTF8String:name];
    if (!nsName) { Py_RETURN_FALSE; }

    @try {
        [[NSProcessInfo processInfo] setValue:nsName forKey:@"processName"];
        Py_RETURN_TRUE;
    } @catch (NSException *e) {
        fprintf(stderr, "[sobornost C] set_process_name failed: %s\n",
                [[e description] UTF8String]);
        Py_RETURN_FALSE;
    }
}

static PyMethodDef module_methods[] = {
    {"connect",            py_connect,            METH_VARARGS, "Connect to X display (no-op on macOS)"},
    {"disconnect",         py_disconnect,         METH_VARARGS, "Disconnect from X display (no-op on macOS)"},
    {"list_windows",       py_list_windows,       METH_VARARGS, "List windows matching pattern via CGWindowListCopyWindowInfo"},
    {"capture",            py_capture,                  METH_VARARGS, "Capture window via CGWindowListCreateImage with timeout"},
    {"capture_pixmap",     py_capture_pixmap,          METH_VARARGS, "Capture window via CGWindowListCreateImage (5s timeout)"},
    {"capture_window_direct", py_capture_window_direct, METH_VARARGS, "Same as capture_pixmap on macOS (no fallback needed)"},
    {"capture_sc",         py_capture_sc,              METH_VARARGS, "Capture window via ScreenCaptureKit (handles Metal windows)"},
    {"focus_window",       py_focus_window,       METH_VARARGS, "Focus and raise window via NSRunningApplication + AX"},
    {"minimize_window",    py_minimize_window,    METH_VARARGS, "Minimize window via AX"},
    {"move_resize",        py_move_resize,        METH_VARARGS, "Move and resize window via AX"},
    {"set_always_on_top",  py_set_always_on_top,  METH_VARARGS, "Set window always-on-top flag"},
    {"hide_caption",       py_hide_caption,       METH_VARARGS, "No-op on macOS (Tkinter handles this)"},
    {"get_geometry",       py_get_geometry,       METH_VARARGS, "Get window geometry from CGWindowListCopyWindowInfo"},
    {"get_window_level",   py_get_window_level,   METH_VARARGS, "Get NSWindow level for diagnostic"},
    {"create_damage",      py_create_damage,      METH_VARARGS, "Always returns -1 (no damage tracking on macOS)"},
    {"destroy_damage",     py_destroy_damage,     METH_VARARGS, "No-op on macOS"},
    {"poll_event",         py_poll_event,         METH_VARARGS, "No-op on macOS (returns None)"},
    {"register_hotkey",    py_register_hotkey,    METH_VARARGS, "Register global hotkey via NSEvent global monitor"},
    {"hotkey_triggered",   py_hotkey_triggered,   METH_VARARGS, "Check and clear hotkey trigger flag"},
    {"is_app_frontmost",   py_is_app_frontmost,   METH_VARARGS, "Check if process with given PID is frontmost app"},
    {"get_window_title",   py_get_window_title,   METH_VARARGS, "Get window title from CGWindowListCopyWindowInfo"},
    {"get_active_window",  py_get_active_window,  METH_VARARGS, "Return CGWindowID of the frontmost window"},
    {"set_process_name",            py_set_process_name,            METH_VARARGS, "Set NSProcessInfo processName via KVC"},
    {"is_accessibility_trusted",     py_is_accessibility_trusted,    METH_VARARGS, "Check AXIsProcessTrustedWithOptions (prompts if not trusted)"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "macOS window management via CoreGraphics + Accessibility APIs (x11utils-compatible API)",
    -1,
    module_methods,
    NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC PyInit__native(void) {
    PyObject *m = PyModule_Create(&module_def);
    if (!m) return NULL;
    return m;
}
