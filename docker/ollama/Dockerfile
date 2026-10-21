# syntax=docker/dockerfile:1.7

FROM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61 AS build

ARG TARGETARCH
ENV CGO_ENABLED=1 \
    GOTOOLCHAIN=local

RUN apt-get update \
    && apt-get install --yes --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*

ADD --checksum=sha256:cfd3168b67445cdb0418892ccdbccb1348921f570e025695be52ffb2fe894d90 \
    https://github.com/ollama/ollama/archive/6383a0fa9cbf97494b847226e189f6e36b401a08.tar.gz \
    /tmp/ollama-source.tar.gz

RUN mkdir /src \
    && tar --extract --gzip --file /tmp/ollama-source.tar.gz \
        --directory /src --strip-components=1 \
    && rm /tmp/ollama-source.tar.gz

WORKDIR /src

# The source revision is the exact commit behind Ollama 0.34.3. These are the
# compatible fixed versions selected from the current advisory data; every
# resolved version is asserted before compiling the replacement executable.
RUN test "$(go env GOVERSION)" = "go1.27.2" \
    && go get \
        github.com/buger/jsonparser@v1.1.2 \
        golang.org/x/crypto@v0.57.0 \
        golang.org/x/image@v0.45.0 \
        golang.org/x/mod@v0.41.0 \
        golang.org/x/net@v0.60.0 \
        golang.org/x/sync@v0.23.0 \
        golang.org/x/sys@v0.48.0 \
        golang.org/x/term@v0.46.0 \
        golang.org/x/text@v0.42.0 \
    && go mod tidy \
    && go mod verify \
    && test "$(go list -m -f '{{.Version}}' github.com/buger/jsonparser)" = "v1.1.2" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/crypto)" = "v0.57.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/image)" = "v0.45.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/mod)" = "v0.41.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = "v0.60.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/sync)" = "v0.23.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/sys)" = "v0.48.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/term)" = "v0.46.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/text)" = "v0.42.0"

RUN mkdir /out \
    && go build -trimpath -buildmode=pie \
        -ldflags="-s -w -X=github.com/ollama/ollama/version.Version=0.34.3-careeros.1 -X=github.com/ollama/ollama/server.mode=release" \
        -o /out/ollama . \
    && cmake \
        -DGO_EXECUTABLE=/usr/local/go/bin/go \
        -DSOURCE_DIR=/src \
        -DBINARY_DIR=/tmp/go-license \
        -DOUTPUT_DIR=/out \
        -DTARGETS=linux/${TARGETARCH} \
        -P /src/cmake/generate_go_license.cmake \
    && { \
        printf '%s\n' \
            'source=https://github.com/ollama/ollama' \
            'source_revision=6383a0fa9cbf97494b847226e189f6e36b401a08' \
            'source_archive_sha256=cfd3168b67445cdb0418892ccdbccb1348921f570e025695be52ffb2fe894d90' \
            'builder=golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61'; \
        go version -m /out/ollama; \
        sha256sum /out/ollama; \
    } > /out/BUILD_PROVENANCE.txt

FROM ollama/ollama:0.40.4@sha256:926d40fd6eeeebd346b5c358a63de2a10ec995371cd93dd22f1843200694b1a6

ENV HOME=/var/lib/ollama

RUN ! grep --extended-regexp '^[^:]+:[^:]*:10001:' /etc/passwd \
    && ! grep --extended-regexp '^[^:]+:[^:]*:10001:' /etc/group \
    && printf 'ollama:x:10001:\n' >> /etc/group \
    && printf 'ollama:x:10001:10001:Ollama runtime:/var/lib/ollama:/usr/sbin/nologin\n' \
        >> /etc/passwd \
    && mkdir --parents /var/lib/ollama/.ollama \
    && chown --recursive 10001:10001 /var/lib/ollama \
    && chmod 0700 /var/lib/ollama /var/lib/ollama/.ollama

LABEL org.opencontainers.image.title="CareerOS Local Ollama runtime" \
      org.opencontainers.image.description="Ollama 0.34.3 with a reproducibly rebuilt, vulnerability-remediated Go executable" \
      org.opencontainers.image.source="https://github.com/ollama/ollama" \
      org.opencontainers.image.revision="6383a0fa9cbf97494b847226e189f6e36b401a08" \
      org.opencontainers.image.version="0.34.3-careeros.1" \
      org.opencontainers.image.licenses="MIT" \
      io.careeros.ollama.source-archive-sha256="cfd3168b67445cdb0418892ccdbccb1348921f570e025695be52ffb2fe894d90"

COPY --from=build --chmod=0755 /out/ollama /usr/bin/ollama
COPY --from=build /out/GO_LICENSE /usr/lib/ollama/GO_LICENSE
COPY --from=build /out/BUILD_PROVENANCE.txt /usr/share/doc/careeros-local-ollama/BUILD_PROVENANCE.txt

# Patch the matched Ubuntu runtime as well as the rebuilt Go executable.
# Verify a minimum fixed release while accepting newer vendor security updates.
RUN set -eu; \
    apt-get update; \
    apt-get install --yes --no-install-recommends --only-upgrade \
        libssl3t64 openssl; \
    for package in libssl3t64 openssl; do \
        installed_version="$(dpkg-query --show --showformat='${Version}' "$package")"; \
        dpkg --compare-versions "$installed_version" ge '3.0.13-0ubuntu3.16'; \
        printf 'runtime_package=%s version=%s\n' "$package" "$installed_version" \
            >> /usr/share/doc/careeros-local-ollama/BUILD_PROVENANCE.txt; \
    done; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /var/lib/ollama
USER 10001:10001
