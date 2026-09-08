# syntax=docker/dockerfile:1.7

FROM golang:1.27.1-bookworm@sha256:648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b AS build

ARG TARGETARCH
ENV CGO_ENABLED=1 \
    GOTOOLCHAIN=local

RUN apt-get update \
    && apt-get install --yes --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*

ADD --checksum=sha256:8f1c4cfe1c687918e00bf9ab6f9966ebd4d727d3d64ccb109b2561afcd347b07 \
    https://github.com/ollama/ollama/archive/b79067b0db7417f20108363bc22adb97f35c966a.tar.gz \
    /tmp/ollama-source.tar.gz

RUN mkdir /src \
    && tar --extract --gzip --file /tmp/ollama-source.tar.gz \
        --directory /src --strip-components=1 \
    && rm /tmp/ollama-source.tar.gz

WORKDIR /src

# The source revision is the exact commit behind Ollama 0.33.3. These are the
# compatible fixed versions selected from the current advisory data; every
# resolved version is asserted before compiling the replacement executable.
RUN test "$(go env GOVERSION)" = "go1.27.1" \
    && go get \
        github.com/buger/jsonparser@v1.1.2 \
        golang.org/x/crypto@v0.55.0 \
        golang.org/x/image@v0.45.0 \
        golang.org/x/mod@v0.40.0 \
        golang.org/x/net@v0.57.0 \
        golang.org/x/sync@v0.22.0 \
        golang.org/x/sys@v0.47.0 \
        golang.org/x/term@v0.45.0 \
        golang.org/x/text@v0.41.0 \
    && go mod tidy \
    && go mod verify \
    && test "$(go list -m -f '{{.Version}}' github.com/buger/jsonparser)" = "v1.1.2" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/crypto)" = "v0.55.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/image)" = "v0.45.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/mod)" = "v0.40.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = "v0.57.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/sync)" = "v0.22.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/sys)" = "v0.47.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/term)" = "v0.45.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/text)" = "v0.41.0"

RUN mkdir /out \
    && go build -trimpath -buildmode=pie \
        -ldflags="-s -w -X=github.com/ollama/ollama/version.Version=0.33.3-careeros.1 -X=github.com/ollama/ollama/server.mode=release" \
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
            'source_revision=b79067b0db7417f20108363bc22adb97f35c966a' \
            'source_archive_sha256=8f1c4cfe1c687918e00bf9ab6f9966ebd4d727d3d64ccb109b2561afcd347b07' \
            'builder=golang:1.27.1-bookworm@sha256:648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b'; \
        go version -m /out/ollama; \
        sha256sum /out/ollama; \
    } > /out/BUILD_PROVENANCE.txt

FROM ollama/ollama:0.33.3@sha256:32931b46719f673c05fdbaa81ccb26da18ea4a1c57590a754874ab28ba269eb2

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
      org.opencontainers.image.description="Ollama 0.33.3 with a reproducibly rebuilt, vulnerability-remediated Go executable" \
      org.opencontainers.image.source="https://github.com/ollama/ollama" \
      org.opencontainers.image.revision="b79067b0db7417f20108363bc22adb97f35c966a" \
      org.opencontainers.image.version="0.33.3-careeros.1" \
      org.opencontainers.image.licenses="MIT" \
      io.careeros.ollama.source-archive-sha256="8f1c4cfe1c687918e00bf9ab6f9966ebd4d727d3d64ccb109b2561afcd347b07"

COPY --from=build --chmod=0755 /out/ollama /usr/bin/ollama
COPY --from=build /out/GO_LICENSE /usr/lib/ollama/GO_LICENSE
COPY --from=build /out/BUILD_PROVENANCE.txt /usr/share/doc/careeros-local-ollama/BUILD_PROVENANCE.txt

WORKDIR /var/lib/ollama
USER 10001:10001
