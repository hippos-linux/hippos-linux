# To use a different panel, copy its overlay to overlays/mipi-panel.dtbo on this partition.
# To force a device tree, put its file name in fdtfile.txt as: fdtfile=rk3326-<board>.dtb

setenv bootpart "mmc 1:1"
setenv fdt_addr_r 0x01f00000
setenv fdtoverlay_addr_r 0x01e00000
setenv kernel_addr_r 0x02080000
setenv ramdisk_addr_r 0x0a000000
setenv kernel_comp_addr_r 0x10000000

if   test "${hwrev}" = "v10-go3"; then setenv fdtfile rk3326-odroid-go3.dtb
elif test "${hwrev}" = "r33s";    then setenv fdtfile rk3326-gameconsole-r33s.dtb
elif test "${hwrev}" = "chi";     then setenv fdtfile rk3326-gameforce-chi.dtb
elif test "${hwrev}" = "rg351v";  then setenv fdtfile rk3326-anbernic-rg351v.dtb
elif test "${hwrev}" = "xu10";    then setenv fdtfile rk3326-magicx-xu10.dtb
elif test "${hwrev}" = "v11"; then
    if gpio input c22; then
        if gpio input d9; then setenv fdtfile rk3326-powkiddy-rgb10.dtb
        else                   setenv fdtfile rk3326-odroid-go2-v11.dtb
        fi
    else
        setenv fdtfile rk3326-anbernic-rg351m.dtb
    fi
else
    setenv fdtfile rk3326-odroid-go2.dtb
fi

if test -e ${bootpart} fdtfile.txt; then
    load ${bootpart} ${loadaddr} fdtfile.txt
    env import -t ${loadaddr} ${filesize} fdtfile
fi

setenv bootdir current
if test -e ${bootpart} hippos-tryboot.json; then
    if test -e ${bootpart} tryboot.used; then
        echo "Previous try of the update did not finish booting; starting the current system"
    else
        mw.b ${loadaddr} 0x31 1
        fatwrite mmc 1:1 ${loadaddr} tryboot.used 1
        setenv bootdir try
    fi
fi
echo "Booting ${bootdir}/ with ${fdtfile} (hwrev ${hwrev})"

load ${bootpart} ${loadaddr} ${bootdir}/boot.env
env import -t ${loadaddr} ${filesize} bootargs

load ${bootpart} ${kernel_comp_addr_r} ${bootdir}/vmlinuz
unzip ${kernel_comp_addr_r} ${kernel_addr_r}
load ${bootpart} ${ramdisk_addr_r} ${bootdir}/initrd.img
setenv ramdisk_size ${filesize}
load ${bootpart} ${fdt_addr_r} ${bootdir}/dtbs/${fdtfile}
fdt addr ${fdt_addr_r}
fdt resize 65536
if test -e ${bootpart} overlays/mipi-panel.dtbo; then
    load ${bootpart} ${fdtoverlay_addr_r} overlays/mipi-panel.dtbo
    fdt apply ${fdtoverlay_addr_r}
fi

setenv bootargs "${bootargs} hippos.hwrev=${hwrev}"
booti ${kernel_addr_r} ${ramdisk_addr_r}:${ramdisk_size} ${fdt_addr_r}
