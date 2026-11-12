// qspi_rx_props.svh — spliced into a scratch copy of src/bus/qspi_ctrl.sv by
// syn/qspi_rx_formal.sh (the RTL itself is untouched).
//
// rx_ref follows rx exactly as the controller wrote it before the speed
// change: it is also cleared when a read continues the open flash stream
// (Q_IDLE with req && can_stream). rx is read only through rdata, so the
// change is exact if rx == rx_ref in every state but Q_DATA, and inside
// Q_DATA the nibbles already shifted in agree: the low 4 * (8 - nib_cnt)
// bits. Every Q_DATA exit follows the shift of its last nibble, and a read
// always shifts 8, so rdata matches whenever it can be consumed.
`ifdef FORMAL
    logic f_past_ok = 1'b0;
    always_ff @(posedge clk) f_past_ok <= 1'b1;
    always @(*) if (!f_past_ok) assume (rst);

    logic [31:0] rx_ref;
    always_ff @(posedge clk) begin
        if (rst) rx_ref <= 32'd0;
        else unique case (state)
            Q_IDLE:   if (req && can_stream) rx_ref <= 32'd0;
            Q_PREFIX: if (phase && nib_cnt == 4'd1 && dummy_cnt == 4'd0) rx_ref <= 32'd0;
            Q_DUMMY:  if (phase && dummy_cnt == 4'd1) rx_ref <= 32'd0;
            Q_DATA:   if (phase) rx_ref <= {rx_ref[27:0], sd_in};
            default: ;
        endcase
    end

    logic [31:0] f_mask;
    assign f_mask = 32'hFFFF_FFFF >> {nib_cnt, 2'b00};
    always @(*) if (f_past_ok && !rst) begin
        if (state != Q_DATA) assert (rx == rx_ref);
        else begin
            assert (nib_cnt <= 4'd8);
            assert ((rx & f_mask) == (rx_ref & f_mask));
        end
    end
`endif
