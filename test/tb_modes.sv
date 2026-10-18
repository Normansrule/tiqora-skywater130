// tb_modes.sv — CPU / GPU / TPU modes (the TIQORA_MODES build), end to end.
//
// Runs test/modes.hex (built by sw/mkmodes.py) from the QSPI flash model
// through the real Tiny Tapeout pins and checks:
//   - every result slot in PSRAM against sw/modes_model.py (directed and
//     seeded random GPU and TPU operations, mode reads, untouched sentinels);
//   - every illegal-instruction trap: exactly the expected PCs, in order, and
//     the ILLEGAL pin (uo_out[6]) rising on the first one;
//   - the switch latency of every MSET, measured in clocks;
//   - the TRIG0 pin edge on the exact armed tick while MSETs commit on both
//     sides of the deadline.
//
// Run with:  make modes        (exits non-zero on any failure)
`default_nettype none
`timescale 1ns/1ps

module tb_modes;
    localparam int TIMEOUT   = 3000000;
    localparam int MAX_EXP   = 512;

    reg        clk   = 1'b0;
    reg        rst_n = 1'b0;
    reg  [7:0] ui_in = 8'h00;
    wire [7:0] uo_out, uio_out, uio_oe;
    integer errors = 0, checks = 0;

    always #5 clk = ~clk;

    wire halt = uo_out[5];
    wire ill  = uo_out[6];
    wire trig0 = uo_out[0];
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
        .ena(1'b1), .clk(clk), .rst_n(rst_n)
    );
    qspi_flash_model #(.DUMMY(4), .WORDS(4096)) u_flash (
        .cs_n(cs_f), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) u_psram (
        .cs_n(cs_r), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    task automatic check(input bit ok, input string what);
        checks++;
        if (!ok) begin errors++; $display("  FAIL  %s", what); end
    endtask

    // ---- probes: what the core is doing (observation only) ----
    wire [2:0]  st     = dut.u_soc.g_cpu.u_core.state;
    wire [2:0]  ph     = dut.u_soc.g_cpu.u_core.phase;
    wire        second = dut.u_soc.g_cpu.u_core.second;
    wire        legal  = dut.u_soc.g_cpu.u_core.legal;
    wire [31:0] pc     = dut.u_soc.g_cpu.u_core.dbg_pc;
    wire [31:0] ir     = dut.u_soc.g_cpu.u_core.ir;
    wire        rvalid = dut.u_soc.g_cpu.u_core.imem_rvalid;
    wire [31:0] rdata  = dut.u_soc.g_cpu.u_core.imem_rdata;
    wire [31:0] now    = dut.u_soc.u_sync.now;

    // trap log: an instruction found illegal at the end of its first pass
    reg [31:0] trap_pc [0:MAX_EXP-1];
    integer    n_trap = 0;
    longint    cyc = 0, first_trap_cyc = -1, ill_rise_cyc = -1;
    reg        ill_q = 1'b0;

    // latency: issue = the clock an instruction word is taken into ir
    longint    issue_cyc = 0, last_issue_cyc = 0;
    reg [31:0] issue_w = 32'h13, last_w = 32'h13;
    integer    lat_min = 1000, lat_max = 0, n_mset = 0;      // MSET issue -> commit
    integer    gap_min = 1000, gap_max = 0;                  // MSET issue -> next issue
    integer    agap_min = 1000, agap_max = 0;                // ADDI issue -> next issue
    // timing section: MSET commits relative to the deadline tick
    integer    commits_timing = 0;
    reg [31:0] commit_now [0:63];

    always @(posedge clk) begin
        cyc <= cyc + 1;
        ill_q <= ill;
        if (ill && !ill_q && ill_rise_cyc < 0) ill_rise_cyc <= cyc;
        if (rst_n && st == 3'd2 && ph == 3'd7 && !second && !legal) begin
            if (n_trap < MAX_EXP) trap_pc[n_trap] <= pc;
            n_trap <= n_trap + 1;
            if (first_trap_cyc < 0) first_trap_cyc <= cyc;
        end
        if (rst_n && st == 3'd0 && rvalid) begin
            // the previous instruction's issue-to-issue gap
            if (last_w[6:0] == 7'h2B && last_w[14:12] == 3'd1) begin
                if (cyc - issue_cyc < gap_min) gap_min = cyc - issue_cyc;
                if (cyc - issue_cyc > gap_max) gap_max = cyc - issue_cyc;
            end
            if (last_w[6:0] == 7'h13 && last_w[14:12] == 3'd0) begin
                if (cyc - issue_cyc < agap_min) agap_min = cyc - issue_cyc;
                if (cyc - issue_cyc > agap_max) agap_max = cyc - issue_cyc;
            end
            issue_cyc = cyc;
            last_w    = rdata;
        end
        // MSET commits on its XP clock (state 6)
        if (rst_n && st == 3'd6 && ir[6:0] == 7'h2B && ir[14:12] == 3'd1) begin
            n_mset++;
            if (cyc - issue_cyc < lat_min) lat_min = cyc - issue_cyc;
            if (cyc - issue_cyc > lat_max) lat_max = cyc - issue_cyc;
            if (ir[11:7] == 5'd14 && commits_timing < 64) begin
                commit_now[commits_timing] = now;
                commits_timing++;
            end
        end
    end

    // TRIG0 edge, sampled exactly as tb_soc does
    reg [31:0] trig_rise_time = 32'hFFFF_FFFF;
    reg        trig_seen = 1'b0, trig0_q = 1'b0;
    always @(posedge clk) begin
        trig0_q <= trig0;
        if (trig0 && !trig0_q && !trig_seen) begin
            trig_rise_time <= now;
            trig_seen      <= 1'b1;
        end
    end

    function automatic [31:0] psram_word(input integer s);
        psram_word = {u_psram.mem[s*4+3], u_psram.mem[s*4+2], u_psram.mem[s*4+1], u_psram.mem[s*4]};
    endfunction

    // ---- expectations ----
    string     kind_s, lbl;
    integer    fd, code, a_i, k, n_slot = 0, n_exp_trap = 0, dead_slot = -1, exp_msets = -1;
    reg [31:0] b_v;
    integer    e_slot [0:MAX_EXP-1];
    reg [31:0] e_val  [0:MAX_EXP-1];
    string     e_lbl  [0:MAX_EXP-1];
    reg [31:0] t_pc   [0:MAX_EXP-1];
    string     t_lbl  [0:MAX_EXP-1];

    initial begin
        integer n_before, n_after;
        reg [31:0] dl;
        #1 $readmemh("modes.hex", u_flash.mem);
        fd = $fopen("modes_expect.txt", "r");
        if (fd == 0) $fatal(1, "cannot open modes_expect.txt: run python3 ../sw/mkmodes.py");
        code = 1;
        while (code == 4 || code == 1) begin
            code = $fscanf(fd, "%s %h %h %s\n", kind_s, a_i, b_v, lbl);
            if (code != 4) code = 0;
            else if (kind_s == "slot")     begin e_slot[n_slot] = a_i; e_val[n_slot] = b_v; e_lbl[n_slot] = lbl; n_slot++; end
            else if (kind_s == "trap") begin t_pc[n_exp_trap] = a_i; t_lbl[n_exp_trap] = lbl; n_exp_trap++; end
            else if (kind_s == "deadline") dead_slot = a_i;
            else if (kind_s == "msets") exp_msets = a_i;
        end
        $fclose(fd);
        $display("\n=== Tiqora CPU / GPU / TPU modes ===");
        $display("loaded %0d result slots, %0d expected traps", n_slot, n_exp_trap);
        check(n_slot > 100 && n_exp_trap > 20 && dead_slot >= 0 && exp_msets > 0, "expectation file is complete");

        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        while (!halt && cyc < TIMEOUT) @(posedge clk);
        repeat (40) @(posedge clk);
        $display("ran %0d clocks", cyc);

        check(halt, "program reached ECALL and halted");

        // results
        for (k = 0; k < n_slot; k++) begin
            checks++;
            if (psram_word(e_slot[k]) !== e_val[k]) begin
                errors++;
                $display("  FAIL  slot %0d got %08x want %08x  %s", e_slot[k], psram_word(e_slot[k]), e_val[k], e_lbl[k]);
            end
        end

        // traps
        check(n_trap == n_exp_trap, $sformatf("%0d traps seen, %0d expected", n_trap, n_exp_trap));
        for (k = 0; k < n_exp_trap && k < n_trap; k++) begin
            checks++;
            if (trap_pc[k] !== t_pc[k]) begin
                errors++;
                $display("  FAIL  trap %0d at pc %08x, expected %08x  %s", k, trap_pc[k], t_pc[k], t_lbl[k]);
            end
        end
        check(ill_rise_cyc == first_trap_cyc + 1, "ILLEGAL pin rises the clock after the first trap");

        // latency
        $display("  MSET issue -> commit: %0d..%0d clocks over %0d switches (measured)", lat_min, lat_max, n_mset);
        $display("  MSET issue -> next issue: %0d..%0d clocks; ADDI: %0d..%0d clocks (measured)",
                 gap_min, gap_max, agap_min, agap_max);
        check(n_mset == exp_msets, $sformatf("%0d mode switches committed, %0d expected", n_mset, exp_msets));
        check(lat_min >= 9 && lat_max <= 16, "every switch commits 9..16 clocks after issue (align 0..7 + pass 8 + XP 1)");

        // deadline across switches
        dl = psram_word(dead_slot);
        n_before = 0; n_after = 0;
        for (k = 0; k < commits_timing; k++) begin
            if ($signed(commit_now[k] - dl) < 0) n_before++; else n_after++;
        end
        $display("  deadline %0d, TRIG0 rose at %0d; %0d switches committed before it, %0d after",
                 dl, trig_rise_time, n_before, n_after);
        check(commits_timing == 24, "all 24 timing-section switches committed");
        check(n_before > 0 && n_after > 0, "switches committed on both sides of the deadline");
        check(trig_seen && trig_rise_time == dl, "TRIG0 edge on the exact armed tick across mode switches");

        $display("\n%0d checks, %0d failures", checks, errors);
        if (errors == 0) $display("MODES TEST PASSED\n");
        else begin $display("MODES TEST FAILED\n"); $fatal(1, "modes test failed"); end
        $finish;
    end
endmodule
