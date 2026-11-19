// tiqora_macro.sv — Tiqora as a plain-pin hard macro, for any chip.
//
// The Tiny Tapeout top (tt_um_normansrule_tiqora) packs the pins into the
// tile's ui/uo/uio buses. Every other tape-out target (a general sky130
// macro, Caravel, Openframe, gf180) starts from this module instead: the
// same tp_soc with the same parameters, with every signal on its own named
// pin. targets/README.md lists the targets; syn/targets/tapeout.py builds
// their configurations.
//
// Contract
//   - Identical behaviour to the Tiny Tapeout top, pin for pin, every clock:
//     test/tb_targets.sv runs both in lockstep (make targets).
//   - qspi_ctl_oe and qspi_sd_oe are 0 while rst_n is low, so an external
//     programmer can drive the flash through the same pins (the Tiny Tapeout
//     top does the same with uio_oe).
//   - No technology cells: the target's PDK and library come from its
//     target file (targets/*.toml).
//
// Cost: no logic beyond tp_soc except the reset gating of the six enables.
`default_nettype none

module tiqora_macro (
`ifdef USE_POWER_PINS
    inout  wire       vccd1,           // 1.8 V core supply (Caravel naming)
    inout  wire       vssd1,           // core ground
`endif
    input  wire       clk,
    input  wire       rst_n,
    // general-purpose pins: same meaning as Tiny Tapeout ui_in / uo_out
    input  wire [7:0] gpio_in,         // [3] UART RX, [7] boot select at reset
    output wire [7:0] gpio_out,        // [0] TRIG0 ... [4] UART TX (see tp_soc)
    // QSPI flash and two QSPI RAMs on one shared bus
    output wire       qspi_sck,
    output wire       qspi_cs_flash_n,
    output wire       qspi_cs_rama_n,
    output wire       qspi_cs_ramb_n,
    output wire       qspi_ctl_oe,     // drive sck and the three CS pins
    input  wire [3:0] qspi_sd_in,
    output wire [3:0] qspi_sd_out,
    output wire [3:0] qspi_sd_oe       // per data line, active high
);
    wire rst = ~rst_n;
    wire [3:0] sd_oe;

    tp_soc u_soc (
        .clk       (clk),
        .rst       (rst),
        .ui        (gpio_in),
        .uo        (gpio_out),
        .sck       (qspi_sck),
        .cs_flash_n(qspi_cs_flash_n),
        .cs_rama_n (qspi_cs_rama_n),
        .cs_ramb_n (qspi_cs_ramb_n),
        .sd_out    (qspi_sd_out),
        .sd_oe     (sd_oe),
        .sd_in     (qspi_sd_in)
    );

    assign qspi_ctl_oe = ~rst;
    assign qspi_sd_oe  = rst ? 4'h0 : sd_oe;
endmodule : tiqora_macro
