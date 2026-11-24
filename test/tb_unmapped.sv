// tb_unmapped.sv — loads, stores and a jump into address space nothing answers.
//
// The data bus decodes flash, PSRAM, the timing unit and the peripherals.
// Before tp_bus.sv answered the rest, one stray pointer was enough to stop
// the chip: a load or store to the boot ROM (fetch-only) or to 0x5..0xF
// waited for a reply that never came, with no pin to say why. Found
// 2026-11-24 while writing a program to cover the core's state diagram.
//
// Now a data access there completes in one clock, reads 0 and drops writes,
// and a fetch there reads 0x00000000, an illegal instruction, so ILLEGAL
// rises. sw/mkunmapped.py documents the program and its result slots.
//
// Run with:  make unmapped
`default_nettype none
`timescale 1ns/1ps

module tb_unmapped;

    localparam int TIMEOUT = 40000;

    reg        clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg  [7:0] ui_in = 8'h00;
    wire [7:0] uo_out, uio_out, uio_oe;

    integer errors = 0, checks = 0;

    task chk(input cond, input string name);
        begin
            checks = checks + 1;
            if (!cond) begin
                errors = errors + 1;
                $display("  FAIL  %0s", name);
            end else
                $display("  ok    %0s", name);
        end
    endtask

    always #5 clk = ~clk;

    wire sck  = uio_out[3];
    wire cs_f = uio_out[0];
    wire cs_r = uio_out[6];

    wire [3:0] flash_sd, psram_sd;
    wire [3:0] sd_bus = uio_oe[1] ? {uio_out[5], uio_out[4], uio_out[2], uio_out[1]}
                      : (!cs_f ? flash_sd : (!cs_r ? psram_sd : 4'hF));
    wire [7:0] uio_in = {2'b00, sd_bus[3], sd_bus[2], 1'b0, sd_bus[1], sd_bus[0], 1'b0};

    tt_um_normansrule_tiqora dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    qspi_flash_model #(.DUMMY(4), .WORDS(512)) u_flash (
        .cs_n(cs_f), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) u_psram (
        .cs_n(cs_r), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    wire        illegal = dut.u_soc.g_cpu.u_core.illegal;
    wire [2:0]  state   = dut.u_soc.g_cpu.u_core.state;

    function automatic [31:0] slot(input integer n);
        slot = {u_psram.mem[4*n+3], u_psram.mem[4*n+2], u_psram.mem[4*n+1], u_psram.mem[4*n]};
    endfunction

    integer cyc, in_mem, longest_mem;

    initial begin
        #1 $readmemh("unmapped.hex", u_flash.mem);
        $display("\n=== Tiqora unmapped-address test ===");
        repeat (20) @(posedge clk);
        rst_n = 1'b1;

        // run until ILLEGAL rises, timing the longest stay in S_MEM
        cyc = 0; in_mem = 0; longest_mem = 0;
        while (!illegal && cyc < TIMEOUT) begin
            @(posedge clk);
            cyc = cyc + 1;
            in_mem = (state === 3'd5) ? in_mem + 1 : 0;
            if (in_mem > longest_mem) longest_mem = in_mem;
        end
        repeat (10) @(posedge clk);

        $display("  slots: %08x %08x %08x %08x %08x", slot(0), slot(1), slot(2), slot(3), slot(4));
        $display("  longest load or store: %0d clocks; ILLEGAL after %0d clocks", longest_mem, cyc);

        chk(cyc < TIMEOUT, "the core did not hang: ILLEGAL rose after the jump into unmapped space");
        chk(longest_mem < 100, "no load or store waited more than 100 clocks");
        chk(slot(0) === 32'h0, "load from the boot ROM (no data port) reads 0");
        chk(slot(1) === 32'h0, "load from unmapped 0x50000000 reads 0, the store before it was dropped");
        chk(slot(2) === 32'h0, "load from unmapped 0xF0000004 reads 0");
        chk(slot(3) === 32'h0, "byte load from unmapped 0x7000000B reads 0");
        chk(slot(4) === 32'h60D, "the program carried on past every unmapped access");
        chk(uo_out[6] === 1'b1, "ILLEGAL pin (uo[6]) is high");

        $display("\n%0d checks, %0d failures", checks, errors);
        if (errors == 0) $display("UNMAPPED TEST PASSED\n");
        else             $display("UNMAPPED TEST FAILED\n");
        $finish;
    end

endmodule
