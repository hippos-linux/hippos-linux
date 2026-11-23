set_cpu_governor() {
    local gov="$1" policy tunable value path
    for policy in /sys/devices/system/cpu/cpufreq/policy*; do
        [[ -f "${policy}/scaling_governor" ]] || continue
        [[ "$(cat "${policy}/scaling_governor")" == "${gov}" ]] || printf '%s' "${gov}" > "${policy}/scaling_governor" 2>/dev/null || true
    done
    [[ "${gov}" == ondemand ]] || return 0
    for tunable in up_threshold sampling_down_factor; do
        value="$(hippos-settings get "system.cpu.ondemand.${tunable}" 2>/dev/null || true)"
        [[ -n "${value}" ]] || continue
        for path in /sys/devices/system/cpu/cpufreq/ondemand/"${tunable}" /sys/devices/system/cpu/cpufreq/policy*/ondemand/"${tunable}"; do
            [[ -f "${path}" ]] && printf '%s' "${value}" > "${path}"
        done
    done
    return 0
}

set_devfreq_governor() {
    local gov="$1" device
    for device in /sys/class/devfreq/*; do
        [[ -f "${device}/governor" ]] || continue
        grep -qw "${gov}" "${device}/available_governors" 2>/dev/null || continue
        [[ "$(cat "${device}/governor")" == "${gov}" ]] || printf '%s' "${gov}" > "${device}/governor"
    done
    return 0
}
