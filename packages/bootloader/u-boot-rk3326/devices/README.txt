Put this card in the handheld's first card slot. Games can stay on a card in the second slot.

Odroid Go 2/3/Super, Anbernic RG351M/RG351V, Powkiddy RGB10, GameForce Chi and MagicX XU10: nothing to do, just boot.

R36S and similar clones: before the first boot, copy the .dtb from the original card into the stock folder for the screen (see stock/README.txt).

If yours is listed below, copy its file to the top of this partition and rename the copy to fdtfile.txt:
  r33s.txt           R33S
  eeclone.txt        EE clone
  xu-mini-m.txt      MagicX XU-Mini M
  g350.txt           BatleXP G350
  xifan-dc35v.txt    XiFan DC35V
  xifan-dc40v.txt    XiFan DC40V
  xifan-dc45v.txt    XiFan DC45V
  xifan-mini40.txt   XiFan Mini40
  xifan-mymini.txt   XiFan MyMini
  xifan-r36max.txt   XiFan R36 Max
  xifan-r36max2.txt  XiFan R36 Max2
  xifan-r36pro.txt   XiFan R36 Pro
  xifan-rf35h.txt    XiFan RF35H
  xifan-rf40h.txt    XiFan RF40H
  xifan-rf45v.txt    XiFan RF45V
  xifan-xf28.txt     XiFan XF28
  xifan-xf35h.txt    XiFan XF35H
  xifan-xf40h.txt    XiFan XF40H
  xifan-xf40v.txt    XiFan XF40V
  xifan-xf45v.txt    XiFan XF45V

If an EE clone's screen stays blank, also copy the .dtb from its original card into the stock folder.
If the screen still stays blank, ask in #rk3326 on the HippOS Discord (hippos-linux.org/discord) and say which handheld you have.
