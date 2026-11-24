// tb_lockstep.sv — the RTL and its sky130 gate netlist, side by side, clock by clock.
//
// Two copies of the chip run the same program from two identical flash and
// RAM models, with the same input pins. One is the RTL (src/*.sv). The other
// is the gate netlist the views page draws (docs/views/netlist.json, turned
// back into Verilog by test/views/netlist_v.py with every module renamed G_*;
// its cells are modelled from the liberty functions that views_switch.py has
// checked against the transistors).
//
// Every clock, all 24 output and output-enable pins must match. Any
// difference is a failure, reported with the clock it happened on.
//
// It also writes, every clock, each state machine's RTL state before and after
// and the gate side's one-hot flip-flops to +FSMLOG=, so test/views/fsm_check.py
// can check each step against the state diagram and the encoding.
//
//   +PROG=<hex for flash>  +CYCLES=<n>  +SEED=<n>  +FSMLOG=<file>  +BOOT (start in the ROM)
//   +RESETS (also pull rst_n low for 3 clocks at random moments, about once
//   every 4,096 clocks, so the reset transition out of busy states is taken)
//   +RESETHUNT (pull rst_n low for 3 clocks, at most once per 1,024, while a state
//   lasts only a few clocks: the core's S_SHIFT and qspi_ctrl's Q_PREFIX,
//   Q_END and Q_DESEL; every other one waits for Q_END, the rarest. Random
//   resets almost never land in them, so their reset arrows went untaken.)
`default_nettype none
`timescale 1ns/1ps

module tb_lockstep;
    reg clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg [7:0] ui_in = 8'h00;
    always #5 clk = ~clk;

    // ---------------- one chip + its memories, twice ----------------
    wire [7:0] r_uo, r_uio_out, r_uio_oe, r_uio_in;
    wire [7:0] g_uo, g_uio_out, g_uio_oe, g_uio_in;
    wire [3:0] r_fsd, r_psd, g_fsd, g_psd;

    `define BUS(P) \
        wire [3:0] P``_sd = P``_uio_oe[1] ? {P``_uio_out[5], P``_uio_out[4], P``_uio_out[2], P``_uio_out[1]} \
                          : (!P``_uio_out[0] ? P``_fsd : (!P``_uio_out[6] ? P``_psd : 4'hF)); \
        assign P``_uio_in = {2'b00, P``_sd[3], P``_sd[2], 1'b0, P``_sd[1], P``_sd[0], 1'b0};
    `BUS(r)
    `BUS(g)

    tt_um_normansrule_tiqora r (.ui_in(ui_in), .uo_out(r_uo), .uio_in(r_uio_in), .uio_out(r_uio_out),
                                .uio_oe(r_uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n));
    G_tt_um_normansrule_tiqora g (.ui_in(ui_in), .uo_out(g_uo), .uio_in(g_uio_in), .uio_out(g_uio_out),
                                  .uio_oe(g_uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n));

    qspi_flash_model #(.DUMMY(4), .WORDS(4096)) r_flash (.cs_n(r_uio_out[0]), .sck(r_uio_out[3]),
        .ctrl_sd({r_uio_out[5], r_uio_out[4], r_uio_out[2], r_uio_out[1]}), .dev_sd(r_fsd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) r_psram (.cs_n(r_uio_out[6]), .sck(r_uio_out[3]),
        .ctrl_sd({r_uio_out[5], r_uio_out[4], r_uio_out[2], r_uio_out[1]}), .dev_sd(r_psd));
    qspi_flash_model #(.DUMMY(4), .WORDS(4096)) g_flash (.cs_n(g_uio_out[0]), .sck(g_uio_out[3]),
        .ctrl_sd({g_uio_out[5], g_uio_out[4], g_uio_out[2], g_uio_out[1]}), .dev_sd(g_fsd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) g_psram (.cs_n(g_uio_out[6]), .sck(g_uio_out[3]),
        .ctrl_sd({g_uio_out[5], g_uio_out[4], g_uio_out[2], g_uio_out[1]}), .dev_sd(g_psd));

    // ---------------- the two state machines, on both sides ----------------
    wire [2:0] r_core = r.u_soc.g_cpu.u_core.state;
    wire [3:0] r_qspi = r.u_soc.u_qspi.state;
    // synthesis re-encoded both state machines one-hot (Yosys fsm_recode):
    // the gate side holds 8 and 9 flip-flops, one per state. fsm_check.py
    // checks every clock that the hot one is the RTL state's.
    wire [7:0] g_core = g.u_soc.\g_cpu.u_core .state;
    wire [8:0] g_qspi = g.u_soc.u_qspi.state;

    integer cycles, seed, fd, cyc, mism, fsm_steps, resets, hold, quiet, last_reset;
    function automatic hunted(input [2:0] core, input [3:0] qspi);
        hunted = (core == 3'd7) || (qspi == 4'd1) || (qspi == 4'd4) || (qspi == 4'd5);
    endfunction
    reg [1023:0] prog, fsmlog;
    reg [2:0] last_core;
    reg [3:0] last_qspi;

    initial begin
        if (!$value$plusargs("PROG=%s", prog)) prog = "prog.hex";
        if (!$value$plusargs("CYCLES=%d", cycles)) cycles = 20000;
        if (!$value$plusargs("SEED=%d", seed)) seed = 1;
        fd = 0;
        if ($value$plusargs("FSMLOG=%s", fsmlog)) fd = $fopen(fsmlog, "w");
        #1 $readmemh(prog, r_flash.mem);
        $readmemh(prog, g_flash.mem);
        if ($test$plusargs("BOOT")) ui_in[7] = 1'b1;   // start in the UART bootloader ROM
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);
        ui_in[7] = 1'b0;
        mism = 0; fsm_steps = 0; resets = 0; hold = 0; quiet = 0; last_reset = 0;
        last_core = r_core; last_qspi = r_qspi;
        for (cyc = 0; cyc < cycles; cyc = cyc + 1) begin
            @(negedge clk);
            // compare after the outputs have settled from the last rising edge
            if ({r_uo, r_uio_out, r_uio_oe} !== {g_uo, g_uio_out, g_uio_oe}) begin
                mism = mism + 1;
                if (mism <= 5)
                    $display("  MISMATCH clock %0d: rtl uo=%h uio=%h oe=%h core=%0d qspi=%0d | gates uo=%h uio=%h oe=%h core=%b qspi=%b",
                             cyc, r_uo, r_uio_out, r_uio_oe, r_core, r_qspi, g_uo, g_uio_out, g_uio_oe, g_core, g_qspi);
            end
            if (fd != 0) begin
                $fwrite(fd, "tp_ncore %0d %0d %b\n", last_core, r_core, g_core);
                $fwrite(fd, "qspi_ctrl %0d %0d %b\n", last_qspi, r_qspi, g_qspi);
            end
            if (last_core !== r_core || last_qspi !== r_qspi) fsm_steps = fsm_steps + 1;
            last_core = r_core; last_qspi = r_qspi;
            // stimulus: capture pins and the UART line wiggle at random; the
            // boot-select pin (ui_in[7]) only moves in reset, never here
            if (($random(seed) & 15) == 0) ui_in[5:0] = $random(seed);
            // ui[2:0] set the QSPI read latency while reset is held (README
            // pinout). A board straps them; a random value here makes every
            // fetch after a mid-run reset land a byte off, and the program
            // runs garbage. Hold them at 0 from a reset until 4 clocks after.
            if (quiet > 0) begin ui_in[2:0] = 3'd0; quiet = quiet - 1; end
            // mid-run resets: both copies see the same rst_n, so the pins must still agree
            if (hold > 0) begin
                hold = hold - 1;
                if (hold == 0) rst_n = 1'b1;
            end else if ($test$plusargs("RESETS") && ($random(seed) & 4095) == 0) begin
                rst_n = 1'b0; hold = 3; quiet = 8; ui_in[2:0] = 3'd0; resets = resets + 1; last_reset = cyc;
            end else if ($test$plusargs("RESETHUNT") && cyc - last_reset > 1024 &&
                         (resets % 2 ? r_qspi == 4'd4 : hunted(r_core, r_qspi) && ($random(seed) & 15) == 0)) begin
                // every other hunted reset waits for Q_END, which lasts a single clock and is rare
                rst_n = 1'b0; hold = 3; quiet = 8; ui_in[2:0] = 3'd0; resets = resets + 1; last_reset = cyc;
            end
        end
        if (fd != 0) $fclose(fd);
        $display("lockstep %0s: %0d clocks, %0d state changes, %0d mid-run resets, %0d mismatches", prog, cycles, fsm_steps, resets, mism);
        if (mism == 0) $display("LOCKSTEP PASSED");
        else           $display("LOCKSTEP FAILED");
        $finish;
    end
endmodule
