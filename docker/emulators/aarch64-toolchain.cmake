# CMake toolchain for cross-compiling to aarch64 from an amd64 Debian host.
# Relies on Debian multiarch layout: arm64 packages in /usr/lib/aarch64-linux-gnu.

set(CMAKE_SYSTEM_NAME      Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(CMAKE_C_COMPILER   aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_AR           aarch64-linux-gnu-ar    CACHE FILEPATH "")
set(CMAKE_RANLIB       aarch64-linux-gnu-ranlib CACHE FILEPATH "")
set(CMAKE_STRIP        aarch64-linux-gnu-strip  CACHE FILEPATH "")

# Clang target triple — emulators that explicitly use clang will auto-add
# --target=aarch64-linux-gnu without any per-script change.
set(CMAKE_C_COMPILER_TARGET   aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)

# Debian multiarch: cmake resolves find_library() via the library architecture
# suffix, i.e. /usr/lib/aarch64-linux-gnu.
set(CMAKE_LIBRARY_ARCHITECTURE aarch64-linux-gnu)

set(CMAKE_FIND_ROOT_PATH /)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)

# Qt cross-compilation: moc/rcc/uic must run on the build host (amd64).
# When a matching arm64 Qt6 11 build is mounted at /opt/hippos/qt/6.11 we use
# it alongside the amd64 host tools — same version, no mismatch.
# Without the arm64 build, fall back to the system Qt6 (6.8.x) for both target
# and host; qt6-base-dev (amd64) must be installed to provide host cmake files.
if(IS_DIRECTORY /opt/hippos/qt/6.11-host)
    if(IS_DIRECTORY /opt/hippos/qt/6.11)
        list(PREPEND CMAKE_PREFIX_PATH /opt/hippos/qt/6.11)
        set(QT_HOST_PATH /opt/hippos/qt/6.11-host)
        set(QT_HOST_PATH_CMAKE_DIR /opt/hippos/qt/6.11-host/lib/cmake)
    else()
        set(QT_HOST_PATH /usr)
        set(QT_HOST_PATH_CMAKE_DIR /usr/lib/x86_64-linux-gnu/cmake)
    endif()
endif()

# pkg-config: override the search path so the native binary finds arm64 .pc files.
set(ENV{PKG_CONFIG_LIBDIR}      /usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig)
set(ENV{PKG_CONFIG_PATH}        /usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig)
set(ENV{PKG_CONFIG_SYSROOT_DIR} /)
