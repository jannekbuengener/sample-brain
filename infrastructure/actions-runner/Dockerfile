FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

ARG RUNNER_VERSION=2.323.0
ARG RUNNER_ARCH=x64
ARG RUNNER_CONTAINER_HOOKS_VERSION=0.6.2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        jq \
        sudo \
        systemd \
        systemd-sysv \
        && \
    rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" --uid 1001 runner && \
    echo "runner ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/runner && \
    chmod 0440 /etc/sudoers.d/runner

RUN mkdir -p /home/runner/actions-runner && \
    cd /home/runner/actions-runner && \
    curl -o actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz \
        -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz && \
    tar xzf actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz && \
    rm actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz && \
    ./bin/installdependencies.sh

RUN cd /home/runner/actions-runner && \
    curl -o actions-runner-hooks-${RUNNER_CONTAINER_HOOKS_VERSION}.tar.gz \
        -L https://github.com/actions/runner-container-hooks/releases/download/v${RUNNER_CONTAINER_HOOKS_VERSION}/actions-runner-container-hooks-${RUNNER_CONTAINER_HOOKS_VERSION}.tar.gz && \
    tar xzf actions-runner-hooks-${RUNNER_CONTAINER_HOOKS_VERSION}.tar.gz && \
    rm actions-runner-hooks-${RUNNER_CONTAINER_HOOKS_VERSION}.tar.gz

ENV RUNNER_ALLOW_RUNASROOT=1
ENV ACTIONS_RUNNER_HOOK_JOB_STARTED=/home/runner/actions-runner/hooks/job-started.sh

COPY entrypoint.sh /home/runner/actions-runner/entrypoint.sh
RUN chmod +x /home/runner/actions-runner/entrypoint.sh

RUN chown -R runner:runner /home/runner

WORKDIR /home/runner/actions-runner
USER runner

ENTRYPOINT ["/home/runner/actions-runner/entrypoint.sh"]
