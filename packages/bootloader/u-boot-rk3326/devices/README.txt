These handhelds are recognised automatically and need nothing else, just boot: Odroid Go 2/3/Super, Anbernic RG351M/RG351V, Powkiddy RGB10, GameForce Chi and MagicX XU10.
The R36S and similar clones are recognised too, but also need the original card's .dtb in the stock folder for their screen (see stock/README.txt).

If yours is listed below instead, copy its file to the top of this partition and rename the copy to fdtfile.txt:
  r33s.txt       R33S
  eeclone.txt    EE clone
  xu-mini-m.txt  MagicX XU-Mini M
  g350.txt       BatleXP G350

If an EE clone's screen stays blank, also copy the .dtb from its original card into the stock folder.
