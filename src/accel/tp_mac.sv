// tp_mac.sv — TPU mode: an int8 dot-product multiply-accumulate unit.
//
// Contract
//   One 32-bit accumulator `acc`, reset to 0. On a clock with en = 1:
//     op 000 TMAC  acc <= acc + sum over lanes i of signed(a.byte i) * signed(b.byte i)
//     op 011 TCLR  acc <= 0
//     op 100 TSET  acc <= a
//     anything else leaves acc alone
//   y is combinational from acc: op 010 (TRELU) gives max(acc, 0) as a
//   signed number, every other op gives acc (TRD). Addition wraps mod 2^32.
//
// A tensor processor's inner loop is exactly this: four int8 weights times
// four int8 activations, summed into a wide accumulator, then a ReLU. One
// TMAC is four multiply-accumulates. Built only when tp_ncore's MODES = 1;
// the Tiny Tapeout tile does not contain it.
// Cost: see docs/MODES.md.
`default_nettype none

module tp_mac (
    input  wire  logic        clk,
    input  wire  logic        rst,
    input  wire  logic        en,
    input  wire  logic [2:0]  op,
    input  wire  logic [31:0] a,
    input  wire  logic [31:0] b,
    output logic       [31:0] y
);
    logic [31:0] acc;
    logic [31:0] dot;

    always_comb begin
        dot = 32'd0;
        for (int i = 0; i < 4; i++)
            dot = dot + 32'($signed(a[8*i +: 8]) * $signed(b[8*i +: 8]));
    end

    always_ff @(posedge clk) begin
        if (rst) acc <= 32'd0;
        else if (en) begin
            unique case (op)
                tp_pkg::UF3_MAC: acc <= acc + dot;
                tp_pkg::UF3_CLR: acc <= 32'd0;
                tp_pkg::UF3_SET: acc <= a;
                default: acc <= acc;
            endcase
        end
    end

    assign y = (op == tp_pkg::UF3_RELU && acc[31]) ? 32'd0 : acc;
endmodule : tp_mac
