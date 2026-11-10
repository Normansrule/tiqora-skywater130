// regfile_props.svh — spliced into a scratch copy of src/core/tp_nregfile.sv
// (syn/formal/run.sh). The register file rotates every register by one nibble
// on every clock and has no reset, so its correctness rests on one invariant:
// a nibble written at phase k is read back at phase k, on every later lap,
// until it is overwritten. The solver picks any register f_reg (1..15) and any
// phase f_k, follows the last nibble written there in a ghost f_val, and
// R1: reading f_reg at phase f_k on either port returns f_val, forever.
// R2: register 0 always reads as zero.
// The phase counter is ghost state too: the core's own 3-bit counter is just
// as free-running, and the proof does not care where it starts.
    (* anyconst *) logic [3:0] f_reg;
    (* anyconst *) logic [2:0] f_k;
    logic       f_past_ok = 1'b0;
    logic [2:0] f_ph;
    logic [3:0] f_val;
    logic       f_valid = 1'b0;
    always @(posedge clk) begin
        f_past_ok <= 1'b1;
        f_ph <= f_ph + 3'd1;
        if (we && wa == f_reg && f_ph == f_k) begin f_val <= wd; f_valid <= 1'b1; end
    end
    logic [31:0] f_r;
    assign f_r = r[f_reg];
    always @(*) begin
        assume (f_reg != 4'd0);
        if (ra == 4'd0) assert (qa == 4'd0);                                   // R2
        if (rb == 4'd0) assert (qb == 4'd0);
        if (f_valid) begin
            // where the tracked nibble sits right now: it reaches the bottom
            // (bits 3:0) when the phase comes round to f_k again
            assert (f_r[{f_k - f_ph, 2'b00} +: 4] == f_val);                  // invariant
            if (f_ph == f_k && ra == f_reg) assert (qa == f_val);              // R1
            if (f_ph == f_k && rb == f_reg) assert (qb == f_val);
        end
    end
