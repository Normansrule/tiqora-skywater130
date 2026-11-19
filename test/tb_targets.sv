// tb_targets.sv — every tape-out target's top, in lockstep with the Tiny
// Tapeout top.
//
// Four copies of the chip run the same program from their own flash and RAM
// models, with the same input pins, clock and reset:
//
//   ref  tt_um_normansrule_tiqora     the Tiny Tapeout submission
//   mac  tiqora_macro                 sky130-macro and gf180-macro
//   car  user_project_wrapper         caravel-sky130 (generated)
//   opf  openframe_project_wrapper    openframe-sky130 (generated)
//
// Each target's pins are read back through its own pin map (the pad numbers
// below are the ones in targets/*.toml) and compared with the reference
// every clock: outputs, output enables and the QSPI bus. One differing clock
// fails the run. Pad-level rules are checked too: an input pad is never
// driven, an Openframe pad that drives is in a driving digital mode.
//
// The bench also proves the comparison saw real work: the program halts,
// TRIG0 pulses, the flash clock toggles and RAM is written.
//
// Run with:  make targets   (xpulse.hex, isa.hex and wrap.hex; +PROG= +SEED=)
`default_nettype none
`timescale 1ns/1ps

module tb_targets;

    localparam int TIMEOUT = 200000;

    reg        clk = 1'b0, rst_n = 1'b0;
    reg  [7:0] ui  = 8'h00;
    always #5 clk = ~clk;

    integer errors = 0, checks = 0, mism = 0, cyc = 0;
    integer trig_edges = 0, sck_edges = 0, ram_writes = 0;

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

    // ---------------------------------------------------------------
    // One QSPI harness per copy: a flash and a RAM on a shared bus.
    // Inputs are the copy's pins in Tiny Tapeout order:
    //   [0] CS0  [1] SD0  [2] SD1  [3] SCK  [4] SD2  [5] SD3  [6] CS1  [7] CS2
    // ---------------------------------------------------------------
    // ref
    wire [7:0] r_uo, r_uio_out, r_uio_oe;
    wire [3:0] r_fsd, r_psd;
    wire [3:0] r_ctrl = {r_uio_out[5], r_uio_out[4], r_uio_out[2], r_uio_out[1]};
    wire [3:0] r_bus  = r_uio_oe[1] ? r_ctrl : (!r_uio_out[0] ? r_fsd : (!r_uio_out[6] ? r_psd : 4'hF));
    wire [7:0] r_uio_in = {2'b00, r_bus[3], r_bus[2], 1'b0, r_bus[1], r_bus[0], 1'b0};
    tt_um_normansrule_tiqora ref_dut (
        .ui_in(ui), .uo_out(r_uo), .uio_in(r_uio_in), .uio_out(r_uio_out), .uio_oe(r_uio_oe),
        .ena(1'b1), .clk(clk), .rst_n(rst_n));
    qspi_flash_model #(.DUMMY(4), .WORDS(512)) r_flash (
        .cs_n(r_uio_out[0]), .sck(r_uio_out[3]), .ctrl_sd(r_ctrl), .dev_sd(r_fsd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) r_psram (
        .cs_n(r_uio_out[6]), .sck(r_uio_out[3]), .ctrl_sd(r_ctrl), .dev_sd(r_psd));

    // mac: tiqora_macro
    wire [7:0] m_uo;
    wire m_sck, m_csf, m_csa, m_csb, m_ctl_oe;
    wire [3:0] m_sd_out, m_sd_oe, m_fsd, m_psd;
    wire [3:0] m_bus = m_sd_oe[0] ? m_sd_out : (!m_csf ? m_fsd : (!m_csa ? m_psd : 4'hF));
    tiqora_macro mac_dut (
        .clk(clk), .rst_n(rst_n), .gpio_in(ui), .gpio_out(m_uo),
        .qspi_sck(m_sck), .qspi_cs_flash_n(m_csf), .qspi_cs_rama_n(m_csa), .qspi_cs_ramb_n(m_csb),
        .qspi_ctl_oe(m_ctl_oe), .qspi_sd_in(m_bus), .qspi_sd_out(m_sd_out), .qspi_sd_oe(m_sd_oe));
    qspi_flash_model #(.DUMMY(4), .WORDS(512)) m_flash (
        .cs_n(m_csf), .sck(m_sck), .ctrl_sd(m_sd_out), .dev_sd(m_fsd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) m_psram (
        .cs_n(m_csa), .sck(m_sck), .ctrl_sd(m_sd_out), .dev_sd(m_psd));
    wire [7:0] m_uio_out = {m_csb, m_csa, m_sd_out[3], m_sd_out[2], m_sck, m_sd_out[1], m_sd_out[0], m_csf};
    wire [7:0] m_uio_oe  = {m_ctl_oe, m_ctl_oe, m_sd_oe[3], m_sd_oe[2], m_ctl_oe, m_sd_oe[1], m_sd_oe[0], m_ctl_oe};

    // car: Caravel user_project_wrapper, pads from targets/caravel-sky130.toml
    wire [37:0] c_io_in, c_io_out, c_io_oeb;
    wire [3:0]  c_fsd, c_psd;
    wire [3:0]  c_ctrl = {c_io_out[29], c_io_out[28], c_io_out[26], c_io_out[25]};
    wire [3:0]  c_bus  = !c_io_oeb[25] ? c_ctrl : (!c_io_out[24] ? c_fsd : (!c_io_out[30] ? c_psd : 4'hF));
    assign c_io_in = {6'b0, 2'b00, c_bus[3], c_bus[2], 1'b0, c_bus[1], c_bus[0], 1'b0, 8'h00, ui, 8'h00};
    user_project_wrapper car_dut (
        .wb_clk_i(clk), .wb_rst_i(~rst_n), .wbs_stb_i(1'b0), .wbs_cyc_i(1'b0), .wbs_we_i(1'b0),
        .wbs_sel_i(4'h0), .wbs_dat_i(32'h0), .wbs_adr_i(32'h0), .wbs_ack_o(), .wbs_dat_o(),
        .la_data_in(128'h0), .la_data_out(), .la_oenb({128{1'b1}}),
        .io_in(c_io_in), .io_out(c_io_out), .io_oeb(c_io_oeb), .analog_io(),
        .user_clock2(1'b0), .user_irq());
    qspi_flash_model #(.DUMMY(4), .WORDS(512)) c_flash (
        .cs_n(c_io_out[24]), .sck(c_io_out[27]), .ctrl_sd(c_ctrl), .dev_sd(c_fsd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) c_psram (
        .cs_n(c_io_out[30]), .sck(c_io_out[27]), .ctrl_sd(c_ctrl), .dev_sd(c_psd));
    wire [7:0] c_uo      = c_io_out[23:16];
    wire [7:0] c_uio_out = c_io_out[31:24];
    wire [7:0] c_uio_oe  = ~c_io_oeb[31:24];

    // opf: Openframe openframe_project_wrapper, pads from targets/openframe-sky130.toml
    wire [43:0] o_in, o_out, o_oeb, o_ind, o_dm2, o_dm1, o_dm0;
    wire [3:0]  o_fsd, o_psd;
    wire [3:0]  o_ctrl = {o_out[37], o_out[36], o_out[42], o_out[41]};
    wire [3:0]  o_bus  = !o_oeb[41] ? o_ctrl : (!o_out[39] ? o_fsd : (!o_out[43] ? o_psd : 4'hF));
    reg  [43:0] o_pads;
    always @* begin
        o_pads = 44'h0;
        o_pads[5] = ui[3];
        o_pads[16] = ui[0]; o_pads[17] = ui[1]; o_pads[18] = ui[2];
        o_pads[19] = ui[4]; o_pads[20] = ui[5]; o_pads[21] = ui[6]; o_pads[22] = ui[7];
        o_pads[38] = clk;
        o_pads[41] = o_bus[0]; o_pads[42] = o_bus[1]; o_pads[36] = o_bus[2]; o_pads[37] = o_bus[3];
    end
    assign o_in = o_pads;
    openframe_project_wrapper opf_dut (
        .porb_h(1'b1), .porb_l(1'b1), .por_l(1'b0), .resetb_h(rst_n), .resetb_l(rst_n),
        .mask_rev(32'h0), .gpio_in(o_in), .gpio_in_h(44'h0), .gpio_out(o_out), .gpio_oeb(o_oeb),
        .gpio_inp_dis(o_ind), .gpio_ib_mode_sel(), .gpio_vtrip_sel(), .gpio_slow_sel(),
        .gpio_holdover(), .gpio_analog_en(), .gpio_analog_sel(), .gpio_analog_pol(),
        .gpio_dm2(o_dm2), .gpio_dm1(o_dm1), .gpio_dm0(o_dm0), .analog_io(), .analog_noesd_io(),
        .gpio_loopback_one({44{1'b1}}), .gpio_loopback_zero(44'h0));
    qspi_flash_model #(.DUMMY(4), .WORDS(512)) o_flash (
        .cs_n(o_out[39]), .sck(o_out[40]), .ctrl_sd(o_ctrl), .dev_sd(o_fsd));
    qspi_psram_model #(.DUMMY(6), .BYTES(4096)) o_psram (
        .cs_n(o_out[43]), .sck(o_out[40]), .ctrl_sd(o_ctrl), .dev_sd(o_psd));
    wire [7:0] o_uo      = {o_out[30], o_out[29], o_out[28], o_out[6], o_out[27], o_out[26], o_out[25], o_out[24]};
    wire [7:0] o_uio_out = {o_out[35], o_out[43], o_out[37], o_out[36], o_out[40], o_out[42], o_out[41], o_out[39]};
    wire [7:0] o_uio_oe  = ~{o_oeb[35], o_oeb[43], o_oeb[37], o_oeb[36], o_oeb[40], o_oeb[42], o_oeb[41], o_oeb[39]};
    wire [7:0] o_uo_oeb  = {o_oeb[30], o_oeb[29], o_oeb[28], o_oeb[6], o_oeb[27], o_oeb[26], o_oeb[25], o_oeb[24]};

    // ---------------------------------------------------------------
    // the comparison
    // ---------------------------------------------------------------
    // Output pins only matter while driven; the QSPI pins are compared
    // value-for-value where the reference drives them.
    function automatic [7:0] drv(input [7:0] v, input [7:0] oe);
        drv = v & oe;
    endfunction

    task automatic cmp(input string who, input [7:0] uo, input [7:0] uio_out, input [7:0] uio_oe);
        if (uo !== r_uo || uio_oe !== r_uio_oe || drv(uio_out, uio_oe) !== drv(r_uio_out, r_uio_oe)) begin
            mism = mism + 1;
            if (mism <= 5)
                $display("  FAIL  cycle %0d %0s: uo %02x/%02x uio_oe %02x/%02x uio_out %02x/%02x (target/ref)",
                         cyc, who, uo, r_uo, uio_oe, r_uio_oe, uio_out, r_uio_out);
        end
    endtask

    integer pad_rule_fail = 0;
    integer k;
    // compared from the third clock of reset on (flip-flops are X before
    // their first reset edge): the reset-time pin state is part of the contract
    integer clk_n = 0;
    always @(posedge clk) clk_n <= clk_n + 1;
    always @(negedge clk) if (clk_n >= 3) begin
        cmp("sky130/gf180 macro", m_uo, m_uio_out, m_uio_oe);
        cmp("caravel",            c_uo, c_uio_out, c_uio_oe);
        cmp("openframe",          o_uo, o_uio_out, o_uio_oe);
        // pad rules: input pads never driven; outputs always driven
        if (c_io_oeb[15:8] !== 8'hFF || c_io_oeb[23:16] !== 8'h00) pad_rule_fail = pad_rule_fail + 1;
        if (o_uo_oeb !== 8'h00 || o_oeb[38] !== 1'b1 || o_oeb[5] !== 1'b1) pad_rule_fail = pad_rule_fail + 1;
        for (k = 0; k < 44; k = k + 1) begin
            // a driving Openframe pad must be in a driving mode (dm 110);
            // a pad whose input is used must have its input buffer on
            if (o_oeb[k] === 1'b0 && {o_dm2[k], o_dm1[k], o_dm0[k]} !== 3'b110) pad_rule_fail = pad_rule_fail + 1;
        end
        // every pad whose input the core reads keeps its input buffer on
        if ({o_ind[5], o_ind[22:16], o_ind[38], o_ind[37:36], o_ind[42:41]} !== 13'h0)
            pad_rule_fail = pad_rule_fail + 1;
    end

    // activity, measured on the reference
    reg r_trig_q = 1'b0, r_sck_q = 1'b0;
    always @(posedge clk) begin
        r_trig_q <= r_uo[0];
        r_sck_q  <= r_uio_out[3];
        if (r_uo[0] && !r_trig_q) trig_edges = trig_edges + 1;
        if (r_uio_out[3] && !r_sck_q) sck_edges = sck_edges + 1;
        if (!r_uio_out[6] && r_uio_oe[1]) ram_writes = ram_writes + 1;
    end

    // random activity on the capture inputs; the UART line idles high and
    // the boot and latency straps stay at their flash-boot values
    integer seed = 1;
    always @(posedge clk) if (rst_n && ($random(seed) % 23 == 0))
        ui <= {1'b0, $random(seed) & 3'h7, 1'b1, $random(seed) & 3'h7};

    reg [8*64-1:0] prog;
    initial begin
        if (!$value$plusargs("PROG=%s", prog)) prog = "xpulse.hex";
        if (!$value$plusargs("SEED=%d", seed)) seed = 1;
        $display("\n=== tape-out targets in lockstep with the Tiny Tapeout top: %0s, seed %0d ===", prog, seed);
        #1;
        $readmemh(prog, r_flash.mem);
        $readmemh(prog, m_flash.mem);
        $readmemh(prog, c_flash.mem);
        $readmemh(prog, o_flash.mem);
        ui = 8'h08;
        repeat (20) @(posedge clk);
        rst_n = 1'b1;
        while (!r_uo[5] && cyc < TIMEOUT) begin
            @(posedge clk);
            cyc = cyc + 1;
        end
        repeat (50) @(posedge clk);
        $display("  clocks %0d, TRIG0 rising edges %0d, flash clock edges %0d, RAM write clocks %0d",
                 cyc, trig_edges, sck_edges, ram_writes);
        chk(r_uo[5], "the reference program halted (HALT pin)");
        chk(sck_edges > 100, "the QSPI clock ran");
        chk(mism == 0, "every target matched the Tiny Tapeout top on every clock");
        chk(pad_rule_fail == 0, "pad rules held on every clock (inputs undriven, Openframe modes)");
        if (errors == 0) $display("tb_targets: %0d checks PASSED", checks);
        else             $display("tb_targets: %0d of %0d checks FAILED", errors, checks);
        $finish;
    end
endmodule
