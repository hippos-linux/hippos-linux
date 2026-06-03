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

cargo +"${TOOLCHAIN}" build --release --package ruffle_desktop

cp "${SRC}/target/release/ruffle_desktop" "${STAGING}/bin/ruffle"

if [[ ! -x "${STAGING}/bin/ruffle" ]]; then
    die "ruffle binary was not produced"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
