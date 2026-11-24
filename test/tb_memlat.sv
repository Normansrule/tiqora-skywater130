// tb_memlat.sv — how long each load or store keeps the core in S_MEM.
//
// The core goes from S_MEM straight back to S_PASS only if the memory
// answers exactly as its 3-bit phase comes round to 7, which means a stay
// of a multiple of 8 clocks (S_MEM is entered on phase 0). This bench runs a
// program (+PROG=, RTL only) and prints one line per stay:
//     MEMLAT <clocks> <next state>
// test/memlat.py runs it over many random programs (sw/mkrandmem.py).
`default_nettype none
`timescale 1ns/1ps

module tb_memlat;
    reg        clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg  [7:0] ui_in = 8'h00;
    wire [7:0] uo_out, uio_out, uio_oe;
    always #5 clk = ~clk;

    wire sck = uio_out[3], cs_f = uio_out[0], cs_r = uio_out[6];
    wire [3:0] flash_sd, psram_sd;
    wire [3:0] sd_bus = uio_oe[1] ? {uio_out[5], uio_out[4], uio_out[2], uio_out[1]}
                      : (!cs_f ? flash_sd : (!cs_r ? psram_sd : 4'hF));
    wire [7:0] uio_in = {2'b00, sd_bus[3], sd_bus[2], 1'b0, sd_bus[1], sd_bus[0], 1'b0};

    tt_um_normansrule_tiqora dut (.ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in), .uio_out(uio_out),
                                  .uio_oe(uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n));
    qspi_flash_model #(.DUMMY(4), .WORDS(4096)) u_flash (.cs_n(cs_f), .sck(sck),
        .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) u_psram (.cs_n(cs_r), .sck(sck),
        .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    wire [2:0] state = dut.u_soc.g_cpu.u_core.state;
    reg [1023:0] prog;
    integer n, cyc, phase0_bad;

    initial begin
        if (!$value$plusargs("PROG=%s", prog)) prog = "prog.hex";
        #1 $readmemh(prog, u_flash.mem);
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        n = 0; phase0_bad = 0;
        for (cyc = 0; cyc < 400000 && !uo_out[5]; cyc = cyc + 1) begin
            @(negedge clk);
            if (state === 3'd5) begin
                if (n == 0 && dut.u_soc.g_cpu.u_core.phase !== 3'd0) phase0_bad = phase0_bad + 1;
                n = n + 1;
            end else if (n != 0) begin
                $display("MEMLAT %0d %0d", n, state);
                n = 0;
            end
        end
        if (phase0_bad != 0) $display("FAIL %0d stays in S_MEM did not start on phase 0", phase0_bad);
        if (!uo_out[5]) $display("FAIL program did not halt");
        if (phase0_bad == 0 && uo_out[5]) $display("MEMLAT PASSED");
        $finish;
    end
endmodule
