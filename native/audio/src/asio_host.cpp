#if defined(_WIN32) && !defined(SAMPLEBRAIN_AUDIO_TEST_NULL_BACKEND)

#include "asio_host.hpp"
#include "sb_asio_com.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>
#include <vector>

struct SbAsioHost {
    IASIO* driver = nullptr;
    ASIOBufferInfo buffer_infos[8] = {};
    ASIOChannelInfo channel_infos[8] = {};
    ASIOCallbacks callbacks = {};
    long buffer_size = 0;
    long output_channels = 0;
    ASIOSampleType sample_type = ASIOSTFloat32LSB;
    bool buffers_created = false;
    bool com_inited_here = false;
    bool running = false;
    std::atomic<int> device_lost{0};
    sb_asio_render_fn render = nullptr;
    void* render_user = nullptr;
    std::vector<float> scratch;
    std::string driver_name;
    std::string clsid;
};

namespace {

// ASIO callbacks run on the driver thread, not the opener thread.
std::atomic<SbAsioHost*> g_callback_host{nullptr};

void write_silence(SbAsioHost* host, long index) {
    for (long ch = 0; ch < host->output_channels; ++ch) {
        void* buf = host->buffer_infos[ch].buffers[index];
        if (!buf) continue;
        size_t sample_bytes = sizeof(float);
        if (host->sample_type == ASIOSTInt32LSB || host->sample_type == ASIOSTInt32MSB) {
            sample_bytes = sizeof(int32_t);
        } else if (host->sample_type == ASIOSTInt16LSB || host->sample_type == ASIOSTInt16MSB) {
            sample_bytes = sizeof(int16_t);
        }
        std::memset(buf, 0, static_cast<size_t>(host->buffer_size) * sample_bytes);
    }
}

void float_to_driver(SbAsioHost* host, long index, const float* interleaved) {
    for (long ch = 0; ch < host->output_channels; ++ch) {
        void* buf = host->buffer_infos[ch].buffers[index];
        if (!buf) continue;
        if (host->sample_type == ASIOSTFloat32LSB || host->sample_type == ASIOSTFloat32MSB) {
            float* dst = static_cast<float*>(buf);
            for (long i = 0; i < host->buffer_size; ++i) {
                dst[i] = interleaved[static_cast<size_t>(i) * host->output_channels + ch];
            }
        } else if (host->sample_type == ASIOSTInt32LSB) {
            int32_t* dst = static_cast<int32_t*>(buf);
            for (long i = 0; i < host->buffer_size; ++i) {
                float s = interleaved[static_cast<size_t>(i) * host->output_channels + ch];
                // Scale in double and clamp to INT32_MAX so +1.0f never rounds
                // to 2147483648 before the int32 cast (UB / sign flip).
                double scaled = static_cast<double>(s) * 2147483647.0;
                if (scaled > 2147483647.0) scaled = 2147483647.0;
                if (scaled < -2147483648.0) scaled = -2147483648.0;
                dst[i] = static_cast<int32_t>(scaled);
            }
        } else {
            // Leave silence for uncommon packed formats in V1.
        }
    }
}

void buffer_switch(long index, ASIOBool /*directProcess*/) {
    SbAsioHost* host = g_callback_host.load(std::memory_order_acquire);
    if (!host || !host->driver) return;
    if (!host->running || !host->render) {
        write_silence(host, index);
        host->driver->outputReady();
        return;
    }
    const size_t samples =
        static_cast<size_t>(host->buffer_size) * static_cast<size_t>(host->output_channels);
    host->scratch.resize(samples);
    host->render(host->render_user, host->scratch.data(), static_cast<uint32_t>(host->buffer_size));
    float_to_driver(host, index, host->scratch.data());
    host->driver->outputReady();
}

void sample_rate_changed(ASIOSampleRate) {
    // Live rate changes from the driver/control panel invalidate the opened
    // rate contract. Signal device-lost so the control thread fail-closes
    // rather than continuing with a stale SessionTransport/PCM rate.
    SbAsioHost* host = g_callback_host.load(std::memory_order_acquire);
    if (host) host->device_lost.store(1, std::memory_order_release);
}

long asio_message(long selector, long value, void*, double*) {
    if (selector == kAsioSelectorSupported) {
        return (value == kAsioEngineVersion || value == kAsioResetRequest) ? 1 : 0;
    }
    if (selector == kAsioEngineVersion) return 2;
    if (selector == kAsioResetRequest) {
        SbAsioHost* host = g_callback_host.load(std::memory_order_acquire);
        if (host) host->device_lost.store(1, std::memory_order_release);
        return 1;
    }
    return 0;
}

ASIOTime* buffer_switch_time_info(ASIOTime*, long index, ASIOBool direct) {
    buffer_switch(index, direct);
    return nullptr;
}

}  // namespace

int sb_asio_host_available(void) { return 1; }

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
) {
    if (!out_host || !clsid_string || !render || output_channels == 0 || output_channels > 8) {
        return SB_ERR_INVALID_ARG;
    }
    *out_host = nullptr;

    auto* host = new (std::nothrow) SbAsioHost();
    if (!host) return SB_ERR_OUT_OF_MEMORY;
    host->render = render;
    host->render_user = render_user;

    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (SUCCEEDED(hr)) {
        host->com_inited_here = (hr == S_OK);
    } else if (hr != RPC_E_CHANGED_MODE && hr != S_FALSE) {
        delete host;
        return SB_ERR_DEVICE_ERROR;
    }

    CLSID clsid{};
    int wide_len = MultiByteToWideChar(CP_UTF8, 0, clsid_string, -1, nullptr, 0);
    if (wide_len <= 0) {
        delete host;
        return SB_ERR_INVALID_ARG;
    }
    std::wstring wide(static_cast<size_t>(wide_len), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, clsid_string, -1, wide.data(), wide_len);
    if (FAILED(CLSIDFromString(wide.c_str(), &clsid))) {
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_INVALID_ARG;
    }

    // Steinberg convention: CoCreateInstance(clsid, ..., clsid, ...) yields IASIO*.
    IASIO* driver = nullptr;
    hr = CoCreateInstance(
        clsid,
        nullptr,
        CLSCTX_INPROC_SERVER,
        clsid,
        reinterpret_cast<void**>(&driver)
    );
    if (FAILED(hr) || !driver) {
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_DEVICE_ERROR;
    }
    if (!driver->init(GetDesktopWindow())) {
        char err[128] = {};
        driver->getErrorMessage(err);
        driver->Release();
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_DEVICE_ERROR;
    }

    char name[64] = {};
    driver->getDriverName(name);
    long in_ch = 0, out_ch = 0;
    if (driver->getChannels(&in_ch, &out_ch) != ASE_OK || out_ch <= 0) {
        driver->Release();
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_DEVICE_ERROR;
    }
    long use_out = static_cast<long>(output_channels);
    if (use_out > out_ch) use_out = out_ch;

    ASIOSampleRate rate = static_cast<ASIOSampleRate>(sample_rate);
    uint32_t effective_rate = 0;
    if (driver->canSampleRate(rate) == ASE_OK) {
        ASIOError set_rc = driver->setSampleRate(rate);
        if (set_rc != ASE_OK && set_rc != ASE_SUCCESS) {
            // Requested rate claimed supported but could not be applied.
            ASIOSampleRate current = 0;
            if (driver->getSampleRate(&current) != ASE_OK || current <= 0) {
                driver->Release();
                if (host->com_inited_here) CoUninitialize();
                delete host;
                return SB_ERR_UNSUPPORTED;
            }
            effective_rate = static_cast<uint32_t>(current);
        } else {
            ASIOSampleRate current = 0;
            if (driver->getSampleRate(&current) == ASE_OK && current > 0) {
                effective_rate = static_cast<uint32_t>(current);
            } else {
                effective_rate = sample_rate;
            }
        }
    } else {
        ASIOSampleRate current = 0;
        if (driver->getSampleRate(&current) == ASE_OK && current > 0) {
            effective_rate = static_cast<uint32_t>(current);
        }
    }
    if (effective_rate == 0) {
        driver->Release();
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_UNSUPPORTED;
    }

    long min_sz = 0, max_sz = 0, pref_sz = 0, gran = 0;
    if (driver->getBufferSize(&min_sz, &max_sz, &pref_sz, &gran) != ASE_OK) {
        driver->Release();
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_DEVICE_ERROR;
    }
    long buf = static_cast<long>(preferred_buffer_frames);
    if (buf < min_sz) buf = min_sz;
    if (buf > max_sz && max_sz > 0) buf = max_sz;
    if (gran > 0) {
        buf = min_sz + ((buf - min_sz) / gran) * gran;
        if (buf < min_sz) buf = min_sz;
    } else if (pref_sz > 0) {
        buf = pref_sz;
    }

    for (long ch = 0; ch < use_out; ++ch) {
        host->buffer_infos[ch].isInput = ASIOFalse;
        host->buffer_infos[ch].channelNum = ch;
        host->buffer_infos[ch].buffers[0] = nullptr;
        host->buffer_infos[ch].buffers[1] = nullptr;
        host->channel_infos[ch].channel = ch;
        host->channel_infos[ch].isInput = ASIOFalse;
        if (driver->getChannelInfo(&host->channel_infos[ch]) == ASE_OK) {
            host->sample_type = host->channel_infos[ch].type;
        }
    }
    // V1 renderer supports Float32 and Int32LSB only. Fail closed on packed/
    // Int16/Float64 rather than reporting healthy callbacks while writing silence
    // into the wrong buffer stride (#1350 review).
    if (host->sample_type != ASIOSTFloat32LSB &&
        host->sample_type != ASIOSTFloat32MSB &&
        host->sample_type != ASIOSTInt32LSB) {
        driver->Release();
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_UNSUPPORTED;
    }

    host->callbacks.bufferSwitch = &buffer_switch;
    host->callbacks.sampleRateDidChange = &sample_rate_changed;
    host->callbacks.asioMessage = &asio_message;
    host->callbacks.bufferSwitchTimeInfo = &buffer_switch_time_info;

    g_callback_host.store(host, std::memory_order_release);
    ASIOError cre = driver->createBuffers(host->buffer_infos, use_out, buf, &host->callbacks);
    if (cre != ASE_OK && cre != ASE_SUCCESS) {
        g_callback_host.store(nullptr, std::memory_order_release);
        driver->Release();
        if (host->com_inited_here) CoUninitialize();
        delete host;
        return SB_ERR_DEVICE_ERROR;
    }

    host->driver = driver;
    host->buffer_size = buf;
    host->output_channels = use_out;
    host->buffers_created = true;
    host->driver_name = name;
    host->clsid = clsid_string;

    if (out_driver_name && out_driver_name_len > 0) {
        std::snprintf(out_driver_name, out_driver_name_len, "%s", name);
    }
    if (out_sample_rate) *out_sample_rate = effective_rate;
    if (out_buffer_frames) *out_buffer_frames = static_cast<uint32_t>(buf);
    if (out_output_channels) *out_output_channels = static_cast<uint32_t>(use_out);

    *out_host = host;
    return SB_OK;
}

sb_result_t sb_asio_host_start(SbAsioHost* host) {
    if (!host || !host->driver) return SB_ERR_NOT_INITIALIZED;
    g_callback_host.store(host, std::memory_order_release);
    host->running = true;
    ASIOError err = host->driver->start();
    if (err != ASE_OK && err != ASE_SUCCESS) {
        host->running = false;
        return SB_ERR_DEVICE_ERROR;
    }
    return SB_OK;
}

sb_result_t sb_asio_host_stop(SbAsioHost* host) {
    if (!host || !host->driver) return SB_OK;
    host->running = false;
    host->driver->stop();
    return SB_OK;
}

int sb_asio_host_device_lost(SbAsioHost* host) {
    if (!host) return 0;
    return host->device_lost.load(std::memory_order_acquire);
}

void sb_asio_host_close(SbAsioHost** host_ptr) {
    if (!host_ptr || !*host_ptr) return;
    SbAsioHost* host = *host_ptr;
    host->running = false;
    if (host->driver) {
        host->driver->stop();
        if (host->buffers_created) {
            host->driver->disposeBuffers();
            host->buffers_created = false;
        }
        host->driver->Release();
        host->driver = nullptr;
    }
    SbAsioHost* expected = host;
    g_callback_host.compare_exchange_strong(expected, nullptr, std::memory_order_acq_rel);
    if (host->com_inited_here) CoUninitialize();
    delete host;
    *host_ptr = nullptr;
}

#endif
