// basys3_top.sv — Tiqora on a Digilent Basys 3 (Artix-7 XC7A35T).
//
// The same RTL that goes to silicon (src/), unchanged, with the board as its
// demo board:
//   clock      100 MHz oscillator divided by 2 -> 50 MHz, the chip's target
//   reset      btnC (and a power-on reset)
//   ui_in      sw[2:0] read latency (sampled in reset; 000 for the emulator)
//              RsRx    UART RX: the board's own USB serial port
//              btnL/btnR/btnU (or sw4..6)  capture inputs 4..6
//              sw[7]   BOOT: up while pressing btnC runs the UART bootloader
//   uo_out     LEDs 0..7 (TRIG0, TRIG1, EVT, OVF, UART TX, HALT, ILLEGAL,
//              HEARTBEAT); uo_out[4] is also RsTx, the USB serial port
//   uio        USE_PMOD = 0: the QSPI memory emulated in block RAM (qspi_emu)
//              USE_PMOD = 1: the real Tiny Tapeout QSPI Pmod on port JA
//   LEDs 8..15 memory activity: flash, RAM A, RAM B selected; reset released
//   7-segment  uo_out and ui_in in hex
`default_nettype none
module basys3_top #(
    parameter bit    USE_PMOD   = 1'b0,
    parameter        FLASH_INIT = "flash.mem"
) (
    input  wire logic        clk,          // 100 MHz
    input  wire logic        btnC, btnL, btnR, btnU,
    input  wire logic [15:0] sw,
    output logic      [15:0] led,
    output logic      [6:0]  seg,
    output logic             dp,
    output logic      [3:0]  an,
    input  wire logic        RsRx,
    output logic             RsTx,
    inout  wire logic [7:0]  JA
);
    // ---- 50 MHz ----
    logic clk_div = 1'b0, clk50;
    always_ff @(posedge clk) clk_div <= ~clk_div;
`ifdef SYNTHESIS
    BUFG u_bufg (.I(clk_div), .O(clk50));
`else
    assign clk50 = clk_div;
`endif

    // ---- reset: power-on, then btnC ----
    logic [3:0] btn_sync = 4'hF;
    logic [7:0] por = 8'd0;
    always_ff @(posedge clk50) begin
        btn_sync <= {btn_sync[2:0], btnC};
        if (por != 8'hFF) por <= por + 8'd1;
    end
    wire rst_n = (por == 8'hFF) && !btn_sync[3];

    // ---- the chip ----
    logic [7:0] ui_in, uo_out, uio_in, uio_out, uio_oe;
    assign ui_in = {sw[7], sw[6] | btnU, sw[5] | btnR, sw[4] | btnL, RsRx, sw[2:0]};

    tt_um_normansrule_tiqora u_chip (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(1'b1), .clk(clk50), .rst_n(rst_n));

    // ---- memory: emulated, or the real Pmod on JA ----
    // TT QSPI Pmod: uio[0] CS0 flash, [1] SD0, [2] SD1, [3] SCK, [4] SD2, [5] SD3, [6] CS1 RAM A, [7] CS2 RAM B
    wire cs_f = uio_oe[0] ? uio_out[0] : 1'b1;      // released in reset: deselected
    wire cs_a = uio_oe[6] ? uio_out[6] : 1'b1;
    wire cs_b = uio_oe[7] ? uio_out[7] : 1'b1;
    generate if (USE_PMOD) begin : g_pmod
        for (genvar k = 0; k < 8; k++) begin : g_io
            assign JA[k]     = uio_oe[k] ? uio_out[k] : 1'bz;
            assign uio_in[k] = JA[k];
        end
    end else begin : g_emu
        logic [3:0] emu_sd;
        logic       emu_drive;
        qspi_emu #(.FLASH_INIT(FLASH_INIT)) u_mem (
            .clk(clk50), .cs_flash_n(cs_f), .cs_rama_n(cs_a), .cs_ramb_n(cs_b), .sck(uio_out[3]),
            .sd_from_ctrl({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}),
            .sd_to_ctrl(emu_sd), .sd_drive(emu_drive));
        // what the chip's bidirectional pins would see on the board
        wire [3:0] bus = emu_drive ? emu_sd : {uio_out[5], uio_out[4], uio_out[2], uio_out[1]};
        assign uio_in = {uio_out[7:6], bus[3], bus[2], uio_out[3], bus[1], bus[0], uio_out[0]};
        assign JA = 8'bz;
    end endgenerate

    // ---- board outputs ----
    assign RsTx = uo_out[4];
    assign led  = {rst_n, 4'b0, !cs_b, !cs_a, !cs_f, uo_out};

    logic [16:0] scan = 17'd0;
    always_ff @(posedge clk50) scan <= scan + 17'd1;
    wire  [1:0]  digit = scan[16:15];
    logic [3:0]  hex;
    always_comb begin
        unique case (digit)
            2'd0: hex = ui_in[3:0];
            2'd1: hex = ui_in[7:4];
            2'd2: hex = uo_out[3:0];
            default: hex = uo_out[7:4];
        endcase
        an = ~(4'b0001 << digit);
        unique case (hex)                      // segments g..a, active low
            4'h0: seg = 7'b1000000; 4'h1: seg = 7'b1111001; 4'h2: seg = 7'b0100100; 4'h3: seg = 7'b0110000;
            4'h4: seg = 7'b0011001; 4'h5: seg = 7'b0010010; 4'h6: seg = 7'b0000010; 4'h7: seg = 7'b1111000;
            4'h8: seg = 7'b0000000; 4'h9: seg = 7'b0010000; 4'hA: seg = 7'b0001000; 4'hB: seg = 7'b0000011;
            4'hC: seg = 7'b1000110; 4'hD: seg = 7'b0100001; 4'hE: seg = 7'b0000110; default: seg = 7'b0001110;
        endcase
    end
    assign dp = ~(digit == 2'd2);              // the dot separates outputs from inputs
endmodule
