# How all four were found, and why the fixes are safe

Technical write-up of two crashes, one hang and one lost display in the
NoPrgress DQ6 translation.

- **Part one, below:** the **Info > All** hang, and the three-byte restoration
  that fixes it. Shipped in v1, v2 and v3.
- **[Part two](#part-two-the-forget-crash):** the **Forget** crash, and the
  variable relocation that fixes it. Shipped in v2 and v3.
- **[Part three](#part-three-the-gold-window):** the **gold window**, deleted
  from the info screen when the status window was widened for English labels.
  Shipped in v3 and v4. Not a crash.
- **[Part four](#the-fourth-the-tactics-equip-hang):** the **Tactics-equip
  hang**, and the routine that answers the same question correctly four hundred
  bytes away. Shipped in v4 only. **Not the translation's defect** - it is in
  Enix's 1995 code and in the Japanese ROM.

All four are unrelated defects with different shapes. The first is a deleted
instruction. The second is a memory allocation collision, in which every
instruction on the fault path is byte-identical to the Japanese original and the
defect is in *where* the translation put its data. The third is a deletion made
deliberately, to free space that a wider window had taken. The fourth is not the
translation's at all: a broken duplicate of a correct routine, shipped in 1995,
that only English data reaches.

Measured facts and inferences are labelled separately throughout. Where
something is a guess, it says so. The refuted hypotheses are kept: they were
most of the work, and a write-up showing only the path that worked would be a
worse document.

Addresses are SNES addresses. The ROM is **HiROM**, headerless, 4 MiB, so file
offset `N` maps to `$C0+(N>>16):N&FFFF`.

---

## 1. The fault

The game does not crash. It hangs, spinning on a two-byte instruction that
branches to itself:

```
$C4:560F   F0 FE      BEQ $C4560F
```

Register state at the moment it becomes inescapable:

```
A:2D01  X:0001  Y:0000  S:0841  D:0000  DB:7E   P:nvMXdIZC
```

`Z` is set, so the branch is always taken. Non-maskable interrupts still fire,
the music keeps playing, and the interrupt handler returns straight back into the
loop. In a 1.93 GiB trace of the crash, 4,878,936 lines are this one
instruction.

This is not corrupted execution. It is a **deliberate assertion left in the
shipped game**:

```
$C4:560A   BC EE 3E   LDY $3EEE,X
$C4:560D   C0 00      CPY #$00
$C4:560F   F0 FE      BEQ $C4560F     ; hang if the table entry is zero
$C4:5611   88         DEY
```

"Load a table entry, and if it is zero, stop the world." There are **835 such
self-branch sites** in the ROM below `0x360000`, so this is a house pattern
rather than a one-off. `$C4:560F` is byte-identical in the Japanese and
translated ROMs, and it executes harmlessly many times in normal play. The first
of its millions of appearances in the trace has `Y:0001`, clears `Z`, and falls
straight through.

## 2. The chain

```
$C3:963D   ...                       ; slot loop, reached by a PHA/RTL dispatch
$C3:9647   LDA $3868                 ; slot index          = $0001
$C3:964A   CMP $3AC2                 ; upper bound         = $00FF   <-- wrong
$C3:964D   BCC $9652                 ; 1 < 255, so taken
$C3:9652   JSL $C455E7
$C3:9656   02 FF FD                  ; inline parameter bytes

$C4:55E7   PHP / PHB / SEI / REP #$30
$C4:55EC   PHA                       ; 16-bit, so the caller's A is saved here
$C4:55F3   JSL $C426CB               ; copy the 3 inline bytes to $7E:4898..489A
$C4:55FB   LDA $4899                 ; = $FF
$C4:55FE   JSL $C426E0               ; resolve the $FF sentinel
$C4:5602   TAX                       ; X = 1
$C4:5603   LDA $4898                 ; = $02
$C4:5606   JSR $2C6F                 ; dispatcher, returns 1
$C4:5609   TAX                       ; X = 1
$C4:560A   LDY $3EEE,X               ; reads $7E:3EEF = $00
$C4:560D   CPY #$00                  ; Z set
$C4:560F   BEQ $C4560F               ; hang
```

The sentinel resolver is the pivot:

```
$C4:26E0   PHP
$C4:26E1   REP #$30
$C4:26E3   AND #$00FF
$C4:26E6   CMP #$00FF                ; is the parameter the $FF sentinel?
$C4:26E9   BNE $26EF
$C4:26EB   LDA $09,S                 ; yes: substitute the caller's saved A
$C4:26ED   PLP
$C4:26EE   RTL
```

`$09,S` resolves to exactly where `$C4:55EC`'s 16-bit `PHA` put the accumulator.
So the ROM byte `0xFF` at `$C3:9657` means **"use the value the caller passed in
A"**, and the caller passed the slot index.

**Why index 1 is fatal.** `$7E:3EEF` is accessed exactly **once in the entire
1.93 GiB trace**, and that once is the fatal read. It is never written.
`$7E:3EEE` is accessed 81 times, and a 16-bit read there returns `$0001`. So
`$3EEE` holds the 16-bit value 1, and `$3EEF` is merely that value's high byte.
There is no entry 1. Index 1 reads a byte the game never initializes, which is
zero, and the assertion fires.

Everything in that chain is **byte-identical between the two ROMs**. Bank `$C4`
contains exactly one changed byte in all 64 KiB, and it is nowhere near this
path. Stack balance was checked and is correct at every frame; the fault is not
a stack bug.

## 3. The measured divergence

The bound `$7E:3AC2` has two kinds of writer. One writes a sentinel:

```
$C3:7489   JSL $C92F6B      ; test $7E:3888 & $0008
$C3:7493   BCS $C3749B      ; bit set: compute a real value
$C3:7495   LDA #$00FF       ; bit clear: the "not applicable" sentinel
$C3:7498   STA $3AC2
```

and others write the actual party size. Reading the operand off the comparing
instruction in both traces:

```
Japanese : $C3:964A CMP $3AC2 reads $0001 at ALL 20 executions. Never $00FF.
NoPrgress: $C3:964A CMP $3AC2 reads $00FF at 4 of 5, including the fatal one.
```

With the correct bound of 1 on a one-member party, index 1 is rejected: `1 >= 1`
leaves carry set, the branch is not taken, and the routine exits three
instructions later. That is what the Japanese ROM does 18 times out of 20. In the
translated ROM the bound is 255, so index 1 is accepted.

The same routine, invoked safely and fatally, differs only in the caller's
accumulator:

```
Japanese  (both)     C45602 TAX  A:0000  -> X=0  -> reads $3EEE  -> fine
NoPrgress (1,2,3)    C45602 TAX  A:0000  -> X=0  -> reads $3EEE  -> fine
NoPrgress (fatal)    C45602 TAX  A:0001  -> X=1  -> reads $3EEF  -> hang
```

`$C4:560A` executes **twice** in the whole Japanese trace, and `$7E:3EEF` is
never read there at all.

### The write that is missing

Japanese, immediately before each comparison:

```
$C3:7498  STA $3AC2   A:$00FF   -> bound = FF   (sentinel)
$C3:3538  STA $3AC2   A:$0001   -> bound = 1    (the real party count)
$C3:964A  CMP $3AC2             -> reads 1      -> safe
```

`$C3:3538` fires 20 times in the Japanese trace, matching the 20 dispatches one
for one. **In the translated ROM it does not exist**, and the last three writes
before the fatal comparison are all the sentinel with nothing correcting them.

### A note on `$7E:3888` bit 3

It is tempting to chase the bit that selects the sentinel path. Do not: bit 3 is
**clear at this point in both ROMs**, and the Japanese ROM does not hang. The bit
only decides whether the sentinel or a computed value gets written first, and in
the Japanese ROM the sentinel is then overwritten by `$C3:3538` regardless.

## 4. The change in the ROM

```
              Japanese                             NoPrgress
$C3:3532  22 1c 2b c4   JSL $C42B1C          22 1c 2b c4   JSL $C42B1C
$C3:3536  02 ff         (inline params)      02 ff         (inline params)
$C3:3538  8d c2 3a      STA $3AC2            --- DELETED ---
$C3:353B  22 25 7b c3   JSL $C37B25          22 25 7b c3   JSL $C37B25  (now $3538)
$C3:353F  a9 87 00      LDA #$0087           a9 87 00      LDA #$0087   (now $353C)
             ... everything after shifts up by 3 ...
```

**Measured:** `EN[i] == JP[i+3]` for **84 consecutive bytes**, from `$C3:3538`
to `$C3:358C`, where unshifted equality resumes. The block is byte-for-byte the
Japanese code with one instruction removed and the remainder moved up. Every
string identifier in it is unchanged: `#$0087`, `#$0026`, `#$002C`, `#$002D`,
`#$002E`, `#$002F`, `#$0030`, `#$008A`.

The three bytes the deletion frees at the tail are left holding a now-unreachable
copy of the routine's own epilogue, `68 28 6B` = `PLA / PLP / RTL`, at
`$C3:358C`. The translated routine already returned three bytes earlier, at
`$C3:358B`.

`$C4:2B1C`, the call whose result the Japanese ROM stores, fetches two inline
parameter bytes and returns a count in `A`. In the trace it returns `$0001` with
a one-member party, consistent with "number of party members".

### Why this looks like a slip

**This section is inference, not measurement.** Three things point at an
accidental deletion:

- The deletion frees three bytes and then spends nothing. The freed space is left
  as dead epilogue bytes. A deliberate byte reclaim that reclaims nothing makes
  no sense.
- `STA $3AC2` has no text content. Every other change in this area serves the
  translation; this one only drops state initialization.
- The deleted instruction sits **immediately after inline parameter bytes**
  (`02 FF` at `$C3:3536`, consumed by the call above it). A tool or a hand edit
  that mismeasured where the inline parameters end would swallow exactly the
  following three bytes. And there was editing going on right there: the
  adjacent deletion at `$C3:3594`, removing `LDA #$007A / JSL $C3763A`, drops a
  Japanese-only label and is clearly deliberate translation work.

What is **measured** is only that the instruction is gone and nothing replaced
its effect.

## 5. The fix, and why the span is safe to shift

The fix restores `EN[0x033538:0x03358F]` from the Japanese ROM: an 87-byte span
of which 84 bytes differ. That reinserts `8D C2 3A`, shifts the block back to
Japanese positions, and consumes the three dead bytes at `$C3:358C`. No free
space, no hook, no relocation.

**The span stops at `0x03358F` and must not be widened.** The 7-byte deletion at
`$C3:3594`, in the following routine, is deliberate translation work and is
preserved.

Shifting code is only safe if nothing points into the middle of it. Checked, all
measured:

| Check | Result |
|---|---|
| 24-bit pointers into `$C3:3539`-`$C3:358E` | 2 apparent hits, both in banks `$F0` and `$F5`, which are text and graphics payload. Coincidental data bytes, not pointers. |
| Same-bank `JSR` / `JMP abs` into the span | none |
| Relative branches from outside into the span | 1 apparent hit at `$C3:34FE`, a **false positive**: that byte is the operand of `REP #$30`, and the real instruction boundaries are `$C3:34FD` and `$C3:34FF`. |
| Window-descriptor handler pointers into the span | none. The nearest, record 57 of the 240-entry table at `$C5:7B67`, points at `$C3:352E`, before the span. |
| Bytes from `0x03358F` onward | already identical between the two ROMs, so the routine boundary is preserved |

The SNES internal checksum is recomputed afterwards. The translation ships a
**correct** checksum (`0xD17A`), so leaving a stale value after modifying the ROM
would be a regression. The image is 4 MiB, a power of two, so the plain sum
applies, with the header at `$FFC0`. The result is `0xD208`, complement
`0x2DF7`.

Net effect on the ROM, exactly 88 bytes:

```
0x00FFDC - 0x00FFE0    4 bytes    checksum and complement
0x033538 - 0x03358C   84 bytes    the restored instruction and the undone shift
```

### Why here and not a guard at the comparison

Adding a bounds guard at `$C3:964A`, rejecting `$00FF` before using it as a
count, would stop the hang. It was kept as a fallback and not used, because it
treats the symptom: the bound would still be wrong, so the screen would still
iterate slots that do not exist and still draw the empty member windows that are
visible on the status screen today. Restoring the instruction puts the routine
back to what the original developers wrote, and the correct bound then rejects
the bad index by itself.

---

## Two methodology notes

Both of these cost real time during this investigation, and both generalise to
any trace-driven romhacking work.

### MesenCE prints the pre-write value for stores

In a trace line for a store, the `[$address] = $value` column shows **what was at
the address before the write**, not what is being written. The value written is
in the `A` column.

```
$C3:3538  STA $3AC2 [$7E3AC2] = $00FF   A:0001    <- writes 1, displays the old FF
$C3:7279  STZ $3868 [$7E3868] = $0001   A:....    <- STZ writes 0, displays the old 1
```

An `STZ` that displays a nonzero value settles the question. Reading that column
as the value written inverts the meaning of every store in the log, and it
inverted an entire earlier pass of this analysis before an `STZ` gave it away.

### Read a loop bound off the comparing instruction

The obvious way to find out what a variable held at some moment is to find the
most recent write to it earlier in the trace. On a shared address this is
**wrong**, because writes from unrelated screens and unrelated code paths
interleave, and the reconstruction silently picks up somebody else's write. It
produced a confident and completely incorrect answer here.

The comparing instruction prints the operand value it actually read. Use that. It
is authoritative and needs no reconstruction.

---

## Status: confirmed in game, 2026-08-17

The defect, the fault, and the byte-level content of the fix are measured, and
the patch mechanics are verified against Flips as an independent implementation.

**The fix is confirmed working.** On `DQVI_NoPrgress_MenuFix.sfc`, CRC32
`174D40F8`, SHA-1 `01e417a0036db27fc5a4102e012ceec82c56ca76`, in MesenCE, with a
solo party at level 1, the previously fatal sequence no longer hangs. Entering
Info > All and backing out before the screen finishes now behaves normally, as
does the uninterrupted path.

Two further observations make this more than "the crash went away":

- **The two phantom empty party windows are gone.**
- **The Def column shows a number instead of `?`.**

Both artifacts were the same defect wearing a different face. The slot loop was
running past the end of a one-member party, so it drew window frames for members
that do not exist and read stat fields that were never initialized. With the
bound restored to the real party count, the loop stops after slot 0 and all
three symptoms disappear together. This is what distinguishes fixing the cause
from suppressing the symptom: the bounds guard discussed above would have
stopped the hang and left both artifacts on screen.

### Confirmed at instruction level

A trace of the fixed ROM covering the Info > All sequence has since been
captured, on a save with a full **eight-member party**. Every prediction the
section above left open is now measured directly:

| Predicted | Measured in the fixed build |
|---|---|
| `$C3:3538 STA $3AC2` executes and writes the party count | executes **8 times**, writing `$0008` each time |
| `$C3:964A CMP $3AC2` reads the count, not the sentinel | reads **`$0008` at all 8 executions**, never `$00FF` |
| out-of-range slots rejected, matching the Japanese ratio | **7 rejections** via the early exit at `$C3:964F`, 1 proceed |
| `$7E:3EEF` never read at the fault site | `$C4:560A` read `$7E:3EEE` with `X:0000` |
| `$C4:560F` never reached with `Z` set | executes **once**, `Z` clear, passed harmlessly |

The value read is taken from the operand of the comparing instruction itself,
and the value written from the `A` column, per the two methodology notes above.

Note the ratio scales with the party rather than being a fixed number: the
Japanese ROM produced 18 rejections in 20 dispatches on a one-member party, and
the fixed build produces 7 in 8 on an eight-member one. Both are the same
behavior, which is the loop stopping at the real end of the party.

### Scope

Verified on one ROM and one emulator, at **two party sizes**: a solo level 1
character and a full eight-member party, neither of which hangs. **Not**
verified across a full playthrough, or on emulators other than MesenCE.

---

# Part two: the Forget crash

Shipped in **v2 only**.

Using **Forget** in the Remember conversation system produces jumbled repeating
text, then a black screen, and the game does not recover.

It looks intermittent. It is not. It is deterministic, and what varies is
whether one of the original game's periodic memory clears happens to land in the
middle of a message.

---

## 1. The collision

The translation keeps its word-wrap state in three variables:

```
$7E:379E    a width accumulator      5 instruction sites
$7E:37A0    the buffer length        8 instruction sites
$7E:37A2    the buffer itself        6 instruction sites
```

All three sit inside a 112-byte block at `$7E:3768`-`$37D6` that belongs to the
original game. That block is a **bitfield**, and a live one:

```
$C3:11DE   LSR / LSR / LSR / TAX     ; index divided by 8 -> byte offset
$C3:11EE   LDA $3768,X / AND $FC31   ; test a bit
$C3:1815   LDX #$FFFE
$C3:1818   INX / INX
$C3:181A   LDA $3768,X / BEQ $1818   ; scan for the first non-empty word
$C3:1825   LSR / LSR / STA $3AE0     ; convert back to an index
```

112 bytes, so 896 bits. It has four users, `$C3:11EE`, `$C3:181A`, `$C3:787B`
and `$C5:CF90`, and **all four are Enix code, byte-identical to the Japanese
ROM.** The value `$C3:1825` produces feeds `$3AE0`, which `$C3:7B25` reads to
set the party-slot index, so this bitfield is live on exactly the screens where
messages appear.

Three block clears own it, with their bounds read off the instruction rather
than inferred:

```
$C3:7878   LDX #$006E / STZ $3768,X / DEX x2    clears $7E:3768-$37D7
$C5:CF8D   LDX #$006E / STZ $3768,X / DEX x2    clears $7E:3768-$37D7
$C5:CF97   LDX #$006E / STZ $37D8,X / DEX x2    clears $7E:37D8-$3847
```

A second 112-byte block butts directly against the first, so there is no unused
tail to borrow at either end. The translation's buffer had **54 bytes** before
it ran into that second block.

**This is the whole defect.** A clear fires, the buffer and its length are
zeroed underneath a live cursor, and the message machinery carries on as though
nothing happened.

---

## 2. The chain

Nine steps from the clear to the black screen, each measured in a trace rather
than reasoned about:

1. A block clear fires mid-message and zeroes the length at `$7E:37A0` and the
   buffer at `$7E:37A2`.
2. The replay loop's bound is now `$0000` while its cursor is already past it.
3. The loop reads a buffer slot that was never written, getting `$0000`.
4. That `$0000` reaches `$C0:29F0 SBC #$00AB`.
5. `$0000 - $00AB` **underflows to `$FF55`**.
6. `$FF55` is used as a table index, so the lookup reads **backwards** out of
   the table and into the translation's own inserted routine.
7. What it finds there is executed as an address, and the `JML` lands in **open
   bus**.
8. Open bus on this machine reads as `$00`, which is `BRK`. The BRK handler
   takes a **garbage return address** off the stack.
9. That garbage propagates into the message-ID derivation, which fabricates ID
   **`$0AAA`**. The Huffman decoder is pointed at data that is not text, decodes
   an endless character stream, and the screen goes black.

Step 8 is worth a note. `$C5:9942` is genuinely the BRK handler: `$00:FFE6`
holds `$FFA8`, and `$00:FFA8` holds `5C 42 99 C5`, a `JML $C59942`. But its
first instructions are `PLP / REP #$30 / PHA / LDA $03,S / DEC / DEC /
STA $03,S`, which is **return-address adjustment**. This engine uses `BRK #imm`
as a compact inline-parameter call instruction, so a BRK is normal here. What is
abnormal is reaching it from a corrupted return path.

---

## 3. The measured divergence

The underflow at step 5 is the point where the runs separate. Counting how often
`$C0:29F0` receives a value below `$00AB`:

| run | underflows |
|---|---|
| Japanese ROM, same conversation | **0 of 109** |
| Translation, healthy Forget | **0 of 9** |
| Translation, failing Forget | **1 of 85** |

One underflow in eighty-five is enough. Everything downstream is deterministic
once it happens.

---

## 4. The fix

Move all three variables somewhere the original game does not touch:

```
$7E:379E  ->  $7E:55BE    width      5 sites
$7E:37A0  ->  $7E:55C0    length     8 sites
$7E:37A2  ->  $7E:55C2    buffer     6 sites
```

Nineteen sites, thirty-eight operand bytes. **Opcodes and instruction lengths
are unchanged**, so there is no code motion, no hook, and no ROM free space
consumed. Every site was verified to hold its expected opcode and operand before
anything was written.

v2 also changes two branch conditions that test equality where they need an
ordered test, so an index already past a shrunken bound could never reach the
exit:

```
$C0:FE27   F0 -> B0    BEQ -> BCS
$C0:FF1D   D0 -> 90    BNE -> BCC
```

Both are **no-ops on a healthy path**, where the index only ever reaches the
bound from below. They were fixed before the root cause was found, neither
resolved the crash alone, and they were **not individually isolated**: no build
was made with the relocation and without them.

### Choosing the destination

The target had to fail four independent tests to qualify:

1. **A CDL-guided static scan.** The emulator's code/data log records which ROM
   bytes actually executed and the register widths in force, giving real
   instruction boundaries instead of guessing code from data. 60,924
   instructions decoded.
2. **A trace touch map** from five clean sessions, every effective address
   widened to two bytes.
3. **Snapshot content:** any byte non-zero in either of two WRAM dumps.
4. **Snapshot diff:** any byte differing between the two dumps is definitively
   written. The dumps differ in 27.3% of WRAM, so they are genuinely different
   game states.

`$7E:55AE`-`$5689` failed all four, and its 192-byte core reads zero on every
one of them. Of the candidates it also had by far the largest margin against
indexed addressing reaching into it from below: an index of `$046A` would be
needed, against `$40` and `$02` for the runners-up.

For the parts of the ROM that have never executed and so cannot be classified,
the byte-scan hit counts were compared against chance. All three finalists came
in **below** what random data predicts (948 observed against 2,277 expected for
this one), so those hits carry no evidence of real references.

Bank `$7F` was rejected despite holding the largest free run in the machine,
21,905 bytes. The code reaches its buffer as `STA $37A2,X` with the data bank set
to `$7E`; reaching `$7F` needs long addressing, which is a different opcode and
an extra byte at every site, so it stops being a drop-in.

### Headroom

```
before   $37A2 -> $37D8 (the next Enix block)    54 bytes
after    $55C2 -> $568A                         200 bytes
worst overrun actually observed                 136 bytes
```

The old location could not contain the overspill that occurs. The new one can.

---

## 5. Verification

Two independent traced sessions, 90 GB and 58.75 GB, the second spanning roughly
23,000 frames on a different save. Coverage confirmed by instruction counts
rather than assumed, and including **battle**, which was the standing gap in the
evidence for the destination region.

In both sessions: no underflow, no uninitialized slot read, no execution outside
legitimate banks, no fabricated message ID.

The strongest single result is the **lane analysis**. Across the whole second
session, every access to the relocated region came from translation code, and
each variable stayed in its own set of sites:

```
$55BE  width     written by $C0:FE81 FEA2         read by $C0:FE85 FE8B FEA7
$55C0  length    written by $C0:FDD5 FDE8 FDFE
                            FF03 FF1F             read by $C0:FDE0 FE24 FF1A
$55C2  buffer    written by $C0:FDE3 FEF2         read by $C0:FE29 FE69 FF22 FF34
```

8,727 writes and 13,420 reads, and **zero foreign accesses**. In the other
direction, a static scan of every instruction the translation added returns
**zero references** into `$7E:3768`-`$3847`.

One WRAM snapshot was captured mid-message and shows the relocation live: width
`$0007`, length `$000C`, real glyph data at `$55C2`, the old slots all zero, and
the Enix block entirely clean.

---

## 6. Hypotheses that were wrong

Six theories were pursued and refuted by measurement. They are listed because
each one looked right at the time.

- **The accumulator-value theory.** The idea that a particular value reaching
  `$C0:2C92` was inherently non-returning. Refuted: the Japanese run takes the
  same path 109 times and the routine is balanced 881 entries to 881 returns.
  The value `$00AC` strands in one run and returns in two others, so it is not
  the discriminator.
- **The buffer-clobbering theory, in its first form.** An ownership test asked
  *who wrote* each byte that was read back, found every one had been written by
  the same invocation, and concluded the content was fine. That was the **wrong
  question**: same-invocation authorship does not imply correct content. A pass
  that appends the wrong bytes still owns what it wrote.
- **The re-entrancy theory.** That nested message cycles were the bug and a
  re-entrancy guard was the fix. Refuted: the nesting is **intended by design**,
  one cycle per prompt, and a guard would have broken the feature.
- **The short-table theory.** That the translation's rewritten message-offset
  table was too short and the lookup ran off the end. Measured and refuted: the
  table covers IDs `$0000`-`$0365` and the highest ID any build legitimately
  requests is `$030F`, comfortably inside it. The fabricated `$0AAA` was a
  symptom, not a missing entry.
- **The `$C6:FDF6 CMP #$09A7` threshold theory.** That a translation-added
  threshold was misclassifying message IDs. It is on a different path entirely,
  the name-buffer builder, not the message-table lookup.
- **Three branch-condition fixes.** Each corrected a real defect, and none fixed
  the crash. The lesson is the useful part: **no comparison can recover state
  that unrelated code has already deleted.** Each fix moved the symptom to the
  next exit. Two of them ship in v2 anyway, because they are correct and
  harmless; the third would have been neither.

---

## 7. Measurement errors made along the way

Two of these produced confident, wrong, published-to-the-notes conclusions.

- **The touch map recorded only base effective addresses.** The emulator prints
  one address per memory access and leaves the width to the processor status
  flags, so every 16-bit access left its high byte looking untouched. That
  produced a neat alternating pattern which was duly reported as "a 16-bit
  strided structure with only the odd halves untouched". It was an artifact of
  the extraction. Widening every access to two bytes removes it. This single bug
  produced a false negative that concluded **no safe memory existed anywhere**,
  when in fact bank `$7F` alone had a 21,905-byte free run.
- **Block-clear bounds were capped at 2048 bytes** by the analysis code, so
  `$C2:3467 LDX #$07CE / STZ $2030,X` appeared to stop short of its real extent,
  `$7E:2030`-`$27FF`. Read the bound off the instruction. Never cap it.
- **A crashed run was nearly used as evidence of normal memory use.** The failing
  session touched 122,079 of 131,072 bytes, 93% of all work RAM, because it was
  executing through wild banks. Counting it would have marked essentially
  everything as owned.
- **Absolute stores to `$4300`-`$4325` are DMA register writes, not memory
  writes.** Any map that assumes the data bank is `$7E` everywhere will mark the
  `$2100`-`$43FF` window owned for no reason.
- **A third variable was missed on the first pass.** `$7E:379E` was found only
  after a full trace of the first relocation build, because the search looked
  for the two addresses already known instead of scanning the range. The correct
  query is: scan every instruction the translation added for **any** operand in
  `$7E:3768`-`$3847`. That returns exactly three variables, and it agrees with
  what the trace observed executing.

There is also a standing methodology note from part one that applies here too:
the emulator prints the **pre-write** value for stores, and the value actually
written is in the `A` column. An `STZ` displaying a non-zero value is the proof.

---

## 8. What this does not fix

**The unbounded fill at `$C0:FDD8`-`$C0:FDF0` is still there.** The loop appends
while a condition holds, with no length cap, and was measured writing 136 bytes
past the buffer base.

v2 **contains** this rather than fixing it. The relocation gives the buffer 200
bytes of headroom instead of 54, so the overspill no longer lands on live game
state. That is a real difference in outcome and not a real fix to the loop.

No test session ever triggered the overrun: the longest session's highest write
was 26 bytes past the base, leaving 174 of the 200 bytes untouched. So the
sessions demonstrate correct operation, and they do **not** demonstrate that the
containment works, because it was never called on. This is why the README
suggests savestates the first time you use Forget.

The unbounded loop is listed as an open defect.

---

# Part three: the gold window

Not a crash. A display the translation lost, restored in v3.

## 1. The fault

The Japanese game draws your gold in a window at the top right of the info
screen. The English translation draws nothing there.

## 2. How it was found

Two MesenCE traces of the same screen, one per ROM. Every ROM address executed
during the Japanese trace was collected - 14,839 unique - mapped to file
offsets, and compared byte for byte against the English ROM.

That reduced the whole problem to **seven regions of divergence in code that
demonstrably runs**, which is a far narrower target than scanning for
constants. Scanning has produced false positives on this ROM repeatedly; a
diff restricted to executed addresses cannot, because every hit is by
construction code the console ran.

This is the same technique that found the deleted `STA $3AC2` in part one.

## 3. The measured divergence

```
JAPANESE                          ENGLISH
$358F  JSL $C3736C                $358F  JSL $C3736C
$3593  LDA #$007A                 $3593  LDA #$003E
$3596  JSL $C3763A     <- gone    $3596  JSL $C383FE
$359A  LDA #$003E                 $359A  PLB / REP / PLY / PLX / PLA / PLP / RTL
$359D  JSL $C383FE                $35A2  REP / PLY / PLX / PLA / PLP / RTL  <- duplicate
$35A1  PLB / ... / RTL
```

Seven bytes deleted, `A9 7A 00 22 3A 76 C3`, and the gap backfilled with a
duplicated `RTL` epilogue so every downstream address stayed put.

**That is the same padding technique as the `STA $3AC2` deletion**, which sits
four bytes earlier in the same routine. Two deletions, same method, four bytes
apart.

Confirmed in both directions: the Japanese trace executes the pair three times,
once per info-screen open, and the English trace never calls `$C3:763A` with
`A:007A` anywhere in 3.16 GB.

## 4. The cause, which is not the deletion

Window geometry lives in a descriptor table at **`$C5:7B5C`, 14 bytes per
entry, indexed by `$3058`**. Gold is entry 58. Bytes 11-13 of each entry are
the draw routine pointer, which is how the entry was identified: they read
`8F 35 C3`.

Comparing entry 58 and the status window between ROMs:

```
Japanese   status cols 10-21   gold cols 22-30    side by side
English    status cols 10-24   gold cols 16-23    gold inside the status window
```

English stat labels are wider than Japanese ones. The status window was widened
to fit them, and the gold window ended up underneath it. **With nowhere left to
draw, the call was removed.** The deletion is a consequence of the layout
change, not an independent defect.

This matters for the fix: restoring the seven bytes alone would have drawn a
`G` into coordinates the status window now covers.

## 5. The fix

Twenty-five bytes.

```
0x033593   22 bytes   the draw call restored, at exact size
0x057E88    3 bytes   descriptor 58: X=1, Y=1, W=9  (cols 1-9, rows 1-3)
```

- **Code.** Written over the English fifteen bytes plus the dead duplicate
  epilogue, consuming it exactly. No relocation and no expansion space. The
  write ends at `$35A8`, one byte short of `$35A9`, which is the routine that
  opens the window.
- **Position.** Top left, where the English layout has room. Only the gold
  window's own descriptor changes.
- **The `G`.** It draws string `$10`, a bare one-byte `G`. Entry `$7A` is not a
  gold string at all: `$74`-`$7F` are ` A` through ` L`, an alphabet series in
  which every entry carries an `$88` prefix, and that prefix renders as a stray
  mark on screen. `$10` is what the translation points its **other** gold window
  at, so this is their own substitution applied to the site they missed.

## 6. Why it is safe to compose with v1 and v2

Measured, not assumed:

```
Info > All   0x033538-0x03358F      gold code   0x033593-0x0335A9
Forget       0x00FDD6-0x00FF36      gold desc   0x057E88-0x057E8B
```

No overlap anywhere. The gold code begins four bytes after the Info > All span
ends, and the descriptor is in a different bank from everything else.

Further:

- Only descriptor `$3A` points at `$C3:358F`, so nothing else can enter the
  rewritten code.
- Only descriptor `$3A` differs from the stock translation. The status window,
  the command menu and every other window are byte-identical.
- The consumed epilogue follows an `RTL`, so nothing falls through to it, and
  the three `$35A2` byte-patterns elsewhere in the ROM sit in banks `$C9`,
  `$CD` and `$CF`. A same-bank `JMP` cannot cross banks and the one long call
  among them carries bank `$CD`, so **none of them can reach `$C3:35A2`**.
- No text changes. The message payload, the message pointer table and the name
  table are byte-identical to the stock translation.

## 7. Two wrong readings, and what they cost

Both are recorded because both were confidently held.

**"The labels are too wide, shrink them."** The first theory was that the UI
glyph table had been abandoned and labels rewritten as blank plus an ordinary
letter, making them wider. It was dismissed after measuring `HP` and `MP`,
which are two bytes in both ROMs and genuinely untouched. **Generalising from
those two labels was the error.** The theory was right about the mechanism -
entries `$7A` and `$7B` did go from one byte to two - and wrong only about the
consequence.

**"They missed a site."** The second reading was that the translation had a
working substitution at its other gold window and simply forgot this one, so
the fix was seven bytes. Screenshots of both games side by side killed it: the
English status window visibly occupies the space, so the deletion was
deliberate. **The screenshots had been available throughout.** Reasoning from
the disassembly alone produced a confident wrong conclusion that one look would
have prevented.

The general lesson, which applies to both: the trace work was necessary to find
the deleted call, and it was not sufficient to say what the deletion meant.

## Status: confirmed in game, 2026-08-18

Gold renders at the top left of the info screen. Info > All confirmed working
at two party sizes on the same build, and Forget unaffected.


---

# The fourth: the Tactics-equip hang

Cycling in and out of a character's equipment through the Tactics menu locks the
game. It needs repeated cycling to reach, which is why it went unreported. It is
present in the unpatched translation and in v1, v2 and v3 of this patch.

## What it is

`$C3:1AB1` is a broken duplicate of `$C3:1D0E`. Both answer the same question -
the cursor is on an entry that cannot be selected, so where should it go.

`$C3:1D0E` answers it correctly:

```
LDA $3AE4 / STA $3000       save the ordinal
LDA $3AE4 / JSL $C31B1E
BCC found                   honour the carry
LDA $3768,Y / AND mask / BNE found
DEC $3AE4 / BMI up          floor check
BRA down
up:  LDA $3000 / STA $3AE4  restore, search upward
     INC $3AE4 / ... / CMP $38A6 / BCS none    ceiling check
```

`$C3:1AB1` does none of that. It steps back once, unconditionally, and commits.

## Why one step is enough to break it

One step past zero hands `$C3:1B1E` an ordinal it cannot satisfy. **That routine
is not at fault.** It is bounded with `CPY #$0070`, and it reports failure the
way this codebase reports failure: it returns with the carry set, leaving `Y` at
the bound. The caller never tests it.

The sentinel is then packed as though it were a screen position:

```
linear = (112/2)*16 + 1 = 897     row = 897>>5 = 28     col = 897&31 = 1
```

The tilemap is `$3068`-`$3767`, exactly 28 rows, so `$3068 + 28*64 = $3768`.
**Row 28 is not merely out of range - it is precisely the cursor bitmap that the
same code reads.** The write corrupts the structure the next read depends on, so
the fault sustains itself once started.

## What made it hard

**One producer that gets it right, four consumers that do not check.** Four of
the eight callers of `$C3:1B1E` honour its carry; four do not, and all the damage
came through those four: the packer calls at `$C3:1AD4` and `$C3:16EE`, the bit
test at `$C3:1AC1`, and the unbounded scan at `$C3:1B6E`. Patching any one of
them moved the symptom to the next.

**And the bad write was doing two jobs.** Row 28 corrupts the tilemap, and it is
also nineteen rows below anywhere the cursor legitimately goes, which is how the
original gets the cursor off the visible list. Removing the write fixed the hang
and left a cursor drawn over the item text; no in-bounds substitute could restore
the parking, because the parking works only because the value is out of bounds.

## The fix

Mirror `$C3:1D0E`'s search into `$C3:1AB1`. `$C3:1AC1`-`$1AC9` and everything
from `$1AD8` are untouched, so the common path is byte-identical and ordinary
cursor movement is unaffected.

Two deliberate departures from `$C3:1D0E`:

- its "found nothing in either direction" case is `BRA $1D57`, a self-loop
  asserting the case cannot happen. It has been observed happening, so this
  restores the saved ordinal and redraws instead. Answering a hang with a hang
  would be no answer.
- `$3000` is reused as the save slot because that is what `$C3:1D0E` uses for
  this operation. The two paths are different menus and cannot be live at once.

## Behavioural change

**The cursor may land on a different entry than before in edge cases**, because
it now searches down to the floor and up to the ceiling instead of stepping back
once. That is `$C3:1D0E`'s intended behaviour and what the game does everywhere
else, but it is visible, and it is a change rather than a pure fix.

## Verification

Confirmed in play, then verified from a trace of the fixed build: the sentinel
reaches none of the four consumers, the ordinal never goes negative, nothing
writes row 28, `$376B` holds only `$0000`, and the scan exits cleanly on every
call - 286 reads across 20 calls, against the Japanese ROM's 122 across 9.

The Japanese ROM never enters the fault. Its data never drives the ordinal below
the valid range, so `$C3:1B1E` is never asked a question it cannot answer.
