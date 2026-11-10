LIBRETRO_CORE_ALIASES: dict[str, tuple[str, ...]] = {
    'beetle-saturn': ('mednafen_saturn',),
    'bsnes_hd': ('bsnes_hd_beta',),
    'genesis_plus_gx-wide': ('genesis_plus_gx_wide',),
    'mame078plus': ('mame2003_plus',),
    'pce': ('mednafen_pce',),
    'pce_fast': ('mednafen_pce_fast',),
    'pcfx': ('mednafen_pcfx',),
    'vb': ('mednafen_vb',),
    'vba-m': ('vbam',),
}

def core_file_names(core: str) -> tuple[str, ...]:
    return tuple(f'{name}_libretro.so' for name in (core, *LIBRETRO_CORE_ALIASES.get(core, ())))
