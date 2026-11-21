#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='duckstation'
REPO='https://github.com/duckstation/old-releases.git'
REF="${DUCKSTATION_REF:-v0.1-7371}"

WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${REF}" "${SRC}" --submodules

sed -i -e 's/^find_package(Qt6 6.7.2 COMPONENTS Core Gui Widgets LinguistTools REQUIRED)$/find_package(Qt6 6.7.2 COMPONENTS Core Gui GuiPrivate Widgets LinguistTools REQUIRED)/' \
       -e 's/ Qt6::Core Qt6::Gui Qt6::Widgets)$/ Qt6::Core Qt6::Gui Qt6::GuiPrivate Qt6::Widgets)/' \
    "${SRC}/src/duckstation-qt/CMakeLists.txt"
grep -q 'Qt6::GuiPrivate Qt6::Widgets' "${SRC}/src/duckstation-qt/CMakeLists.txt" || die "Qt GuiPrivate link edit did not apply"
sed -i 's/const bool visible = force_visible || !hide_window || !has_window;/const bool visible = force_visible || !hide_window || (!has_window \&\& !QtHost::InNoGUIMode());/' \
    "${SRC}/src/duckstation-qt/mainwindow.cpp"
grep -q '!has_window && !QtHost::InNoGUIMode()' "${SRC}/src/duckstation-qt/mainwindow.cpp" || die "nogui main window edit did not apply"

BUILT_BIN='duckstation-qt'
STAGED_BIN='duckstation'
VERSION="${REF}"
DOC_FILES=(LICENSE)
source "/work/packages/emulators/duckstation/duckstation-family.sh"
