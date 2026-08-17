// metrics.h - Metrics collection
#ifndef SAMPLEBRAIN_METRICS_H
#define SAMPLEBRAIN_METRICS_H

#include <atomic>
#include <array>
#include <chrono>

class MetricsCollector {
public:
    MetricsCollector();
    void reset();
    void on_callback_start();
    void on_callback_end();
    void get_snapshot(double& mean_us, double& p95_us, double& p99_us, double& max_us, double& p99_9_us,
                      uint64_t& underflows, uint64_t& overflows, uint64_t& xruns);

private:
    static constexpr size_t SAMPLE_COUNT = 10000;
    std::array<double, SAMPLE_COUNT> callback_times_us;
    std::atomic<size_t> sample_index{0};
    std::atomic<uint64_t> total_callbacks{0};

    std::atomic<uint64_t> underflow_count{0};
    std::atomic<uint64_t> overflow_count{0};
    std::atomic<uint64_t> xrun_count{0};

    std::chrono::high_resolution_clock::time_point callback_start_time;
};

#endif