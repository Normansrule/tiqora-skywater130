// tb_reset.sv — reset in the middle of work, from the pins.
//
// tb_mcu.sv resets the chip once, from power-up. On a board, reset also
// comes while the chip is busy: a button, a host that restarts it, a
// watchdog. This bench runs sw/examples/mcu_e2e.c from flash and pulls
// rst_n low for ONE clock (the shortest reset the chip can see; it is
// synchronous) at six points where something is in flight:
//
//   uart    a byte half-way out of the UART transmitter
//   fetch   the core streaming instructions from the flash, which is in
//           continuous-read mode and keeps it across the chip's reset
//   ram     the QSPI controller driving a write into the RAM
//   armed   trigger 0 armed 20,000 ticks ahead, not yet fired
//   pulse   trigger 0 high, part-way through its 10-tick pulse
//   capture an input edge waiting in the event queue
//
// After each one it checks, one clock into reset:
//   * every output pin (uo_out, uio_out, uio_oe) equals its value in the
//     power-up reset, whatever the chip was doing;
//   * the timing unit is back at zero: timebase 0, nothing armed, queue
//     empty, overflow clear, no trigger output;
// and after release:
//   * the chip boots again from the flash and prints "ready";
//   * a deadline armed before the reset never fires afterwards.
// Finally the whole mcu_e2e conversation runs to "done" after the last
// reset, so nothing the resets left behind (the flash's continuous-read
// mode, the RAM's quad mode) breaks a full run.
//
// The flash and RAM models keep their own state across the chip's reset,
// as real parts do. Run with:  make reset
`default_nettype none
`timescale 1ns/1ps

module tb_reset;
    localparam int BOOT_DIV = 32;
    localparam int PROG_DIV = 8;        // what the program sets (BAUD_DIV=8 build)
    reg        clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg  [7:0] ui_in = 8'h08;           // UART RX idle high, read latency 0
    wire [7:0] uo_out, uio_out, uio_oe;
    integer errors = 0, checks = 0;
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
        .uio_out(uio_out), .uio_oe(uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n));

    defparam dut.u_soc.u_periph.DIV_RESET = BOOT_DIV;
    qspi_flash_model #(.DUMMY(4), .WORDS(4096)) u_flash (
        .cs_n(cs_f), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(1 << 20)) u_psram (
        .cs_n(cs_r), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    task chk(input cond, input [8*88:1] msg);
        begin
            checks = checks + 1;
            if (cond) $display("  ok    %0s", msg);
            else begin errors = errors + 1; $display("  FAIL  %0s", msg); end
        end
    endtask

    wire [31:0] now = dut.u_soc.u_sync.now;
    integer     cyc = 0;
    always @(posedge clk) cyc <= cyc + 1;

    // ---- the host end of the serial line (as tb_mcu.sv) ----
    reg [7:0] rx_buf [0:1023];
    integer   rx_n = 0;
    always begin : receiver
        integer i; reg [7:0] b;
        @(posedge clk);
        if (rst_n && uo_out[4] === 1'b0) begin
            repeat (PROG_DIV / 2) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin repeat (PROG_DIV) @(posedge clk); b[i] = uo_out[4]; end
            repeat (PROG_DIV) @(posedge clk);
            if (rx_n < 1024) rx_buf[rx_n] = b;
            rx_n = rx_n + 1;
        end
    end

    task host_send(input [7:0] b);
        integer i;
        begin
            ui_in[3] = 1'b0; repeat (PROG_DIV) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin ui_in[3] = b[i]; repeat (PROG_DIV) @(posedge clk); end
            ui_in[3] = 1'b1; repeat (PROG_DIV) @(posedge clk);
        end
    endtask

    integer   rd = 0;
    reg [7:0] line [0:79];
    integer   len;
    task get_line(output logic got);
        integer t;
        begin
            len = 0; got = 1'b0; t = 0;
            while (!got && t < 500000) begin
                if (rd < rx_n) begin
                    if (rx_buf[rd] == 8'h0a) got = 1'b1;
                    else if (len < 80) begin line[len] = rx_buf[rd]; len = len + 1; end
                    rd = rd + 1;
                end else begin @(posedge clk); t = t + 1; end
            end
            $write("        chip: \"");
            for (t = 0; t < len; t = t + 1) $write("%c", line[t]);
            $display("\"%0s", got ? "" : "  (timed out)");
        end
    endtask

    function automatic logic line_is(input [8*16:1] s, input integer n);
        integer i;
        begin
            line_is = (len == n);
            for (i = 0; i < n && i < len; i = i + 1)
                if (line[i] !== s[8*(n - i) -: 8]) line_is = 1'b0;
        end
    endfunction

    // ---- trigger 0, watched every clock ----
    integer trig_rises = 0;
    reg     trig_q = 1'b0;
    always @(posedge clk) begin
        trig_q <= uo_out[0];
        if (rst_n && uo_out[0] && !trig_q) trig_rises = trig_rises + 1;
    end

    integer rises_rel = 0;    // trigger rises counted at the last release
    // ---- the state one clock into reset ----
    reg  [7:0] cold_uo, cold_uio, cold_oe;
    logic      clean;

    task snap_cold;
        begin
            cold_uo = uo_out; cold_uio = uio_out; cold_oe = uio_oe;
            $display("        power-up reset: uo_out %h, uio_out %h, uio_oe %h", cold_uo, cold_uio, cold_oe);
        end
    endtask

    // Pull rst_n low across exactly one rising edge, look, and let go.
    task pulse_reset(input [8*12:1] what);
        begin
            @(negedge clk) rst_n = 1'b0;
            @(posedge clk) #1;
            chk(uo_out === cold_uo && uio_out === cold_uio && uio_oe === cold_oe,
                {what, ": every output pin is at its power-up reset value"});
            if (!(uo_out === cold_uo && uio_out === cold_uio && uio_oe === cold_oe))
                $display("        got uo_out %h, uio_out %h, uio_oe %h", uo_out, uio_out, uio_oe);
            clean = (now === 32'd0) && (dut.u_soc.u_sync.armed === '0) &&
                    (dut.u_soc.u_sync.fifo_empty === 1'b1) && (dut.u_soc.u_sync.fifo_ovf === 1'b0) &&
                    (dut.u_soc.u_sync.trig_pin === '0) && (dut.u_soc.u_sync.pend_mask === '0);
            chk(clean, {what, ": timebase 0, nothing armed, queue empty, no overflow, no trigger"});
            // At reset every pin shows its built-in function (README, GPIO_SEL
            // reset 0xFF). Most functions are 0 one clock into reset, so the
            // pins alone cannot show a select left over from the program.
            chk(dut.u_soc.u_periph.gpio_sel === 8'hFF && dut.u_soc.u_periph.gpio_out === 8'h00,
                {what, ": every pin back on its built-in function (GPIO_SEL 0xFF, GPIO_OUT 0)"});
            @(negedge clk) rst_n = 1'b1;
            rises_rel = trig_rises;
            // a byte cut short by the reset may still complete in the
            // receiver: let it, then read only what comes after
            repeat (12 * PROG_DIV) @(posedge clk);
            rd = rx_n;
        end
    endtask

    logic got;
    integer i, n0, t, rises0;
    reg [7:0] msg [0:9];

    task expect_ready(input [8*12:1] what);
        begin
            get_line(got);
            chk(got && line_is("ready", 5), {what, ": boots again from flash and prints ready"});
            if (what != "power-up")
                chk(trig_rises == rises_rel && uo_out[0] === 1'b0,
                    {what, ": trigger 0 stayed low from release to ready"});
        end
    endtask

    // The host side of mcu_e2e up to the "out" line: echo a line, send 'g'.
    task converse_to_out;
        begin
            for (i = 0; i < 10; i = i + 1) begin
                n0 = rx_n;
                host_send(msg[i]);
                t = 0; while (rx_n == n0 && t < 200000) begin @(posedge clk); t = t + 1; end
            end
            get_line(got);
            host_send("g");
            get_line(got);
            get_line(got);
        end
    endtask

    initial begin
        $dumpfile("tb_reset.vcd");
        $dumpvars(0, tb_reset);
        #1 $readmemh("mcu_flash.hex", u_flash.mem);
        msg[0] = "h"; msg[1] = "e"; msg[2] = "l"; msg[3] = "l"; msg[4] = "o";
        msg[5] = " "; msg[6] = "t"; msg[7] = "q"; msg[8] = "7"; msg[9] = 8'h0a;
        $display("\n=== Tiqora: reset in the middle of work (mcu_e2e.c from flash) ===");
        repeat (2) @(posedge clk); #1;
        snap_cold;
        repeat (8) @(posedge clk); rst_n = 1'b1;
        expect_ready("power-up");

        // ---------------------------------------------------------- uart
        $display("[uart]");
        host_send("h");                          // the chip echoes "H"
        t = 0; while (uo_out[4] !== 1'b0 && t < 200000) begin @(posedge clk); t = t + 1; end
        // 2.5 bit times after the start edge: the middle of data bit 1 of
        // 'H' (0x48), a 0, so the line is low when reset arrives
        repeat (5 * PROG_DIV / 2) @(posedge clk);
        chk(t < 200000 && dut.u_soc.u_periph.tx_busy === 1'b1 && uo_out[4] === 1'b0,
            "a byte is going out of the UART and the line is low (a 0 bit)");
        pulse_reset("uart");
        expect_ready("uart");

        // ---------------------------------------------------------- fetch
        $display("[fetch]");
        host_send("x");
        t = 0; while (cs_f !== 1'b0 && t < 200000)
            begin @(posedge clk); t = t + 1; end
        repeat (9) @(posedge clk);
        chk(cs_f === 1'b0 && u_flash.cont === 1'b1,
            "the flash is mid-stream, in continuous-read mode");
        pulse_reset("fetch");
        expect_ready("fetch");

        // ---------------------------------------------------------- armed
        $display("[armed]");
        converse_to_out();
        t = 0; while (dut.u_soc.u_sync.armed[0] !== 1'b1 && t < 200000) begin @(posedge clk); t = t + 1; end
        repeat (100) @(posedge clk);
        chk(dut.u_soc.u_sync.armed[0] === 1'b1 && uo_out[0] === 1'b0,
            "trigger 0 is armed about 20,000 ticks ahead and has not fired");
        rises0 = trig_rises;
        pulse_reset("armed");
        expect_ready("armed");
        repeat (25000) @(posedge clk);
        chk(trig_rises == rises0, "the deadline armed before the reset never fires (25,000 ticks watched)");

        // ---------------------------------------------------------- pulse
        $display("[pulse]");
        rd = rx_n;
        // the chip already printed "ready" and is waiting for a line
        converse_to_out();
        t = 0; while (uo_out[0] !== 1'b1 && t < 200000) begin @(posedge clk); t = t + 1; end
        repeat (4) @(posedge clk);
        chk(uo_out[0] === 1'b1, "trigger 0 is part-way through its 10-tick pulse");
        pulse_reset("pulse");
        expect_ready("pulse");

        // ---------------------------------------------------------- capture
        $display("[capture]");
        converse_to_out();
        get_line(got);                           // "arm <tick>"
        get_line(got);                           // "cap?": channel 5 enabled, queue emptied
        ui_in[5] = 1'b1;
        repeat (6) @(posedge clk);
        chk(dut.u_soc.u_sync.fifo_empty === 1'b0 || dut.u_soc.u_sync.pend_mask !== '0,
            "an input edge is in the event queue");
        pulse_reset("capture");
        ui_in[5] = 1'b0;
        expect_ready("capture");

        // ---------------------------------------------------------- ram
        $display("[ram]");
        // the chip is waiting for a line again: run it to step 7, where it
        // writes 1 KB into the RAM
        converse_to_out();
        get_line(got);                           // "arm <tick>"
        get_line(got);                           // "cap?"
        ui_in[5] = 1'b1;
        get_line(got);                           // "cap ..."
        ui_in[5] = 1'b0;
        get_line(got);                           // "mark Y"
        t = 0; while (!(cs_r === 1'b0 && uio_oe[1] === 1'b1) && t < 400000) begin @(posedge clk); t = t + 1; end
        repeat (3) @(posedge clk);
        chk(cs_r === 1'b0 && uio_oe[1] === 1'b1, "the controller is driving a write into the RAM");
        pulse_reset("ram");
        expect_ready("ram");

        // ---------------------------------------------------------- full run
        $display("[a full run after the six resets]");
        converse_to_out();
        get_line(got);
        chk(got && len > 4 && line[0] == "a", "arm: the trigger is armed and reported");
        get_line(got);
        repeat (100) @(posedge clk);
        ui_in[5] = 1'b1;
        repeat (20) @(posedge clk);
        ui_in[5] = 1'b0;
        get_line(got);
        chk(got && len > 4 && line[0] == "c" && line[4] == "5", "cap: the input edge is captured on channel 5");
        get_line(got);
        chk(got && line_is("mark Y", 6), "mark Y");
        get_line(got);
        chk(got && line_is("ram Y", 5), "ram Y: 1 KB through the RAM reads back intact");
        get_line(got);
        chk(got && line_is("done", 4), "done");
        t = 0; while (!dut.u_soc.g_cpu.u_core.halted && t < 100000) begin @(posedge clk); t = t + 1; end
        chk(dut.u_soc.g_cpu.u_core.halted === 1'b1 && dut.u_soc.g_cpu.u_core.illegal_q === 1'b0,
            "main() returned, the core halted, no illegal instruction");
        chk(u_psram.violations == 0, "RAM timing held throughout");
        $display("        (%0d clocks = %0.1f ms at 50 MHz)", cyc, cyc * 0.00002);

        $display("\n%0d checks, %0d failures", checks, errors);
        if (errors == 0) $display("RESET TEST PASSED\n");
        else             $display("RESET TEST FAILED\n");
        $finish;
    end

    initial begin
        #40_000_000;            // 4M clocks
        $display("  FAIL  timed out\nRESET TEST FAILED");
        $finish;
    end
endmodule
