// tb_branch.sv — forward-branch prefetch and the QSPI abort, at the pins.
//
//   cd test && make branch
//
// Runs sw/examples/branch_mix.c from flash (+HEX) or from RAM (+RAMHEX) on
// the real top level and checks:
//   - the UART prints the checksum test/branch_check.py computes (+EXPECT)
//   - no illegal instruction, main() returns
//   - the abort happened where it can: a flash fetch streaming its data, and
//     a RAM fetch in its select/address/dummy phase. With the abort taken
//     out of the RTL, the dropped fall-through word runs as the branch
//     target and the checksum fails.
//   - no abort met a word already held or arriving in the abort clock: a
//     branch resolves at most 16 clocks after its prefetch starts and a word
//     takes at least 17, and tp_bus relies on it
//   - outside the wake-up sequence chip select never rises while sck is high
//     or on the clock sck falls (the wake-up steps end with both on one edge)
//   - RAM timing (tCPH >= 18 ns, tCEM <= 8 us) held throughout
// Prints one ok/FAIL line per check and "N checks, M failures".
`default_nettype none
`timescale 1ns/1ps

module tb_branch;
    localparam integer DIV = 8;
    reg        clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg  [7:0] ui_in = 8'h08;
    wire [7:0] uo_out, uio_out, uio_oe;
    always #10 clk = ~clk;

    wire sck  = uio_out[3];
    wire cs_f = uio_out[0];
    wire cs_r = uio_out[6];
    wire [3:0] flash_sd, psram_sd;
    wire [3:0] sd_bus = uio_oe[1] ? {uio_out[5], uio_out[4], uio_out[2], uio_out[1]}
                      : (!cs_f ? flash_sd : (!cs_r ? psram_sd : 4'hF));
    wire [7:0] uio_in = {2'b00, sd_bus[3], sd_bus[2], 1'b0, sd_bus[1], sd_bus[0], 1'b0};

    tt_um_normansrule_tiqora dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n));
    qspi_flash_model #(.DUMMY(4), .WORDS(16384)) u_flash (
        .cs_n(cs_f), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(1 << 20)) u_psram (
        .cs_n(cs_r), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    // ---- abort coverage, by where the dropped fetch was ----
    // ab_held: the dropped word was already held, or landed in the abort
    // clock. tp_bus relies on that never happening (it would hand the word
    // to the core as the branch target), so it is a check, not coverage.
    integer ab_stream = 0, ab_addr = 0, ab_end = 0, ab_held = 0, ab_total = 0;
    always @(posedge clk) if (rst_n && dut.u_soc.g_cpu.u_core.imem_abort) begin
        ab_total = ab_total + 1;
        if (dut.u_soc.u_bus.i_hold || (dut.u_soc.q_rvalid && !dut.u_soc.u_bus.owner)) ab_held = ab_held + 1;
        if (dut.u_soc.q_abort) case (dut.u_soc.u_qspi.state)
            4'd3:             ab_stream = ab_stream + 1;     // Q_DATA
            4'd1, 4'd2, 4'd5: ab_addr   = ab_addr + 1;       // Q_PREFIX, Q_DUMMY, Q_DESEL
            4'd4:             ab_end    = ab_end + 1;        // Q_END
            default: ;
        endcase
    end

    // ---- pin protocol: chip select rises only with sck low since the last clock ----
    reg sck_q = 1'b0, csf_q = 1'b1, csr_q = 1'b1;
    integer cs_bad = 0;
    always @(posedge clk) begin
        if (rst_n && !dut.u_soc.waking && ((cs_f && !csf_q) || (cs_r && !csr_q)) && (sck || sck_q)) begin
            cs_bad = cs_bad + 1;
            if (cs_bad < 4) $display("  chip select rose with sck high at %0t", $time);
        end
        sck_q <= sck; csf_q <= cs_f; csr_q <= cs_r;
    end

    // ---- UART terminal: keeps the last line ----
    reg [8*64:1] line = 0;
    always begin : terminal
        integer i; reg [7:0] b;
        @(posedge clk);
        if (rst_n && uo_out[4] === 1'b0) begin
            repeat (DIV / 2) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin repeat (DIV) @(posedge clk); b[i] = uo_out[4]; end
            repeat (DIV) @(posedge clk);
            if (b != 8'h0A) line = {line[8*63:1], b};
        end
    end

    integer fails = 0, checks = 0, n = 0;
    task chk(input bit ok, input [8*96:1] what);
        checks = checks + 1;
        if (!ok) fails = fails + 1;
        $display("  %s  %0s", ok ? "ok  " : "FAIL", what);
    endtask

    reg [8*256:1] hexfile, ramhex, expect_s;
    reg from_ram;
    initial begin
        if (!$value$plusargs("EXPECT=%s", expect_s)) expect_s = "?";
        from_ram = $value$plusargs("RAMHEX=%s", ramhex);
        if (from_ram) begin
            $readmemh(ramhex, u_psram.mem);
            u_flash.mem[0] = 32'h100002b7;        // lui  x5, 0x10000
            u_flash.mem[1] = 32'h00028067;        // jalr x0, 0(x5)
        end else begin
            if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "branch_flash.hex";
            $readmemh(hexfile, u_flash.mem);
        end
        repeat (10) @(posedge clk); rst_n = 1'b1;
        while (!dut.u_soc.g_cpu.u_core.halted && n < 3000000) begin @(posedge clk); n = n + 1; end
        repeat (40 * DIV) @(posedge clk);
        $display("--- branch_mix from %0s: printed '%0s', expected '%0s', %0d clocks; aborts %0d: streaming %0d, address/dummy %0d, end %0d, held word %0d",
                 from_ram ? "RAM" : "flash", line[8*8:1], expect_s[8*8:1], n,
                 ab_total, ab_stream, ab_addr, ab_end, ab_held);
        chk(dut.u_soc.g_cpu.u_core.halted, "main() returned");
        chk(!dut.u_soc.g_cpu.u_core.illegal_q, "no illegal instruction");
        chk(line[8*8:1] == expect_s[8*8:1], "checksum matches the Python model (test/branch_check.py)");
        if (from_ram) begin
            chk(ab_addr > 0, "a RAM fetch was aborted in its select, address or dummy phase");
        end else begin
            chk(ab_stream > 0, "a streaming flash fetch was aborted");
        end
        chk(ab_held == 0, "no fetched word was held or arrived when a branch aborted it");
        chk(cs_bad == 0, "chip select never rose with sck high or as it fell (after wake-up)");
        chk(u_psram.violations == 0, "RAM timing held throughout");
        $display("%0d checks, %0d failures", checks, fails);
        $finish;
    end
endmodule
