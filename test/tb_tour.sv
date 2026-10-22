// tb_tour.sv — the explorer's guided tours, recorded from the real RTL.
//
//   cd test && make tour
//
// Runs sw/mktour.py's program from the flash model, through the Tiny Tapeout
// pins exactly as tb_run does, checks every step the tours narrate, and
// writes one line per clock (+TRACE=file): the pins plus the internal
// signals the tours show. docs/tools/traces.py turns that file into the
// explorer's trace fixtures, so every value an animation shows is a value
// this simulation produced. Values are sampled on the falling clock edge,
// after the rising edge has updated every flip-flop; cycle 0 is the first
// rising edge after reset is released.
`default_nettype none
`timescale 1ns/1ps

module tb_tour;
    reg        clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg  [7:0] ui_in = 8'h08;              // UART RX idles high; latency 0; BOOT low
    wire [7:0] uo_out, uio_out, uio_oe;
    always #10 clk = ~clk;                 // 50 MHz

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
    qspi_flash_model #(.DUMMY(4), .WORDS(512)) u_flash (
        .cs_n(cs_f), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) u_psram (
        .cs_n(cs_r), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    integer errors = 0, checks = 0;
    task chk(input cond, input [8*72:1] msg);
        begin
            checks = checks + 1;
            if (cond) $display("  ok    %0s", msg);
            else begin errors = errors + 1; $display("  FAIL  %0s", msg); end
        end
    endtask

    // ---------------------------------------------------------------- trace
    integer cycle = -4, fd = 0, hang_phase = 0;
    reg [8*256:1] tracefile;
    always @(negedge clk) if (fd != 0) begin
        $fwrite(fd, "%0d%s %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",
            cycle, hang_phase ? "h" : "", rst_n, ui_in, uo_out, uio_out, uio_oe, uio_in,
            dut.u_soc.g_cpu.u_core.state, dut.u_soc.g_cpu.u_core.phase,
            {dut.u_soc.g_cpu.u_core.pc, 2'b00}, dut.u_soc.g_cpu.u_core.ir,
            dut.u_soc.g_cpu.u_core.a_n, dut.u_soc.g_cpu.u_core.bx_n, dut.u_soc.g_cpu.u_core.sum_n,
            dut.u_soc.g_cpu.u_core.cin, dut.u_soc.g_cpu.u_core.cout, dut.u_soc.g_cpu.u_core.rf_we,
            dut.u_soc.g_cpu.u_core.rf_wd,
            dut.u_soc.g_cpu.u_core.imem_req, dut.u_soc.g_cpu.u_core.imem_rvalid,
            dut.u_soc.g_cpu.u_core.imem_rdata, dut.u_soc.g_cpu.u_core.dmem_addr,
            dut.u_soc.g_cpu.u_core.dmem_req, dut.u_soc.u_qspi.state, dut.u_soc.u_qspi.waking,
            dut.u_soc.u_qspi.wstep, dut.u_soc.u_sync.now, dut.u_soc.u_sync.u_cmp.deadline[0],
            dut.u_soc.u_sync.u_cmp.armed[0], dut.u_soc.u_sync.fifo_count[1], dut.u_soc.u_sync.fifo_count[0],
            dut.u_soc.u_sync.fifo_ovf, dut.u_soc.g_cpu.u_core.t_valid, dut.u_soc.g_cpu.u_core.t_rdata);
    end
    always @(posedge clk) if (rst_n) cycle <= cycle + 1;

    // ---------------------------------------------------------------- monitors
    integer trig_rise = -1, trig_width = 0, twait_at_deadline = -1, twait_exit = -1;
    integer ill_rise = -1, halt_rise = -1, ovf_rise = -1, max_count = 0;
    integer pops = 0;
    reg [31:0] pop_val [0:2];
    reg [31:0] deadline;
    always @(negedge clk) if (rst_n && !hang_phase) begin
        if (uo_out[0] && trig_rise < 0) begin
            trig_rise = cycle; deadline = dut.u_soc.u_sync.u_cmp.deadline[0];
            chk(dut.u_soc.u_sync.now == deadline, "TRIG0 pin rises on exactly the deadline tick");
            twait_at_deadline = (dut.u_soc.g_cpu.u_core.state == 3'd3);
        end
        if (uo_out[0]) trig_width = trig_width + 1;
        if (trig_rise >= 0 && twait_exit < 0 && dut.u_soc.g_cpu.u_core.state != 3'd3) twait_exit = cycle;
        if (uo_out[6] && ill_rise < 0) ill_rise = cycle;
        if (uo_out[5] && halt_rise < 0) halt_rise = cycle;
        if (uo_out[3] && ovf_rise < 0) ovf_rise = cycle;
        if (dut.u_soc.u_sync.fifo_count > max_count) max_count = dut.u_soc.u_sync.fifo_count;
        if (dut.u_soc.g_cpu.u_core.t_valid && dut.u_soc.g_cpu.u_core.t_op == 3'd1 && pops < 3) begin
            pop_val[pops] = dut.u_soc.g_cpu.u_core.t_rdata; pops = pops + 1;
        end
    end

    // UART: decode what a terminal on uo_out[4] receives (8 clocks per bit)
    reg [7:0] rx_byte = 8'h00; integer rx_bytes = 0;
    always begin : terminal
        integer i;
        @(posedge clk);
        if (rst_n && dut.u_soc.u_periph.uart_tx === 1'b0 && cycle > 0) begin
            repeat (4) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin repeat (8) @(posedge clk); rx_byte[i] = uo_out[4]; end
            repeat (8) @(posedge clk);
            rx_bytes = rx_bytes + 1;
        end
    end

    // capture stimulus: three rising edges, 4 clocks apart, once ILLEGAL is up
    integer edges_at = -1;
    always @(posedge clk) if (ill_rise >= 0 && !hang_phase) begin
        if (edges_at < 0) edges_at = cycle + 10;
        if (cycle == edges_at)      ui_in[0] <= 1'b1;
        if (cycle == edges_at + 4)  ui_in[1] <= 1'b1;
        if (cycle == edges_at + 8)  ui_in[2] <= 1'b1;
    end

    integer n, wake_clocks, ecall_word;
    initial begin
        $readmemh("tour.hex", u_flash.mem);
        if (!$value$plusargs("ECALL=%d", ecall_word)) ecall_word = -1;
        if ($value$plusargs("TRACE=%s", tracefile)) fd = $fopen(tracefile, "w");
        if (fd != 0) $fwrite(fd, "cycle rst_n ui_in uo_out uio_out uio_oe uio_in state phase pc ir a_n bx_n sum_n cin cout rf_we rf_wd imem_req imem_rvalid imem_rdata dmem_addr dmem_req q_state waking wstep now deadline0 armed0 qcount1 qcount0 ovf t_valid t_rdata\n");
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        n = 0;
        while (dut.u_soc.u_qspi.waking && n < 2000) begin @(posedge clk); n = n + 1; end
        wake_clocks = n;
        chk(!dut.u_soc.u_qspi.waking, "the memory wake-up sequence finishes");
        chk(u_flash.cont === 1'b1 && u_psram.qpi === 1'b1, "flash in continuous read, RAM in QPI mode");
        n = 0;
        while (!uo_out[5] && n < 20000) begin @(posedge clk); n = n + 1; end
        repeat (12) @(posedge clk);
        chk(halt_rise >= 0 && dut.u_soc.g_cpu.u_core.pc == ecall_word, "the program reaches ECALL, not the fail handler");
        chk(rx_bytes == 1 && rx_byte == "K", "one UART byte 'K' at uo_out[4]");
        chk(trig_width == 8, "TRIG0 pulse is 8 ticks wide at the pin");
        chk(twait_at_deadline == 1 && twait_exit - trig_rise <= 2, "the core is parked in TWAIT at the deadline and leaves it");
        chk({u_psram.mem[3], u_psram.mem[2], u_psram.mem[1], u_psram.mem[0]} == 32'h22222221,
            "x9 + x10 = 0x22222221 reached RAM A, least significant byte first");
        chk(ill_rise >= 0, "the all-zero word raises ILLEGAL at uo_out[6]");
        chk(max_count == 2 && ovf_rise >= 0, "three events into a 2-deep queue: full at 2, OVF at uo_out[3]");
        chk(pop_val[0][31] == 1'b0 && pop_val[0][30:28] == 3'd0 && pop_val[0][27] == 1'b1,
            "first TPOP: hardware event, channel 0, rising");
        chk(pop_val[1][30:28] == 3'd1 && pop_val[1][26:0] - pop_val[0][26:0] == 27'd4,
            "second TPOP: channel 1, timestamp exactly 4 ticks later");
        chk(pop_val[2] == 32'd0, "third TPOP: queue empty, reads 0");
        // ---- the error tour: an unmapped load stalls; reset recovers ----
        $readmemh("tour_hang.hex", u_flash.mem);
        // ui_in[2:0] are the QSPI read latency while reset is held: put them
        // back to 0, or the chip boots with latency 7 and reads shifted words
        rst_n = 1'b0; cycle = -4; hang_phase = 1; ui_in = 8'h08;
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        n = 0;
        while (n < 1500) begin @(posedge clk); n = n + 1; end
        chk(dut.u_soc.g_cpu.u_core.state == 3'd5 && dut.u_soc.g_cpu.u_core.dmem_addr == 32'h5000_0000 &&
            !uo_out[5] && !uo_out[6], "a load from 0x5000_0000 stalls in MEM: no HALT, no ILLEGAL");
        rst_n = 1'b0; repeat (4) @(posedge clk);
        chk(dut.u_soc.g_cpu.u_core.state == 3'd0 && dut.u_soc.u_qspi.waking, "reset recovers: FETCH, memory wake-up restarts");
        rst_n = 1'b1; repeat (8) @(posedge clk);
        $display("  wake-up %0d clocks; deadline tick at cycle %0d; HALT at cycle %0d", wake_clocks, trig_rise, halt_rise);
        if (fd != 0) $fclose(fd);
        $display("%0d checks, %0d failures", checks, errors);
        if (errors == 0) $display("TOUR TRACE PASSED");
        else             $display("TOUR TRACE FAILED");
        $finish;
    end
endmodule
