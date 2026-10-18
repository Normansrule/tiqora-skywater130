// bench_alu.c — the best case: straight-line ALU instructions with no loads,
// stores or taken branches inside the block. 6,400 add/xor instructions in
// 64-instruction unrolled blocks.
int main(void) {
    for (int i = 0; i < 50; i++)
        __asm__ volatile (".rept 64\n addi t0, t0, 1\n xor t1, t1, t0\n .endr" ::: "t0", "t1");
    return 0;
}
