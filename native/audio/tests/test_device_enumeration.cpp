#include <samplebrain_audio.h>

#include <cstdio>
#include <cstring>

static bool enumerate_and_check(int capture, uint32_t capacity) {
    sb_device_info_t devices[32] = {};
    uint32_t count = 0;
    if (sb_enumerate_devices(capture, devices, capacity, &count) != SB_OK || count > capacity) {
        return false;
    }
    for (uint32_t i = 0; i < count; ++i) {
        if (std::memchr(devices[i].name, '\0', sizeof(devices[i].name)) == nullptr ||
            std::memchr(devices[i].id_hex, '\0', sizeof(devices[i].id_hex)) == nullptr ||
            (devices[i].is_default != 0 && devices[i].is_default != 1)) {
            return false;
        }
    }
    return true;
}

int main() {
    for (int repeat = 0; repeat < 32; ++repeat) {
        for (int capture = 0; capture <= 1; ++capture) {
            if (!enumerate_and_check(capture, 1) || !enumerate_and_check(capture, 32)) {
                std::fprintf(stderr, "device enumeration failed: capture=%d repeat=%d\n", capture, repeat);
                return 1;
            }
        }
    }
    return 0;
}
