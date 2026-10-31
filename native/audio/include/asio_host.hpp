#pragma once

#include "samplebrain_audio.h"

#include <cstdint>

#if defined(_WIN32) && !defined(SAMPLEBRAIN_AUDIO_TEST_NULL_BACKEND)

struct SbAsioHost;

typedef void (*sb_asio_render_fn)(void* user_data, float* interleaved_output, uint32_t frame_count);

int sb_asio_host_available(void);

sb_result_t sb_asio_host_open(
    SbAsioHost** out_host,
    const char* clsid_string,
    uint32_t sample_rate,
    uint32_t preferred_buffer_frames,
    uint32_t output_channels,
    sb_asio_render_fn render,
    void* render_user,
    char* out_driver_name,
    size_t out_driver_name_len,
    uint32_t* out_sample_rate,
    uint32_t* out_buffer_frames,
    uint32_t* out_output_channels
);

sb_result_t sb_asio_host_start(SbAsioHost* host);
sb_result_t sb_asio_host_stop(SbAsioHost* host);
void sb_asio_host_close(SbAsioHost** host);
/** Non-zero when the driver requested reset/stop (poll from control thread). */
int sb_asio_host_device_lost(SbAsioHost* host);

#else

inline int sb_asio_host_available(void) { return 0; }

#endif
