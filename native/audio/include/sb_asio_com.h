// Minimal ASIO COM host types from the public ASIO specification (#1350).
// Does not redistribute the Steinberg ASIO SDK tree. Manufacturer drivers are
// CoCreateInstance'd via their registered CLSID.
#pragma once

#ifdef _WIN32

#include <windows.h>
#include <objbase.h>
#include <cstdint>

typedef long ASIOBool;
#define ASIOFalse 0L
#define ASIOTrue 1L

typedef long ASIOError;
#define ASE_OK 0L
#define ASE_SUCCESS 0x3f4847a0L
#define ASE_NotPresent (-1000L)
#define ASE_HWMalfunction (-999L)
#define ASE_InvalidParameter (-998L)
#define ASE_InvalidMode (-997L)
#define ASE_SPNotAdvancing (-996L)
#define ASE_NoClock (-995L)
#define ASE_NoMemory (-994L)

typedef long ASIOSampleType;
#define ASIOSTInt16MSB 0L
#define ASIOSTInt24MSB 1L
#define ASIOSTInt32MSB 2L
#define ASIOSTFloat32MSB 3L
#define ASIOSTFloat64MSB 4L
#define ASIOSTInt16LSB 16L
#define ASIOSTInt24LSB 17L
#define ASIOSTInt32LSB 18L
#define ASIOSTFloat32LSB 19L
#define ASIOSTFloat64LSB 20L

typedef double ASIOSampleRate;

typedef struct ASIOBufferInfo {
    ASIOBool isInput;
    long channelNum;
    void* buffers[2];
} ASIOBufferInfo;

typedef struct ASIOChannelInfo {
    long channel;
    ASIOBool isInput;
    ASIOBool isActive;
    long channelGroup;
    ASIOSampleType type;
    char name[32];
} ASIOChannelInfo;

typedef struct ASIOTime ASIOTime;

typedef void (*asio_buffer_switch_fn)(long index, ASIOBool directProcess);
typedef void (*asio_sample_rate_changed_fn)(ASIOSampleRate sRate);
typedef long (*asio_message_fn)(long selector, long value, void* message, double* opt);
typedef ASIOTime* (*asio_buffer_switch_time_info_fn)(ASIOTime* params, long index, ASIOBool directProcess);

typedef struct ASIOCallbacks {
    asio_buffer_switch_fn bufferSwitch;
    asio_sample_rate_changed_fn sampleRateDidChange;
    asio_message_fn asioMessage;
    asio_buffer_switch_time_info_fn bufferSwitchTimeInfo;
} ASIOCallbacks;

#define kAsioSelectorSupported 1L
#define kAsioEngineVersion 2L
#define kAsioResetRequest 3L
#define kAsioBufferSizeChange 4L
#define kAsioResyncRequest 5L
#define kAsioLatenciesChanged 6L
#define kAsioSupportsTimeInfo 7L

// MSVC COM thiscall matches C++ member layout for IASIO.
struct IASIO : public IUnknown {
    virtual ASIOBool init(void* sysHandle) = 0;
    virtual void getDriverName(char* name) = 0;
    virtual long getDriverVersion() = 0;
    virtual void getErrorMessage(char* string) = 0;
    virtual ASIOError start() = 0;
    virtual ASIOError stop() = 0;
    virtual ASIOError getChannels(long* numInputChannels, long* numOutputChannels) = 0;
    virtual ASIOError getLatencies(long* inputLatency, long* outputLatency) = 0;
    virtual ASIOError getBufferSize(long* minSize, long* maxSize, long* preferredSize, long* granularity) = 0;
    virtual ASIOError canSampleRate(ASIOSampleRate sampleRate) = 0;
    virtual ASIOError getSampleRate(ASIOSampleRate* sampleRate) = 0;
    virtual ASIOError setSampleRate(ASIOSampleRate sampleRate) = 0;
    virtual ASIOError getClockSources(void* clocks, long* numSources) = 0;
    virtual ASIOError setClockSource(long reference) = 0;
    virtual ASIOError getSamplePosition(void* sPos, void* tStamp) = 0;
    virtual ASIOError getChannelInfo(ASIOChannelInfo* info) = 0;
    virtual ASIOError createBuffers(ASIOBufferInfo* bufferInfos, long numChannels, long bufferSize, ASIOCallbacks* callbacks) = 0;
    virtual ASIOError disposeBuffers() = 0;
    virtual ASIOError controlPanel() = 0;
    virtual ASIOError future(long selector, void* opt) = 0;
    virtual ASIOError outputReady() = 0;
};

#endif  // _WIN32
