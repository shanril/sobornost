/*
 * Linux native module stub — NOT YET IMPLEMENTED.
 *
 * Importing _native on Linux raises NotImplementedError.
 * The module entry point (PyInit__native) returns NULL, which
 * causes Python to fail the import with a clear error message.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyMethodDef module_methods[] = {
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "Linux support is not yet implemented",
    -1,
    module_methods,
};

PyMODINIT_FUNC PyInit__native(void) {
    PyErr_SetString(PyExc_NotImplementedError,
        "sobornost: Linux support is not yet implemented");
    return NULL;
}
