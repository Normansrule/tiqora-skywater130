// tb_basys3.sv — the whole Basys 3 design, simulated as the board runs it:
// 100 MHz oscillator, switches, buttons, the USB serial pins, and the QSPI
// memory emulated in block RAM. Three modes (+MODE=...):
//   selftest  the C self-test from emulated flash; its data and stack live
//             in emulated RAM A. Every printed character is checked.
//   boot      switch 7 up through reset: the bootloader prints TP>, the same
//             program arrives over the USB serial pin into emulated RAM and
//             runs there. Every printed character is checked.
//   demo      basys3_demo.c: banner, a clean BTNL press and release, a
//             bouncing BTNR press that must be reported once, and an echo.
`default_nettype none
`timescale 1ns/1ps
module tb_basys3;
    localparam int PROG_DIV = 8, BOOT_DIV = 32;        // UART clocks per bit, at 50 MHz
    reg clk = 0, btnC = 0, btnL = 0, btnR = 0, btnU = 0, RsRx = 1;
    reg [15:0] sw = 16'h0000;
    wire [15:0] led; wire [6:0] seg; wire dp; wire [3:0] an; wire RsTx; wire [7:0] JA;
    always #5 clk = ~clk;                               // 100 MHz

    basys3_top #(.USE_PMOD(1'b0), .FLASH_INIT("sim_flash.mem")) dut (
        .clk(clk), .btnC(btnC), .btnL(btnL), .btnR(btnR), .btnU(btnU), .sw(sw), .led(led),
        .seg(seg), .dp(dp), .an(an), .RsRx(RsRx), .RsTx(RsTx), .JA(JA));
    defparam dut.u_chip.u_soc.u_periph.DIV_RESET = BOOT_DIV;

    integer errors = 0, checks = 0;
    task chk(input cond, input [8*80:1] msg);
        begin checks = checks + 1;
              if (cond) $display("  ok    %0s", msg); else begin errors = errors + 1; $display("  FAIL  %0s", msg); end end
    endtask

    // ---- the PC's serial terminal ----
    reg [7:0] rx_buf [0:4095]; integer rx_n = 0; integer rx_div = PROG_DIV;
    always begin : terminal
        integer i; reg [7:0] b;
        @(posedge dut.clk50);
        if (dut.rst_n && RsTx === 1'b0) begin
            repeat (rx_div / 2) @(posedge dut.clk50);
            for (i = 0; i < 8; i = i + 1) begin repeat (rx_div) @(posedge dut.clk50); b[i] = RsTx; end
            repeat (rx_div) @(posedge dut.clk50);
            if (rx_n < 4096) rx_buf[rx_n] = b;
            rx_n = rx_n + 1;
        end
    end
    task send(input [7:0] b, input integer div);
        integer i;
        begin RsRx = 0; repeat (div) @(posedge dut.clk50);
              for (i = 0; i < 8; i = i + 1) begin RsRx = b[i]; repeat (div) @(posedge dut.clk50); end
              RsRx = 1; repeat (div) @(posedge dut.clk50); end
    endtask
    function automatic bit printed(input string s);   // does the text so far contain s?
        string all; all = "";
        for (int i = 0; i < rx_n && i < 4096; i++) all = {all, string'(rx_buf[i])};
        for (int i = 0; i + s.len() <= all.len(); i++) if (all.substr(i, i + s.len() - 1) == s) return 1;
        return 0;
    endfunction
    task wait_for(input string s, input integer max_clk);
        // search the transcript every 500 clocks, not every clock: text arrives at
        // serial speed, and rebuilding the string each cycle made this the slowest part
        integer n; begin n = 0; while (!printed(s) && n < max_clk) begin repeat (500) @(posedge dut.clk50); n = n + 500; end end
    endtask
    task show;
        begin $write("        terminal: \"");
              for (int i = 0; i < rx_n && i < 4096; i++) if (rx_buf[i] == 8'h0a) $write("\\n"); else $write("%c", rx_buf[i]);
              $display("\""); end
    endtask
    task wait_halt;
        integer n; begin n = 0;
              while (dut.rst_n !== 1'b1) @(posedge dut.clk50);          // out of reset first: before that the flag is X
              while (dut.u_chip.u_soc.g_cpu.u_core.halted !== 1'b1 && n < 3000000) begin @(posedge dut.clk50); n = n + 1; end
              repeat (40 * PROG_DIV) @(posedge dut.clk50);
              chk(dut.u_chip.u_soc.g_cpu.u_core.halted === 1'b1, "main() returned and crt0 halted");
              chk(dut.u_chip.u_soc.g_cpu.u_core.illegal_q === 1'b0, "no illegal instruction"); end
    endtask

    localparam string SELFTEST = "Hi from C\ndata 42\nbss 0\nmul -69104\ndiv -22\nmod -2\nfib 144\nfn 42\nwait Y\ndone\n";
    task expect_selftest;
        string got; begin got = "";
              for (int i = 0; i < rx_n && i < 4096; i++) got = {got, string'(rx_buf[i])};
              show; chk(got == SELFTEST, "every character the program printed matches"); end
    endtask

    reg [31:0] img [0:4095]; integer nw, k; reg [31:0] w; string mode;
    initial begin
        if (!$value$plusargs("MODE=%s", mode)) mode = "selftest";
        $display("\n=== Tiqora on the Basys 3 (simulated board: %0s) ===", mode);
        if (mode == "selftest") begin
            wait_halt; expect_selftest;
            chk(dut.g_emu.u_mem.flash_cont === 1'b1, "the emulated flash was put into continuous read by the chip");
            chk(dut.g_emu.u_mem.qpi_a === 1'b1 && dut.g_emu.u_mem.qpi_b === 1'b1, "both emulated RAMs were put into QPI mode by the chip");
        end else if (mode == "boot") begin
            sw[7] = 1'b1;                                         // BOOT up through the power-on reset
            rx_div = BOOT_DIV; wait_for("TP>", 400000);
            chk(printed("TP>"), "bootloader prompt TP> on the USB serial port");
            for (int i = 0; i < 4096; i++) img[i] = 32'hxxxx_xxxx;
            $readmemh("sim_ram.hex", img);
            nw = 0; while (nw < 4096 && img[nw] !== 32'hxxxx_xxxx) nw = nw + 1;
            rx_n = 0;
            for (k = 0; k < 4; k = k + 1) send((4 * nw) >> (8 * k), BOOT_DIV);
            for (int i = 0; i < nw; i++) begin w = img[i]; for (k = 0; k < 4; k = k + 1) send(w[8*k +: 8], BOOT_DIV); end
            wait_for("K", 200000);
            chk(rx_n >= 2 && rx_buf[1] == "K", "program accepted (checksum + K)");
            repeat (12 * BOOT_DIV) @(posedge dut.clk50);
            rx_n = 0; rx_div = PROG_DIV;
            wait_halt; expect_selftest;
            chk(dut.u_chip.u_soc.g_cpu.u_core.pc[31:28] == 4'h1, "the program ran from emulated RAM");
        end else begin
            wait_for("type something.\n", 600000);
            chk(printed("Tiqora on Basys 3"), "demo banner on the USB serial port");
            btnL = 1; repeat (3000) @(posedge dut.clk50); btnL = 0;
            wait_for("BTNL released", 600000);
            chk(printed("BTNL pressed ") && printed("BTNL released"), "BTNL press and release, both timestamped");
            for (int b = 0; b < 6; b++) begin btnR = ~btnR; repeat (13) @(posedge dut.clk50); end   // bounce
            // held long enough for the program to drain the event queue, as a
            // real press does (~100 ms); a bounce burst briefly fills the queue
            btnR = 1; repeat (40000) @(posedge dut.clk50); btnR = 0;
            wait_for("BTNR released", 600000);
            begin : count
                string all; integer cp, cr; all = ""; cp = 0; cr = 0;
                for (int i = 0; i < rx_n && i < 4096; i++) all = {all, string'(rx_buf[i])};
                for (int i = 0; i + 12 <= all.len(); i++) if (all.substr(i, i + 11) == "BTNR pressed") cp++;
                for (int i = 0; i + 13 <= all.len(); i++) if (all.substr(i, i + 12) == "BTNR released") cr++;
                chk(cp == 1, "a bouncing BTNR press is reported exactly once (debounced by timestamp)");
                chk(cr == 1, "and its release exactly once");
            end
            send("x", PROG_DIV); wait_for("you typed 'x'", 400000);
            chk(printed("you typed 'x'"), "a typed character is echoed");
            chk(dut.led[0] !== 1'bx, "LED 0 is driven by the program");
            show;
        end
        $display("\n%0d checks, %0d failures", checks, errors);
        if (errors == 0) $display("BASYS 3 SIMULATION PASSED\n"); else $display("BASYS 3 SIMULATION FAILED\n");
        $finish;
    end
endmodule
