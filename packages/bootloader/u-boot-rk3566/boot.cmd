# To force a device tree, put its file name in fdtfile.txt as: fdtfile=rk3566-<board>.dtb
# A MiniLoong Pocket 1 needs fdtfile=rk3566-miniloong.dtb there, a Powkiddy X55 fdtfile=rk3566-powkiddy-x55.dtb.

setenv bootpart "${devtype} ${devnum}:${distro_bootpart}"
setexpr fdtfile sub "^rockchip/" "" "${fdtfile}"

if test -e ${bootpart} fdtfile.txt; then
    load ${bootpart} ${pxefile_addr_r} fdtfile.txt
    env import -t ${pxefile_addr_r} ${filesize} fdtfile
fi

setenv bootdir current
if test -e ${bootpart} hippos-tryboot.json; then
    if test -e ${bootpart} tryboot.used; then
        echo "Previous try of the update did not finish booting; starting the current system"
    else
        mw.b ${pxefile_addr_r} 0x31 1
        fatwrite ${bootpart} ${pxefile_addr_r} tryboot.used 1
        setenv bootdir try
    fi
fi
echo "Booting ${bootdir}/ with ${fdtfile} (${board_name})"

load ${bootpart} ${pxefile_addr_r} ${bootdir}/boot.env
env import -t ${pxefile_addr_r} ${filesize} bootargs

load ${bootpart} ${kernel_addr_r} ${bootdir}/vmlinuz
load ${bootpart} ${ramdisk_addr_r} ${bootdir}/initrd.img
setenv ramdisk_size ${filesize}
load ${bootpart} ${fdt_addr_r} ${bootdir}/dtbs/${fdtfile}

booti ${kernel_addr_r} ${ramdisk_addr_r}:${ramdisk_size} ${fdt_addr_r}
