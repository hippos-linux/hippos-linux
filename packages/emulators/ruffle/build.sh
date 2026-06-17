#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='ruffle'
REPO='https://github.com/ruffle-rs/ruffle'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

mkdir -p "${STAGING}/bin"

cd "${SRC}"

export PATH="/root/.cargo/bin:${PATH}"

# openssl-sys uses pkg-config but the Debian default path isn't always inherited
# in cargo subprocess environments. OPENSSL_DIR bypasses pkg-config entirely.
export OPENSSL_DIR=/usr
export OPENSSL_INCLUDE_DIR=/usr/include
if [[ "${ARCH:-amd64}" == "arm64" ]]; then
    export AARCH64_UNKNOWN_LINUX_GNU_OPENSSL_DIR=/usr
    export AARCH64_UNKNOWN_LINUX_GNU_OPENSSL_LIB_DIR=/usr/lib/aarch64-linux-gnu
    export AARCH64_UNKNOWN_LINUX_GNU_OPENSSL_INCLUDE_DIR=/usr/include
else
    export OPENSSL_LIB_DIR=/usr/lib/x86_64-linux-gnu
fi

if ! command -v rustup >/dev/null 2>&1; then
    die "rustup not found"
fi

TOOLCHAIN='nightly'
if [[ -f rust-toolchain.toml ]]; then
    TOOLCHAIN="$(python3 - <<'PY'
import pathlib, tomllib
toolchain = tomllib.loads(pathlib.Path('rust-toolchain.toml').read_text()).get('toolchain', {})
print(toolchain.get('channel', 'nightly'))
PY
)"
fi

log "Using Rust toolchain: ${TOOLCHAIN}"
rustup toolchain install "${TOOLCHAIN}" --profile minimal
rustup override set "${TOOLCHAIN}"
rustc +"${TOOLCHAIN}" --version
cargo +"${TOOLCHAIN}" --version

if [[ "${ARCH:-amd64}" == "arm64" ]]; then
    rustup target add aarch64-unknown-linux-gnu --toolchain "${TOOLCHAIN}"
    cargo +"${TOOLCHAIN}" build --release --package ruffle_desktop \
        --target aarch64-unknown-linux-gnu
    cp "${SRC}/target/aarch64-unknown-linux-gnu/release/ruffle_desktop" "${STAGING}/bin/ruffle"
else
    cargo +"${TOOLCHAIN}" build --release --package ruffle_desktop
    cp "${SRC}/target/release/ruffle_desktop" "${STAGING}/bin/ruffle"
fi

if [[ ! -x "${STAGING}/bin/ruffle" ]]; then
    die "ruffle binary was not produced"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
