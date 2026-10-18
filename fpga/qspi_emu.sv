// qspi_emu.sv — the Tiny Tapeout QSPI Pmod (one W25Q128 flash, two APS6404L
// RAMs), emulated in FPGA block RAM, so Tiqora runs on a bare FPGA board.
//
// It follows the same rules as the strict simulation models in
// test/qspi_model.sv, which follow the datasheets:
//   flash  powers up in plain SPI. 0xEB (Fast Read Quad I/O, one bit per
//          clock) is followed by 24 address bits and a mode byte, four
//          wide; mode 10xx_xxxx keeps it in continuous read, where the next
//          transaction starts straight with the address. 4 dummy clocks,
//          then data streams out, address incrementing, until deselected.
//   RAMs   power up in plain SPI and ignore everything but 0x35 (enter QPI).
//          In QPI: 0xEB read (6 dummy clocks), 0x38 write, 0xF5 exit QPI.
// So the emulator only works if Tiqora's wake-up sequence does — it is a
// test of the chip, not a shortcut around it.
//
// Timing. Everything runs on the system clock. The controller makes the
// memory clock (sck) as a register, one level per system clock, launches
// nibbles as sck falls and samples the bus as sck falls again. The emulator
// sees each sck edge one system clock after it happens and answers one clock
// after that, which is still a full system clock before the controller
// samples — so read latency 0 (ui_in[2:0] = 000 during reset) is correct.
//
// Sizes are parameters; addresses wrap within them. Flash contents come from
// FLASH_INIT (one hex byte per line, e.g. made by fpga/basys3/Makefile).
`default_nettype none
module qspi_emu #(
    parameter int    FLASH_BYTES = 32768,
    parameter int    RAM_BYTES   = 65536,      // each of RAM A and RAM B
    parameter        FLASH_INIT  = ""
) (
    input  wire logic       clk,
    input  wire logic       cs_flash_n,
    input  wire logic       cs_rama_n,
    input  wire logic       cs_ramb_n,
    input  wire logic       sck,
    input  wire logic [3:0] sd_from_ctrl,      // SD3..SD0 as driven by Tiqora
    output logic      [3:0] sd_to_ctrl,
    output logic            sd_drive           // emulator is driving the data lines
);
    localparam int FA = $clog2(FLASH_BYTES);
    localparam int RA = $clog2(RAM_BYTES);

    (* ram_style = "block" *) logic [7:0] flash_mem [0:FLASH_BYTES-1];
    (* ram_style = "block" *) logic [7:0] rama_mem  [0:RAM_BYTES-1];
    (* ram_style = "block" *) logic [7:0] ramb_mem  [0:RAM_BYTES-1];
    // One initializer per memory: Yosys (0.70) lets the for loop win over a
    // later $readmemh on the same words, which baked an erased flash into the
    // open-source bitstream. The Makefile pads every image to FLASH_BYTES with ff.
    initial begin
        if (FLASH_INIT != "") $readmemh(FLASH_INIT, flash_mem);
        else for (int i = 0; i < FLASH_BYTES; i++) flash_mem[i] = 8'hFF;   // erased flash
    end

    typedef enum logic [2:0] {S_IDLE, S_CMD_SPI, S_CMD_QPI, S_ADDR, S_MODE, S_DUMMY, S_DOUT, S_DIN} st_t;
    st_t         st;
    logic [4:0]  cnt;
    logic [7:0]  sh;
    logic [23:0] addr;
    logic        nib_hi, is_flash, is_write;
    logic        flash_cont, qpi_a, qpi_b;
    logic        sck_q, sel_q;
    logic [7:0]  rd_flash, rd_rama, rd_ramb;

    wire sel_a  = !cs_rama_n;
    wire sel_b  = !cs_ramb_n;
    wire sel_f  = !cs_flash_n;
    wire sel    = sel_f | sel_a | sel_b;
    wire rise   = sck & !sck_q;
    wire fall   = !sck & sck_q;
    wire qpi    = sel_a ? qpi_a : qpi_b;
    wire [7:0] rd_byte = is_flash ? rd_flash : (sel_a ? rd_rama : rd_ramb);
    wire [7:0] cmd_spi = {sh[6:0], sd_from_ctrl[0]};
    wire [7:0] cmd_qpi = {sh[3:0], sd_from_ctrl};

    // block RAM read ports: registered, always following the current address
    always_ff @(posedge clk) begin
        rd_flash <= flash_mem[addr[FA-1:0]];
        rd_rama  <= rama_mem[addr[RA-1:0]];
        rd_ramb  <= ramb_mem[addr[RA-1:0]];
    end

    // block RAM write port (RAMs only)
    always_ff @(posedge clk) begin
        if (sel && rise && st == S_DIN && !nib_hi) begin
            if (sel_a) rama_mem[addr[RA-1:0]] <= {sh[7:4], sd_from_ctrl};
            else       ramb_mem[addr[RA-1:0]] <= {sh[7:4], sd_from_ctrl};
        end
    end

    initial begin flash_cont = 1'b0; qpi_a = 1'b0; qpi_b = 1'b0; st = S_IDLE; sd_drive = 1'b0; end

    always_ff @(posedge clk) begin
        sck_q <= sck;
        sel_q <= sel;
        if (!sel) begin
            st       <= S_IDLE;
            sd_drive <= 1'b0;
        end else if (!sel_q) begin                       // a transaction starts
            is_flash <= sel_f;
            is_write <= 1'b0;
            sh       <= 8'd0;
            if (sel_f) begin
                st  <= flash_cont ? S_ADDR : S_CMD_SPI;
                cnt <= flash_cont ? 5'd6 : 5'd8;
            end else begin
                st  <= qpi ? S_CMD_QPI : S_CMD_SPI;
                cnt <= qpi ? 5'd2 : 5'd8;
            end
        end else if (rise) begin
            unique case (st)
                S_CMD_SPI: begin
                    sh  <= cmd_spi;
                    cnt <= cnt - 5'd1;
                    if (cnt == 5'd1) begin
                        if (is_flash && cmd_spi == 8'hEB) begin
                            st <= S_ADDR; cnt <= 5'd6;
                        end else begin
                            if (!is_flash && cmd_spi == 8'h35) begin
                                if (sel_a) qpi_a <= 1'b1;
                                if (sel_b) qpi_b <= 1'b1;
                            end
                            st <= S_IDLE;                 // ignore the rest of this transaction
                        end
                    end
                end
                S_CMD_QPI: begin
                    sh  <= cmd_qpi;
                    cnt <= cnt - 5'd1;
                    if (cnt == 5'd1) begin
                        st <= S_IDLE;
                        unique case (cmd_qpi)
                            8'hEB: begin st <= S_ADDR; cnt <= 5'd6; is_write <= 1'b0; end
                            8'h38: begin st <= S_ADDR; cnt <= 5'd6; is_write <= 1'b1; end
                            8'hF5: begin
                                if (sel_a) qpi_a <= 1'b0;
                                if (sel_b) qpi_b <= 1'b0;
                            end
                            default: ;
                        endcase
                    end
                end
                S_ADDR: begin
                    addr <= {addr[19:0], sd_from_ctrl};
                    cnt  <= cnt - 5'd1;
                    if (cnt == 5'd1) begin
                        if (is_flash)       begin st <= S_MODE;  cnt <= 5'd2; end
                        else if (is_write)  begin st <= S_DIN;   nib_hi <= 1'b1; end
                        else                begin st <= S_DUMMY; cnt <= 5'd6; end
                    end
                end
                S_MODE: begin
                    sh  <= cmd_qpi;
                    cnt <= cnt - 5'd1;
                    if (cnt == 5'd1) begin
                        flash_cont <= (cmd_qpi[5:4] == 2'b10);
                        st <= S_DUMMY; cnt <= 5'd4;
                    end
                end
                S_DUMMY: begin
                    cnt <= cnt - 5'd1;
                    if (cnt == 5'd1) begin st <= S_DOUT; nib_hi <= 1'b1; end
                end
                S_DIN: begin
                    if (nib_hi) begin sh[7:4] <= sd_from_ctrl; nib_hi <= 1'b0; end
                    else begin addr <= addr + 24'd1; nib_hi <= 1'b1; end
                end
                default: ;
            endcase
        end else if (fall && st == S_DOUT) begin
            sd_to_ctrl <= nib_hi ? rd_byte[7:4] : rd_byte[3:0];
            sd_drive   <= 1'b1;
            if (!nib_hi) addr <= addr + 24'd1;
            nib_hi <= !nib_hi;
        end
    end
endmodule
