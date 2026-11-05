FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

USER root
COPY .nvmrc frontend/package.json /tmp/chubby-toolchain/

RUN set -eu; \
    version="$(cat /tmp/chubby-toolchain/.nvmrc)"; \
    case "$(dpkg --print-architecture)" in \
      amd64) architecture=x64 ;; \
      arm64) architecture=arm64 ;; \
      *) echo "Unsupported Node.js architecture" >&2; exit 1 ;; \
    esac; \
    archive="node-v${version}-linux-${architecture}.tar.xz"; \
    cd /tmp/chubby-toolchain; \
    curl --fail --location --retry 3 --output "$archive" "https://nodejs.org/dist/v${version}/${archive}"; \
    curl --fail --location --retry 3 --output SHASUMS256.txt "https://nodejs.org/dist/v${version}/SHASUMS256.txt"; \
    grep " ${archive}$" SHASUMS256.txt | sha256sum --check; \
    tar --extract --xz --file "$archive" --directory /usr/local --strip-components=1; \
    manager="$(node -p "require('/tmp/chubby-toolchain/package.json').packageManager")"; \
    case "$manager" in pnpm@*) ;; *) echo "Expected a pinned pnpm packageManager" >&2; exit 1 ;; esac; \
    npm install --global "$manager"; \
    test "$(node --version)" = "v${version}"; \
    test "$(pnpm --version)" = "${manager#pnpm@}"; \
    rm "$archive" SHASUMS256.txt .nvmrc package.json; \
    cd /tmp; \
    rmdir chubby-toolchain

USER vscode
