// Unlock binary: Clear MX66UW1G45G BP bits via XSPI2 SPI indirect mode
// Assemble with: arm-none-eabi-gcc -mcpu=cortex-m55 -mthumb -O0 -nostdlib -o unlock.elf unlock.c
// objcopy -O binary unlock.elf unlock.bin
// Load to 0x20000000 and execute

#define XSPI2_BASE  0x52006000UL
#define XSPI_CR     (*(volatile unsigned int*)(XSPI2_BASE + 0x000))
#define XSPI_DCR1   (*(volatile unsigned int*)(XSPI2_BASE + 0x008))
#define XSPI_SR     (*(volatile unsigned int*)(XSPI2_BASE + 0x020))
#define XSPI_FCR    (*(volatile unsigned int*)(XSPI2_BASE + 0x024))
#define XSPI_DLR    (*(volatile unsigned int*)(XSPI2_BASE + 0x040))
#define XSPI_DR     (*(volatile unsigned int*)(XSPI2_BASE + 0x050))
#define XSPI_CCR    (*(volatile unsigned int*)(XSPI2_BASE + 0x100))
#define XSPI_TCR    (*(volatile unsigned int*)(XSPI2_BASE + 0x108))
#define XSPI_IR     (*(volatile unsigned int*)(XSPI2_BASE + 0x110))

/* CCR field: IMODE=001 (1-line), ADMODE=000, DMODE=0001 (1-line) shifted to [27:24] */
#define CCR_INSTR_ONLY  0x00000001UL   /* IMODE=1 line, no addr, no data */
#define CCR_INSTR_DATA  0x01000001UL   /* IMODE=1 line, no addr, DMODE=1 line */

static void xspi_wait_tc(void) {
    while (!(XSPI_SR & 0x02)) {}   /* Wait for TCF (Transfer Complete Flag) */
    XSPI_FCR = 0x02;               /* Clear TCF */
}

void unlock(void) {
    /* Enable XSPI2 clock via RCC - skip for now, assume ROM left it enabled */
    /* Ensure indirect write mode (FMODE=00 in CR bits [29:28]) */
    XSPI_CR &= ~(3u << 28);  /* FMODE = 00 = indirect write */

    /* WREN (0x06): 1-byte instruction, no address, no data */
    XSPI_FCR = 0x1F;           /* Clear all flags */
    XSPI_CCR = CCR_INSTR_ONLY;
    XSPI_TCR = 0;
    XSPI_IR  = 0x06;           /* WREN opcode */
    xspi_wait_tc();

    /* WRR (0x01): 1-byte instruction, no address, 1-byte data = 0x00 (clear all BP bits) */
    XSPI_FCR = 0x1F;
    XSPI_DLR = 0;              /* DLR=0 means 1 byte of data */
    XSPI_CCR = CCR_INSTR_DATA;
    XSPI_TCR = 0;
    XSPI_IR  = 0x01;           /* WRR opcode */
    XSPI_DR  = 0x00;           /* SR1 = 0x00 (all BP bits cleared) */
    xspi_wait_tc();

    /* Also try GBULK (Global Block Unlock, 0x98) - no WEN needed */
    XSPI_FCR = 0x1F;
    XSPI_CCR = CCR_INSTR_ONLY;
    XSPI_IR  = 0x98;           /* GBULK opcode */
    xspi_wait_tc();

    /* Spin here so programmer knows we're done */
    while (1) {}
}