// tb_run.sv — run any compiled program on the simulated Tiqora and show
// its UART output live, like a serial terminal on a real board.
//
//   cd test && make run PROG=../sw/examples/hello.c
//
// The program is built for flash with BAUD_DIV=8, loaded into the flash
// model, and the chip runs from reset exactly as silicon would: the memory
// wake-up sequence, fetches over QSPI, everything. Output is printed as each
// byte arrives. The run ends when main() returns (HALT) or after +MAXCLK
// clocks (default 20 million = 0.4 s of chip time at 50 MHz).
`default_nettype none
`timescale 1ns/1ps

module tb_run;
    integer DIV = 8;                       // UART clocks per bit; +DIV=434 for the reset default
    reg        clk = 1'b0, rst_n = 1'b0, ena = 1'b1;
    reg  [7:0] ui_in = 8'h08;
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
    qspi_flash_model #(.DUMMY(4), .WORDS(16384)) u_flash (
        .cs_n(cs_f), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(flash_sd));
    qspi_psram_model #(.DUMMY(6), .BYTES(1 << 20)) u_psram (
        .cs_n(cs_r), .sck(sck), .ctrl_sd({uio_out[5], uio_out[4], uio_out[2], uio_out[1]}), .dev_sd(psram_sd));

    // A simulated SPI flash (Winbond W25Q128) on the software-SPI pins of
    // sw/tp_spi.h, enabled with +spi_flash: SCK uo_out[1], MOSI uo_out[2],
    // CS uo_out[3], MISO ui_in[4]. It answers the JEDEC ID command 0x9F with
    // EF 40 18, changing MISO on falling clock edges (SPI mode 0).
    reg  [7:0] spi_cmd; reg [23:0] spi_out; integer spi_bits = 0;
    wire spi_sck = uo_out[1], spi_mosi = uo_out[2], spi_cs = uo_out[3];
    always @(negedge spi_cs) if ($test$plusargs("spi_flash")) begin spi_bits = 0; spi_cmd = 0; end
    always @(posedge spi_sck) if ($test$plusargs("spi_flash") && !spi_cs) begin
        if (spi_bits < 8) spi_cmd = {spi_cmd[6:0], spi_mosi};
        spi_bits = spi_bits + 1;
    end
    always @(negedge spi_sck) if ($test$plusargs("spi_flash") && !spi_cs) begin
        if (spi_bits == 8) spi_out = (spi_cmd == 8'h9F) ? 24'hEF4018 : 24'h000000;
        if (spi_bits >= 8) begin ui_in[4] = spi_out[23]; spi_out = {spi_out[22:0], 1'b0}; end
    end

    integer n = 0, maxclk, nbytes = 0;
    reg [8*256:1] hexfile, ramhex;

    // Pin monitor: what a scope on the board would see. Pulses on uo_out[0]
    // (TRIG0 in its built-in function) are counted at the PIN, after the
    // GPIO_SEL mux, so a trigger that fires internally but is not routed to
    // the pin counts as zero.
    integer trig0_pulses = 0, trig0_width = 0, trig0_cur = 0;
    integer trig1_pulses = 0, trig1_cur = 0;
    always @(posedge clk) if (rst_n) begin
        if (uo_out[1] === 1'b1) trig1_cur = trig1_cur + 1;
        else if (trig1_cur != 0) begin trig1_pulses = trig1_pulses + 1; trig1_cur = 0; end
    end

    // +PROFILE: clocks spent in each core state, instructions fetched, and the
    // length of every instruction fetch (request to data), for performance work.
    integer prof [0:7];
    integer mix [0:6];
    initial for (int k = 0; k < 7; k++) mix[k] = 0;
    integer prof_instr = 0, fetch_len = 0, fetch_sum = 0, fetch_min = 1 << 30, fetch_max = 0;
    initial for (int k = 0; k < 8; k++) prof[k] = 0;
    always @(posedge clk) if (rst_n && !dut.u_soc.g_cpu.u_core.halted) begin
        prof[dut.u_soc.g_cpu.u_core.state] = prof[dut.u_soc.g_cpu.u_core.state] + 1;
        if (dut.u_soc.g_cpu.u_core.imem_req) fetch_len = fetch_len + 1;
        if (dut.u_soc.g_cpu.u_core.imem_rvalid) begin
            prof_instr = prof_instr + 1;
            begin : classify   // dynamic mix by opcode (shift = funct3 001/101 of OP/OP-IMM)
                reg [31:0] w; w = dut.u_soc.g_cpu.u_core.imem_rdata;
                case (w[6:0])
                    7'h37, 7'h17: mix[0] = mix[0] + 1;                                  // LUI, AUIPC
                    7'h13, 7'h33: if (w[13:12] == 2'b01) mix[1] = mix[1] + 1;           // shifts
                                  else mix[0] = mix[0] + 1;                             // other ALU (incl. SLT)
                    7'h03: mix[2] = mix[2] + 1;  7'h23: mix[3] = mix[3] + 1;            // load, store
                    7'h63: mix[4] = mix[4] + 1;  7'h6f, 7'h67: mix[5] = mix[5] + 1;     // branch, jumps
                    default: mix[6] = mix[6] + 1;
                endcase
            end
            fetch_sum = fetch_sum + fetch_len;
            if (fetch_len < fetch_min) fetch_min = fetch_len;
            if (fetch_len > fetch_max) fetch_max = fetch_len;
            fetch_len = 0;
        end
    end
    always @(posedge clk) if (rst_n) begin
        if (uo_out[0] === 1'b1) trig0_cur = trig0_cur + 1;
        else if (trig0_cur != 0) begin
            trig0_pulses = trig0_pulses + 1;
            if (trig0_pulses == 1) trig0_width = trig0_cur;
            trig0_cur = 0;
        end
    end
    always begin : terminal
        integer i; reg [7:0] b;
        @(posedge clk);
        if (rst_n && uo_out[4] === 1'b0) begin
            repeat (DIV / 2) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin repeat (DIV) @(posedge clk); b[i] = uo_out[4]; end
            repeat (DIV) @(posedge clk);
            $write("%c", b); $fflush();
            nbytes = nbytes + 1;
        end
    end

    initial begin
        if (!$value$plusargs("MAXCLK=%d", maxclk)) maxclk = 20000000;
        if (!$value$plusargs("DIV=%d", DIV)) DIV = 8;
        if ($value$plusargs("RAMHEX=%s", ramhex)) begin
            // run from RAM: the image the bootloader would leave at 0x1000_0000,
            // entered through a two-instruction jump at the flash reset address
            $readmemh(ramhex, u_psram.mem);
            u_flash.mem[0] = 32'h100002b7;        // lui  x5, 0x10000
            u_flash.mem[1] = 32'h00028067;        // jalr x0, 0(x5)
        end else begin
            if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "run.hex";
            $readmemh(hexfile, u_flash.mem);
        end
        $display("--- Tiqora (simulated RTL, 50 MHz) ---");
        repeat (10) @(posedge clk); rst_n = 1'b1;
        while (!dut.u_soc.g_cpu.u_core.halted && n < maxclk) begin @(posedge clk); n = n + 1; end
        repeat (40 * DIV) @(posedge clk);
        $display("--- %s after %0d clocks (%0.2f ms at 50 MHz), %0d bytes printed%s ---",
                 dut.u_soc.g_cpu.u_core.halted ? "main() returned" : "stopped (MAXCLK)",
                 n, n * 0.00002, nbytes,
                 dut.u_soc.g_cpu.u_core.illegal_q ? ", ILLEGAL instruction seen" : "");
        if ($test$plusargs("PROFILE")) begin : profile
            integer tot; tot = 0;
            for (int k = 0; k < 8; k++) tot = tot + prof[k];
            $display("--- profile: %0d instructions in %0d clocks = %0.2f clocks per instruction", prof_instr, tot, 1.0 * tot / prof_instr);
            $display("    FETCH %5.1f%%  ALIGN %5.1f%%  PASS %5.1f%%  MEM %5.1f%%  SHIFT %5.1f%%  XP %5.1f%%  TWAIT %5.1f%%",
                     100.0*prof[0]/tot, 100.0*prof[1]/tot, 100.0*prof[2]/tot, 100.0*prof[5]/tot, 100.0*prof[7]/tot, 100.0*prof[6]/tot, 100.0*prof[3]/tot);
            $display("    fetch request-to-data: min %0d, mean %0.1f, max %0d clocks", fetch_min, 1.0 * fetch_sum / prof_instr, fetch_max);
            $display("    mix: ALU/LUI/AUIPC %0.1f%%  shift %0.1f%%  load %0.1f%%  store %0.1f%%  branch %0.1f%%  jump %0.1f%%  other %0.1f%%",
                     100.0*mix[0]/prof_instr, 100.0*mix[1]/prof_instr, 100.0*mix[2]/prof_instr, 100.0*mix[3]/prof_instr,
                     100.0*mix[4]/prof_instr, 100.0*mix[5]/prof_instr, 100.0*mix[6]/prof_instr);
        end
        $display("--- pins: TRIG0 pulses=%0d first-width=%0d clocks, TRIG1 pulses=%0d, uo_out[7]=%b, ran from %s ---",
                 trig0_pulses, trig0_width, trig1_pulses, uo_out[7], dut.u_soc.g_cpu.u_core.pc[31:28] == 4'h1 ? "RAM" : "flash");
        $finish;
    end
endmodule
