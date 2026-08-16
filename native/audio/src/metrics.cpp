// metrics.cpp - Metrics implementation
#include "metrics.h"
#include <algorithm>
#include <chrono>

MetricsCollector::MetricsCollector() {
    reset();
}

void MetricsCollector::reset() {
    callback_times_us.fill(0.0);
    sample_index.store(0);
    total_callbacks.store(0);
    underflow_count.store(0);
    overflow_count.store(0);
    xrun_count.store(0);
}

void MetricsCollector::on_callback_start() {
    callback_start_time = std::chrono::high_resolution_clock::now();
}

void MetricsCollector::on_callback_end() {
    auto end_time = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - callback_start_time);
    double us = duration.count() / 1000.0;

    size_t idx = sample_index.fetch_add(1, std::memory_order_relaxed);
    if (idx >= SAMPLE_COUNT) {
        idx = idx % SAMPLE_COUNT;
    }
    callback_times_us[idx] = us;

    total_callbacks.fetch_add(1, std::memory_order_relaxed);
}

void MetricsCollector::get_snapshot(double& mean_us, double& p95_us, double& p99_us, double& max_us,
                                    uint64_t& underflows, uint64_t& overflows, uint64_t& xruns) {
    // Copy samples for sorting
    size_t count = std::min(total_callbacks.load(std::memory_order_relaxed), SAMPLE_COUNT);
    if (count == 0) {
        mean_us = p95_us = p99_us = max_us = 0.0;
        underflows = underflow_count.load();
        overflows = overflow_count.load();
        xruns = xrun_count.load();
        return;
    }

    // Create sorted copy
    std::vector<double> samples;
    samples.reserve(count);
    for (size_t i = 0; i < count; ++i) {
        samples.push_back(callback_times_us[i]);
    }
    std::sort(samples.begin(), samples.end());

    // Mean
    double sum = 0.0;
    for (double v : samples) sum += v;
    mean_us = sum / count;

    // Percentiles
    size_t p95_idx = static_cast<size_t>(count * 0.95);
    size_t p99_idx = static_cast<size_t>(count * 0.99);
    p95_us = samples[std::min(p95_idx, count - 1)];
    p99_us = samples[std::min(p99_idx, count - 1)];
    max_us = samples[count - 1];

    underflows = underflow_count.load();
    overflows = overflow_count.load();
    xruns = xrun_count.load();
}