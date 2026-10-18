// tp_simd.sv — GPU mode: four independent byte lanes, one result per clock.
//
// Contract
//   y = op(a, b) applied to each byte lane i (bits 8i+7..8i) on its own;
//   no carry, borrow or saturation crosses a lane boundary. Purely
//   combinational: the core presents rs1/rs2 for one clock (its XP state)
//   and captures y on that clock.
//
//   op (funct3 of custom-2)       per lane, unsigned bytes
//   000 PADD.B    a + b            mod 256
//   001 PSUB.B    a - b            mod 256
//   010 PADDUS.B  a + b            saturates at 255
//   011 PMAXU.B   max(a, b)
//   100 PMINU.B   min(a, b)
//   101 PAVGU.B   (a + b + 1) >> 1 rounds half up, 9-bit sum, no overflow
//   110 PMUL.B    a * b            low 8 bits
//   111 PABSD.B   |a - b|
//
// "GPU" here means the packed-pixel arithmetic a shader core does on 8-bit
// colour channels, four channels per instruction. It is not a graphics
// pipeline. Built only when tp_ncore's MODES = 1 (FPGA and full sky130);
// the Tiny Tapeout tile does not contain it.
// Cost: see docs/MODES.md (measured with Yosys, generic gates and sky130).
`default_nettype none

module tp_simd (
    input  wire  logic [2:0]  op,
    input  wire  logic [31:0] a,
    input  wire  logic [31:0] b,
    output logic       [31:0] y
);
    always_comb begin
        for (int i = 0; i < 4; i++) begin
            logic [7:0] x, z, d;
            logic [8:0] s;
            logic [7:0] p;
            x = a[8*i +: 8];
            z = b[8*i +: 8];
            s = {1'b0, x} + {1'b0, z};
            d = x - z;
            p = 8'(x * z);                // the low byte is all PMUL.B keeps
            unique case (op)
                tp_pkg::GF3_ADD:  y[8*i +: 8] = s[7:0];
                tp_pkg::GF3_SUB:  y[8*i +: 8] = d;
                tp_pkg::GF3_ADDS: y[8*i +: 8] = s[8] ? 8'hFF : s[7:0];
                tp_pkg::GF3_MAX:  y[8*i +: 8] = (x > z) ? x : z;
                tp_pkg::GF3_MIN:  y[8*i +: 8] = (x < z) ? x : z;
                tp_pkg::GF3_AVG:  y[8*i +: 8] = 8'((s + 9'd1) >> 1);
                tp_pkg::GF3_MUL:  y[8*i +: 8] = p;
                tp_pkg::GF3_ABSD: y[8*i +: 8] = (x > z) ? d : 8'(z - x);
                default:          y[8*i +: 8] = 8'd0;
            endcase
        end
    end
endmodule : tp_simd
