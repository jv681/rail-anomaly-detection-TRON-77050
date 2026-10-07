MEMORY { SRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 64K }
SECTIONS { .text : { *(.text) } > SRAM }