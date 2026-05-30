#include <Python.h>
#include <stdint.h>
#include <string.h>

/* Keccak-256 state and constants */
#define ROTL64(x, y) (((x) << (y)) | ((x) >> (64 - (y))))

static const uint64_t keccakf_rndc[24] = {
    0x0000000000000001ULL, 0x0000000000008082ULL, 0x800000000000808aULL,
    0x8000000080008000ULL, 0x000000000000808bULL, 0x0000000080000001ULL,
    0x8000000080008081ULL, 0x8000000000008009ULL, 0x000000000000008aULL,
    0x0000000000000088ULL, 0x0000000080008009ULL, 0x000000008000000aULL,
    0x000000008000808bULL, 0x800000000000008bULL, 0x8000000000008089ULL,
    0x8000000000008003ULL, 0x8000000000008002ULL, 0x8000000000000080ULL,
    0x000000000000800aULL, 0x800000008000000aULL, 0x8000000080008081ULL,
    0x8000000000008080ULL, 0x0000000080000001ULL, 0x8000000080008008ULL
};

static const int keccakf_rotc[24] = {
    1,  3,  6,  10, 15, 21, 28, 36, 45, 55, 2,  14,
    27, 44, 65, 39, 8,  20, 35, 52, 18, 53, 32, 56
};

static const int keccakf_piln[24] = {
    10, 7,  11, 17, 18, 3,  5,  16, 8,  21, 24, 4,
    15, 23, 19, 13, 12, 2,  20, 14, 22, 9,  6,  1
};

static void keccakf(uint64_t st[25]) {
    int i, j, r;
    uint64_t t, bc[5];
    for (r = 0; r < 24; r++) {
        for (i = 0; i < 5; i++) bc[i] = st[i] ^ st[i + 5] ^ st[i + 10] ^ st[i + 15] ^ st[i + 20];
        for (i = 0; i < 5; i++) {
            t = bc[(i + 4) % 5] ^ ROTL64(bc[(i + 1) % 5], 1);
            for (j = 0; j < 25; j += 5) st[j + i] ^= t;
        }
        t = st[1];
        for (i = 0; i < 24; i++) {
            j = keccakf_piln[i];
            bc[0] = st[j];
            st[j] = ROTL64(t, keccakf_rotc[i]);
            t = bc[0];
        }
        for (j = 0; j < 25; j += 5) {
            for (i = 0; i < 5; i++) bc[i] = st[j + i];
            for (i = 0; i < 5; i++) st[j + i] ^= (~bc[(i + 1) % 5]) & bc[(i + 2) % 5];
        }
        st[0] ^= keccakf_rndc[r];
    }
}

void keccak256(const uint8_t *in, size_t len, uint8_t *out) {
    uint64_t st[25];
    uint8_t temp[144];
    size_t rsiz = 136;
    memset(st, 0, sizeof(st));
    while (len >= rsiz) {
        for (size_t i = 0; i < rsiz / 8; i++) st[i] ^= ((uint64_t *)in)[i];
        keccakf(st);
        in += rsiz; len -= rsiz;
    }
    memset(temp, 0, sizeof(temp));
    memcpy(temp, in, len);
    temp[len] = 0x01;
    temp[rsiz - 1] |= 0x80;
    for (size_t i = 0; i < rsiz / 8; i++) st[i] ^= ((uint64_t *)temp)[i];
    keccakf(st);
    memcpy(out, st, 32);
}

static int compare_256(const uint8_t *a, const uint8_t *b) {
    for (int i = 0; i < 32; i++) {
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return 1;
    }
    return 0;
}

static PyObject* pow_search(PyObject* self, PyObject* args) {
    Py_buffer prefix_buf, target_buf;
    unsigned long long start_nonce;
    unsigned int iterations;
    if (!PyArg_ParseTuple(args, "y*y*KI", &prefix_buf, &target_buf, &start_nonce, &iterations)) return NULL;
    uint8_t *prefix = (uint8_t *)prefix_buf.buf;
    size_t prefix_len = prefix_buf.len;
    uint8_t *target = (uint8_t *)target_buf.buf;
    uint8_t block[128];
    memcpy(block, prefix, prefix_len);
    uint8_t digest[32];
    uint64_t nonce = start_nonce;
    int found = 0;
    for (unsigned int i = 0; i < iterations; i++) {
        uint64_t n = nonce;
        for (int j = 31; j >= 0; j--) { block[prefix_len + j] = (uint8_t)(n & 0xFF); n >>= 8; }
        keccak256(block, prefix_len + 32, digest);
        if (compare_256(digest, target) <= 0) { found = 1; break; }
        nonce++;
    }
    PyBuffer_Release(&prefix_buf);
    PyBuffer_Release(&target_buf);
    if (found) return Py_BuildValue("Ky#", nonce, digest, 32);
    Py_RETURN_NONE;
}

static PyMethodDef KeccakPowMethods[] = {
    {"pow_search", pow_search, METH_VARARGS, "Search for nonce using Keccak-256"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef keccakpowmodule = { PyModuleDef_HEAD_INIT, "keccak_pow", NULL, -1, KeccakPowMethods };
PyMODINIT_FUNC PyInit_keccak_pow(void) { return PyModule_Create(&keccakpowmodule); }
