# How the Info > All hang was found, and why the fix is safe

Technical write-up of the crash in the NoPrgress DQ6 translation, and of the
three-byte restoration that fixes it.

Measured facts and inferences are labelled separately throughout. Where
something is a guess, it says so.

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
There is no entry 1. Index 1 reads a byte the game never initialises, which is
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
  translation; this one only drops state initialisation.
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
back to what Square wrote, and the correct bound then rejects the bad index by
itself.

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

Both artefacts were the same defect wearing a different face. The slot loop was
running past the end of a one-member party, so it drew window frames for members
that do not exist and read stat fields that were never initialised. With the
bound restored to the real party count, the loop stops after slot 0 and all
three symptoms disappear together. This is what distinguishes fixing the cause
from suppressing the symptom: the bounds guard discussed above would have
stopped the hang and left both artefacts on screen.

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
behaviour, which is the loop stopping at the real end of the party.

### Scope

Verified on one ROM and one emulator, at **two party sizes**: a solo level 1
character and a full eight-member party, neither of which hangs. **Not**
verified across a full playthrough, or on emulators other than MesenCE.
