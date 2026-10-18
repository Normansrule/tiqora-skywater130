// tb_pins.sv - post-synthesis check of the Basys 3 netlist, board pins only.
// The netlist (Yosys synth_xilinx, the same script as the bitstream) has the
// C self-test baked into the emulated flash. Nothing inside the chip is
// probed: the transcript comes from RsTx, halt and illegal from the LEDs.
// +EXPECT=<file> compares against that file instead of the self-test
// transcript (make netlist-modes: the CPU / GPU / TPU demo).
`timescale 1ns/1ps
module tb_pins;
    reg clk = 0, btnC = 0, btnL = 0, btnR = 0, btnU = 0, RsRx = 1;
    reg [15:0] sw = 16'h0000;
    wire [15:0] led; wire [6:0] seg; wire dp; wire [3:0] an; wire RsTx; wire [7:0] JA;
    always #5 clk = ~clk;                                    // 100 MHz board oscillator
    basys3_top dut (.clk(clk), .btnC(btnC), .btnL(btnL), .btnR(btnR), .btnU(btnU), .sw(sw),
                    .led(led), .seg(seg), .dp(dp), .an(an), .RsRx(RsRx), .RsTx(RsTx), .JA(JA));

    localparam integer DIV = 8;                              // UART clocks per bit at 50 MHz (BAUD_DIV=8)
    localparam integer BIT_NS = DIV * 20;
    localparam string SELFTEST = "Hi from C\ndata 42\nbss 0\nmul -69104\ndiv -22\nmod -2\nfib 144\nfn 42\nwait Y\ndone\n";
    string got = "", want = SELFTEST, path; integer fails = 0, checks = 0;
    initial if ($value$plusargs("EXPECT=%s", path)) begin : load
        integer fd, c; reg [7:0] cb; want = "";
        fd = $fopen(path, "r");
        if (fd == 0) $fatal(1, "cannot open %s", path);
        c = $fgetc(fd);
        while (c != -1) begin cb = c[7:0]; want = {want, string'(cb)}; c = $fgetc(fd); end
        $fclose(fd);
    end

    // UART receiver on the RsTx pin, timed in nanoseconds from the start-bit edge
    initial begin : rx
        reg [7:0] b; integer i;
        #2000;
        forever begin
            @(negedge RsTx);
            #(BIT_NS + BIT_NS / 2);
            for (i = 0; i < 8; i = i + 1) begin b[i] = RsTx; #(BIT_NS); end
            got = {got, string'(b)};
        end
    end

    task chk(input bit ok, input string what);
        begin checks = checks + 1; if (!ok) fails = fails + 1;
              $display("  %s  %s", ok ? "ok  " : "FAIL", what); end
    endtask

    initial begin : main
        integer n; n = 0;
        // led[5] = uo_out[5] HALT, led[6] = uo_out[6] ILLEGAL, led[15] = reset released
        while (!(led[15] === 1'b1 && led[5] === 1'b1) && n < 12_000_000) begin #1000; n = n + 1000; end
        #(BIT_NS * 200);
        $display("  terminal: %s", got);
        chk(led[15] === 1'b1, "reset released (LED 15)");
        chk(led[5] === 1'b1, "main() returned and crt0 halted (LED 5 = HALT)");
        chk(led[6] === 1'b0, "no illegal instruction (LED 6 = ILLEGAL)");
        if (want == SELFTEST) chk(got == want, "every character on the USB serial pin matches the self-test transcript");
        else                  chk(got == want, {"every character on the USB serial pin matches ", path});
        $display("%0d checks, %0d failures", checks, fails);
        if (fails == 0) $display("BASYS 3 NETLIST TEST PASSED"); else $display("BASYS 3 NETLIST TEST FAILED");
        if (fails != 0) $fatal(1, "netlist test failed");
        $finish;
    end
endmodule
