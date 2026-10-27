// tb_mcu.sv — the chip used as a microcontroller, end to end, at its pins.
//
// sw/examples/mcu_e2e.c runs from flash. This bench is everything outside
// the chip: the QSPI flash and RAM, a host on the serial line that answers
// the program, and the pins. Every reply is checked against what the bench
// itself did or saw:
//   uart     a line sent to the chip comes back upper-cased, a byte at a time
//   gpio in  the chip reports the pin levels the bench set
//   gpio out the pins go through the exact set / toggle / clear sequence
//   trigger  the trigger pin rises on the tick the program says it armed,
//            and stays high for the 10 ticks it asked for
//   capture  the timestamp of an input edge matches when the bench made it
//   mark, ram, and a clean halt with no illegal instruction
// Run with:  make mcu
`default_nettype none
`timescale 1ns/1ps

module tb_mcu;
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

    task chk(input cond, input [8*72:1] msg);
        begin
            checks = checks + 1;
            if (cond) $display("  ok    %0s", msg);
            else begin errors = errors + 1; $display("  FAIL  %0s", msg); end
        end
    endtask

    wire [31:0] now = dut.u_soc.u_sync.now;
    integer     cyc = 0;
    always @(posedge clk) cyc <= cyc + 1;

    // ---- the host end of the serial line ----
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

    // Read one line from the chip (without its '\n') into `line`.
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

    // Parse the decimal number that starts at line[p]; p moves past it and one space.
    integer p;
    task num(output [31:0] v);
        begin
            v = 0;
            while (p < len && line[p] >= "0" && line[p] <= "9") begin
                v = v * 10 + (line[p] - "0"); p = p + 1;
            end
            p = p + 1;
        end
    endtask

    // ---- pins, watched every clock ----
    reg  [7:0]  outs [0:63];            // each new value of the GPIO-mode outputs
    integer     n_outs = 0;
    reg  [7:0]  last_out = 8'hxx;
    wire [7:0]  gpio_out = uo_out & 8'hEE;   // pins 0 and 4 show their functions
    reg  [31:0] trig_tick = 32'hFFFF_FFFF;
    integer     trig_high = 0, trig_rises = 0;
    reg         trig_q = 1'b0;
    always @(posedge clk) if (rst_n) begin
        if (gpio_out !== last_out) begin
            if (n_outs < 64) outs[n_outs] = gpio_out;
            n_outs = n_outs + 1;
            last_out = gpio_out;
        end
        trig_q <= uo_out[0];
        if (uo_out[0] && !trig_q) begin trig_tick = now; trig_rises = trig_rises + 1; end
        if (uo_out[0] && trig_rises == 1) trig_high = trig_high + 1;
    end

    logic       got;
    integer     i, n0, edge_tick;
    reg  [31:0] d, ch, rising, ts;
    reg  [7:0]  msg [0:15];
    logic       seq;

    initial begin
        $dumpfile("tb_mcu.vcd");
        $dumpvars(0, tb_mcu);
        #1 $readmemh("mcu_flash.hex", u_flash.mem);
        $display("\n=== Tiqora as a microcontroller: mcu_e2e.c from flash ===");
        repeat (10) @(posedge clk); rst_n = 1'b1;

        get_line(got);
        chk(got && line_is("ready", 5), "boots from flash and prints ready");

        $display("[uart]");
        // A terminal with no receive FIFO on the far side: send the next
        // character once the previous one has been echoed.
        msg[0] = "h"; msg[1] = "e"; msg[2] = "l"; msg[3] = "l"; msg[4] = "o";
        msg[5] = " "; msg[6] = "t"; msg[7] = "q"; msg[8] = "7"; msg[9] = 8'h0a;
        for (i = 0; i < 10; i = i + 1) begin
            n0 = rx_n;
            host_send(msg[i]);
            p = 0; while (rx_n == n0 && p < 200000) begin @(posedge clk); p = p + 1; end
        end
        get_line(got);
        chk(got && line_is("HELLO TQ7", 9), "a line sent to the chip comes back upper-cased");

        $display("[gpio]");
        ui_in = 8'hAD;                  // bit 3 stays high: it is the UART line
        repeat (4) @(posedge clk);
        host_send("g");
        get_line(got);
        chk(got && line_is("in 000000ad", 11), "the chip reads the input pins the host set (0xAD)");
        ui_in = 8'h08;
        get_line(got);
        chk(got && line_is("out", 3), "output sequence done");
        seq = 1'b0;
        for (i = 0; i + 2 < n_outs && i + 2 < 64; i = i + 1)
            if (outs[i] == 8'h80 && outs[i+1] == 8'h0A && outs[i+2] == 8'h02) seq = 1'b1;
        chk(seq, "pins go 0x80, 0x0A, 0x02 (pins 0 and 4 masked): set, toggle, clear");

        $display("[timing unit]");
        get_line(got);
        p = 4; num(d);
        chk(got && len > 4 && line[0] == "a", "the program reports the tick it armed");
        $display("        trigger rose at tick %0d, armed for %0d", trig_tick, d);
        chk(trig_tick == d, "trigger 0 rises on exactly that tick");
        chk(trig_high == 10, "and stays high for the 10 ticks the program asked for");

        get_line(got);
        chk(got && line_is("cap?", 4), "the program waits for an input edge");
        repeat (100) @(posedge clk);
        edge_tick = now;
        ui_in[5] = 1'b1;
        repeat (20) @(posedge clk);
        ui_in[5] = 1'b0;
        get_line(got);
        p = 4; num(ch); num(rising); num(ts);
        $display("        edge made at tick %0d, stamped %0d", edge_tick[26:0], ts);
        chk(got && ch == 5 && rising == 1, "the event is channel 5, rising");
        // The bench moves the pin just after a clock edge, so the latency is
        // exact: two synchroniser flops plus the edge detector, 3 ticks.
        chk(ts == edge_tick[26:0] + 3,
            "its timestamp is the edge's tick plus the fixed 3-tick input latency");

        get_line(got);
        chk(got && line_is("mark Y", 6), "a software mark comes out of the same queue with its tick");
        get_line(got);
        chk(got && line_is("ram Y", 5), "1 KB written to RAM reads back intact");
        get_line(got);
        chk(got && line_is("done", 4), "the program finished");

        p = 0;
        while (!dut.u_soc.g_cpu.u_core.halted && p < 100000) begin @(posedge clk); p = p + 1; end
        chk(dut.u_soc.g_cpu.u_core.halted === 1'b1 && dut.u_soc.g_cpu.u_core.illegal_q === 1'b0,
            "main() returned, the core halted, no illegal instruction");
        chk(u_psram.violations == 0, "RAM timing held throughout");
        $display("        (%0d clocks = %0.1f ms at 50 MHz)", cyc, cyc * 0.00002);

        $display("\n%0d checks, %0d failures", checks, errors);
        if (errors == 0) $display("MICROCONTROLLER TEST PASSED\n");
        else             $display("MICROCONTROLLER TEST FAILED\n");
        $finish;
    end

    initial begin
        #20_000_000;            // 2M clocks; a passing run takes about 250k
        $display("  FAIL  timed out\nMICROCONTROLLER TEST FAILED");
        $finish;
    end
endmodule
