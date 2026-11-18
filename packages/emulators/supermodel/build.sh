#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel'
REPO='https://github.com/trzy/Supermodel'
REF="${SUPERMODEL_REF:-master}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

source "/work/packages/emulators/supermodel/supermodel-family.sh"

clone_source "${REPO}" "${REF}" "${SRC}"
[[ -f "${SRC}/Makefiles/Makefile.UNIX" ]] || die "Makefiles/Makefile.UNIX not found; Supermodel source layout changed"

supermodel_build
supermodel_stage "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
