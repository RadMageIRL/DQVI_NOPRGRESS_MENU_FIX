# DQ6 crash fixes, for the NoPrgress translation

Fixes three hard hangs in **Dragon Quest VI: Maboroshi no Daichi** (Super
Famicom) under the **NoPrgress / DeJap English translation v0.90b2**:

- **Info > All**, when you back out before the status screen finishes drawing.
- **Forget**, in the Remember conversation system.
- **Tactics equip**, after cycling in and out of a character's equipment. This
  one is in Enix's original 1995 code, not the translation's. But triggered by longer EN strings/font.

This repository publishes the patches, the analysis behind them, and a script
that builds them from your own ROMs.

---

<img width="1904" height="1159" alt="DQ6_InfoAll_Forget_Gold" src="https://github.com/user-attachments/assets/cab2a7e8-d726-4ec5-897e-cc9581c63654" />

## Which patch do you want?

Four patches are available. They are a **choice, not a sequence**. v1, v2 and v3
remain available and unchanged; pick the one that matches what you want changed.

| | Info > All | Forget | Tactics equip | gold window | changes what you see |
|---|---|---|---|---|---|
| **v1** | yes | - | - | - | no |
| **v2** | yes | yes | - | - | no |
| **v3** | yes | yes | - | yes | **yes** |
| **v4** | yes | yes | **yes** | yes | **yes** |

**v4 is the one to take unless you have a reason not to.** It is the only one
that fixes the Tactics-equip hang, which affects every other version.

If you want the hang fixes without any visible change, there is no such build:
the equip fix is in v4, and v4 also carries the gold window. v2 remains the
choice for "crash fixes only, nothing looks different", at the cost of the equip
hang.

### v1 - Info > All only, the conservative option

Fixes the hang when you open Info > All and back out before the screen finishes
drawing. The change is minimal: 87 bytes restored so the routine matches the
Japanese original byte for byte, reinstating a deleted `STA $3AC2`. Verified at
instruction level. Nothing else in the game is altered.

### v2 - adds the Forget fix

Everything in v1, plus a fix for the crash in the Forget sequence.

This one relocates word-wrap state that the translation placed inside a block of
memory the original game clears wholesale, moving it to a region established as
unused by static and dynamic analysis.

The residual risk, stated plainly: that region was chosen from emulator code and
data logs, two RAM snapshots, and instruction traces covering field movement,
dialogue, shops, menus and battle. No logged session covers every context in the
game, and code that has never executed cannot be ruled out. If you want only the
change that is verified against the Japanese original, take v1.

**Keep savestates the first time you use Forget.** See "What these patches do not
fix" below for why.

Despite the name `menufix`, kept for continuity with v1, v2 covers both crashes.

### v3 - adds the gold window

Everything in v2, plus the gold display restored to the info screen.

**v3 and v4 are the patches here that change how anything looks.** v1 and v2 are
invisible until they stop a crash; v3 moves a window, and v4 carries that plus a
cursor that can land differently in edge cases. If that is not what you want,
take v2. What you give up is the equip fix.

No text is changed by any of the four.

---

### v4 - adds the Tactics-equip fix

Everything in v3, plus a fix for a hang that **affects every other version of
this patch, and the unpatched translation, and every build of the script-refill
patch before v2.0**.

Cycling in and out of a character's equipment through the Tactics menu locks the
game. It takes repeated cycling to reach, which is why it went unreported for so
long.

`$C3:1AB1` is a broken duplicate of `$C3:1D0E`. Both answer the same question -
the cursor is on an entry that cannot be selected, so where should it go - and
`$C3:1D0E` answers it correctly: it saves the ordinal, honours the carry that
`$C3:1B1E` returns, checks the floor, and if nothing is below it restores the
ordinal and searches upward against a ceiling.

`$C3:1AB1` steps back once, unconditionally, and commits whatever comes back.
One step past zero hands `$C3:1B1E` an ordinal it cannot satisfy. **That routine
reports the failure correctly** - it is bounded and returns with the carry set -
and the caller never looks. The sentinel is then packed as a screen position:

```
linear = (112/2)*16 + 1 = 897     row = 897>>5 = 28     col = 897&31 = 1
```

The tilemap is `$3068`-`$3767`, exactly 28 rows, so **row 28 is one past the end
and lands on `$3768` - the cursor bitmap that the same code reads.** It corrupts
the structure it depends on, which is why the fault sustains itself once it
starts, and why it needs repeated cycling to trigger.

The fix mirrors `$C3:1D0E`'s search into `$C3:1AB1`. The initial check and the
redraw are untouched, so ordinary cursor movement is byte-identical.

**One visible behavioural change.** The cursor may land on a different entry than
before in edge cases, because it now searches down to the floor and up to the
ceiling instead of stepping back once. That is `$C3:1D0E`'s intended behaviour
and what the game does everywhere else, but it is a change you can see rather
than a pure bug fix, so it is stated here rather than buried.

## Start from the stock ROM, not from a v1 output

**Do not stack these patches.** Each one already contains the ones before it -
v2 contains v1, v3 contains v2, v4 contains v3 - so there is nothing to gain by
stacking them. Start again from the unmodified NoPrgress ROM.

What actually happens if you try it anyway, measured rather than assumed.
Applying the v2 **BPS** to a v1 output is refused outright, because BPS records
the CRC32 of the ROM it expects:

```
$ flips --apply dqvi-noprgress-menufix-v2.bps v1-output.sfc out.sfc
This patch is not intended for this ROM.
```

**IPS cannot check its input**, so it will apply to anything and tell you it
succeeded. In this particular case that happens to be harmless, because the v2
IPS rewrites every byte v1 changed and the result is the correct v2 ROM, but
that is a property of these particular patches and not something to rely on in
general.
Do not stack patches and then assume it worked. Start from the stock ROM and
check the SHA-1 of what you get against the table below.

All four patches target the same starting point:

```
Dragon Quest VI with NoPrgress v0.90b2 applied, headerless, 4,194,304 bytes
CRC32  B545C548
SHA-1  7dd3b03a78ee76207fd10363d80bb64bf977ddd3
```

Check that hash before you patch. It is the single most common thing to get
wrong.

---

## Credits

**These are small corrections to somebody else's large piece of work.**

- **NoPrgress**, and **DeJap Translations** before them, for the English
  translation of Dragon Quest VI. This is a Japan-only release that stayed
  unplayable in English for over a decade. Translating a 4 MB Super Famicom RPG
  means rebuilding its text engine, refitting menus around a script that does
  not fit, and hand-editing 65816 assembly, all unpaid.
- The Info > All defect is **one deleted instruction in an area they were
  actively editing**, sitting immediately after a run of inline parameter bytes,
  which is exactly the kind of place a byte count goes wrong. The Forget defect
  is a memory allocation that collides with the original game's, which is the
  kind of thing that is close to invisible without the original developers'
  memory map. The Tactics-equip hang is not theirs at all - it is a defect in
  Enix's own 1995 code, present in the Japanese ROM, which the Japanese data
  never happens to trigger. All of them are slips in difficult work, not
  failings, and the translation is the reason this repository can exist at all.
- **Enix**, publisher of the original 1995 game, whose rights now sit with
  Square Enix. The fixes add nothing; they put bytes back, move three variables
  out of the way, and copy one of Enix's own routines over its broken twin.

---

## No ROMs here. Bring your own.

This repository contains **patches and a script only**. It does not, and will
not, contain a ROM image, the NoPrgress translation patch, or any pre-patched
build. You supply:

| What | Size | CRC32 | SHA-1 |
|---|---:|---|---|
| Dragon Quest VI, Japanese, headerless | 4,194,304 | `33304519` | `3e699dc7e064d6ac84b1981aa150fdf1672b5456` |
| The same ROM with NoPrgress v0.90b2 applied | 4,194,304 | `B545C548` | `7dd3b03a78ee76207fd10363d80bb64bf977ddd3` |

Get the translation patch from its own authors. Both ROMs must be **headerless**
(no 512-byte copier header). The Japanese ROM is only needed for the script,
which restores bytes from it; the patches need only the translated ROM.

---

## What goes wrong

### Info > All

Open the menu, choose **Info**, choose **All**, and press cancel before the
status screen has finished drawing. The game locks up completely: no crash
screen, no reset, just a frozen picture and music that keeps playing.

Romhacking.net's entry for the translation documents this and advises keeping
savestates handy. It is reproducible on demand once you know the timing, and it
happens with a **single party member at level 1 with no equipment**, so it is
not about long names or long item names.

**The Equip menu does not crash *this way*.** It has sometimes been described as
a second crash site for the interrupted-draw sequence; it was tested with the
same timing and does not fault. It does have a separate defect of its own, the
Tactics-equip hang, which is unrelated to drawing and is described below.

### Forget

Using **Forget** in the Remember conversation system produces jumbled repeating
text and then a black screen, with the game unrecoverable.

This is **not** intermittent, despite appearances. It is deterministic, and
depends on whether one of the original game's periodic memory clears happens to
fall in the middle of a message.

---

## Root cause, short version

### Info > All

A loop over party slots reads its upper bound from `$7E:3AC2`. Two things write
that address: one writes a sentinel `0xFF` meaning "not applicable", and another
writes the real party size over the top of it.

The Japanese ROM does both, in that order, every time. The translation is
missing the second write, so the bound stays at `0xFF`. The loop then accepts
slot index 1 on a one-member party, reads a table entry that was never
initialized, and hits an assertion the original developers left in the shipped
game: an infinite branch-to-itself at `$C4:560F`. The game does not crash, it
spins there forever.

Measured, from emulator trace logs of both ROMs running the same sequence:

```
Japanese : the bound reads $0001 at all 20 executions of the comparison
NoPrgress: the bound reads $00FF at 4 of 5, including the fatal one
```

### Forget

A memory allocation collision. The translation keeps its word-wrap state in
three variables at `$7E:379E`, `$7E:37A0` and `$7E:37A2`. All three sit inside a
112-byte block at `$7E:3768`-`$37D6` that the original game clears wholesale, in
code byte-identical to the Japanese ROM.

When a clear lands mid-message, the buffer and its length are destroyed
underneath a live cursor. What follows is a nine-step chain ending in a black
screen, traced instruction by instruction.

The fix moves the three variables somewhere the original game does not touch. It
changes **operands only**: same opcodes, same instruction lengths, no new code,
no hook, and no ROM free space consumed.

Full detail for both, including the byte-level proof, the refuted hypotheses and
the measurement errors made along the way, is in
**[docs/ANALYSIS.md](docs/ANALYSIS.md)**.

---

---

## The gold window, and why v3 exists

Open the info screen in the Japanese game and your gold is in the top right.
Open it in the translation and it is not there at all.

### What happened

English stat labels are wider than Japanese ones, so the status window was
widened to fit them. That left the gold window with nowhere to sit:

```
Japanese   status cols 10-21   gold cols 22-30    side by side
English    status cols 10-24   gold cols 16-23    gold underneath the status window
```

Having no room for it, the translation deleted the seven bytes that draw the
gold figure and padded the gap with a duplicated `RTL` epilogue so the
surrounding addresses still lined up. **That is the same technique as the
`STA $3AC2` deletion four bytes earlier** - the one that causes the Info > All
crash this repository already fixes. The two were almost certainly done in the
same sitting, for the same reason: making room.

### What v3 does about it

It moves the gold window to the top left, where the English layout has space,
and puts the draw call back. Twenty-five bytes:

```
0x033593   22 bytes   the draw call restored, at exact size over dead bytes
0x057E88    3 bytes   the window's position and width
```

The call is written over the English fifteen bytes plus that dead duplicate
epilogue, consuming it exactly, so nothing moves and no new space is needed.
The window draws string `$10`, a bare one-byte `G` - **the same substitution the
translation already uses at its other gold window**, applied to the one place it
was not applied.

### It restores original behaviour rather than adding anything

The gold window is the game's, not this patch's. It was in *Dragon Quest VI* in
1995, the translation lost it while making room for wider English labels, and v3
puts it back. Nothing is invented and no text is written.

Only the gold window's own descriptor changes. The status window, the command
menu and every other window in the game are byte-identical to the ones NoPrgress
shipped.

### How it was found

Two emulator traces of the same screen, one per ROM. Every address executed
during the Japanese trace was collected - 14,839 of them - mapped to file
offsets, and compared against the English ROM. That reduced the problem to seven
regions of divergence in code that demonstrably runs, one of which was the
deleted call.

This is the same technique that found the deleted `STA $3AC2`, and it is much
narrower than searching for constants.


---

## The Tactics-equip hang, and why v4 exists

Cycle in and out of a character's equipment through the Tactics menu enough
times and the game stops responding. No crash screen, no reset: the music keeps
playing and nothing accepts input.

**This one is not the translation's.** It is in Enix's 1995 code and it is in the
Japanese ROM too. The Japanese data never drives it into the failing state, which
is why it survived thirty years unreported, and it affects **v1, v2 and v3 of
this patch, the unpatched translation, and every build of the script-refill patch
before v2.0**.

### What it is

`$C3:1AB1` is a broken duplicate of `$C3:1D0E`. Both answer the same question -
the cursor is on an entry that cannot be selected, so where should it go - and
`$C3:1D0E` answers it properly: save the ordinal, honour the carry, check the
floor, and if there is nothing below, restore and search upward against a
ceiling.

`$C3:1AB1` steps back once, unconditionally, and commits whatever comes back.

### Why one wrong step is enough

One step past zero asks `$C3:1B1E` for an ordinal it cannot supply. **That
routine is not at fault** - it is bounded, and it reports failure the way this
codebase reports failure, by returning with the carry set. Its caller never
looks. The sentinel is then packed as though it were a screen position:

```
linear = (112/2)*16 + 1 = 897     row = 897>>5 = 28     col = 897&31 = 1
```

The tilemap is `$3068`-`$3767`: exactly 28 rows, so `$3068 + 28*64 = $3768`.
**Row 28 is not merely off the end - it is precisely the cursor bitmap the same
code reads.** The bad write corrupts the structure the next read depends on,
which is why it needs repeated cycling to start and why it never recovers once
it has.

### One producer, four consumers, and why chasing the symptom failed

Four of the eight callers of `$C3:1B1E` honour the carry it returns; four do not,
and every bit of the damage arrives through those four. Five builds that patched
consumers each moved the fault to the next one. The producer was right the whole
time.

The bad write was also doing two jobs at once: it corrupts the tilemap **and** it
is what parks the cursor off the visible list, nineteen rows below anywhere it
legitimately goes. Suppressing the write cured the hang and left a cursor drawn
over the item text, and no in-bounds replacement could restore the parking,
because the parking only works because the value is out of bounds.

### What v4 does about it

It mirrors `$C3:1D0E`'s search into `$C3:1AB1`. The initial check and the redraw
are untouched, so ordinary cursor movement is byte-identical and every menu that
was not faulting behaves exactly as before.

**The one visible change:** in edge cases the cursor may land on a different
entry than it used to, because it now searches down to the floor and up to the
ceiling instead of stepping back once. That is `$C3:1D0E`'s behaviour, which is
what the rest of the game does, but it is a change you can see rather than a
pure bug fix.

### How it was verified

Confirmed in play, then checked against a trace of the fixed build: the
out-of-range sentinel reaches none of the four consumers, the ordinal never goes
negative, nothing writes row 28, and the scan that used to spin exits cleanly on
every one of its 20 calls.

---

## How to apply

Two routes, and either works for **any of the four versions**. Route A applies
a ready-made patch and needs one ROM. Route B rebuilds from source and needs
both ROMs.

### Route A, the patch, with Flips

Use [Flips](https://github.com/Alcaro/Flips). Apply the patch you want to your
**already-translated** ROM.

```
flips --apply dqvi-noprgress-menufix-v1.bps "DQ6 NoPrgress.sfc" "DQ6 Fixed.sfc"
flips --apply dqvi-noprgress-menufix-v2.bps "DQ6 NoPrgress.sfc" "DQ6 Fixed.sfc"
flips --apply dqvi-noprgress-menufix-v3.bps "DQ6 NoPrgress.sfc" "DQ6 Fixed.sfc"
flips --apply dqvi-noprgress-menufix-v4.bps "DQ6 NoPrgress.sfc" "DQ6 Fixed.sfc"
```

**All four patches target the translated ROM (`B545C548`), not the Japanese
base, and not each other's output.** BPS records its expected source, so Flips refuses
a wrong ROM rather than producing a broken one. An IPS is included for tools
that cannot read BPS, but IPS cannot validate its input at all, so prefer the
BPS.

Every patch here was cross-checked against Flips as the reference
implementation rather than only against this repository's own code: Flips
applies both the BPS and the IPS to the expected result, and a patch Flips
generates independently produces the same ROM.

### Route B, the script, from both ROMs

One command per version. `--version` picks what you get; **1 is the default**,
so the command that built v1 still builds v1.

```
python DQVI_NoPrgress_Menu_Crash_Fix.py --jp "Dragon Quest VI - Maboroshi no Daichi (Japan).sfc" --en "DQ6 NoPrgress.sfc"
python DQVI_NoPrgress_Menu_Crash_Fix.py --jp "Dragon Quest VI - Maboroshi no Daichi (Japan).sfc" --en "DQ6 NoPrgress.sfc" --version 2
python DQVI_NoPrgress_Menu_Crash_Fix.py --jp "Dragon Quest VI - Maboroshi no Daichi (Japan).sfc" --en "DQ6 NoPrgress.sfc" --version 3
python DQVI_NoPrgress_Menu_Crash_Fix.py --jp "Dragon Quest VI - Maboroshi no Daichi (Japan).sfc" --en "DQ6 NoPrgress.sfc" --version 4
```

Python 3.8 or newer, standard library only, no pip and no external tools. It
verifies both inputs by SHA-1, checks that every byte it is about to change
holds exactly what it expects, refuses to write anything if any check fails, and
never modifies its inputs. `--help` explains what you need to supply. Route B
also regenerates the patch files, so you can confirm they match the ones shipped
here.

**`--version 3`**, which adds the gold window on top of v2:

![The fix script running with --version 3 in a clean folder, showing both ROMs verified by SHA-1, the restored STA $3AC2, the twenty-one Forget relocation sites, the gold window restoration at 0x033593 and 0x057E88, the recomputed checksum, and the hashes of all three outputs](screenshots/script-run-v3.png)

v1, v2 and v4 produce the same shape of output, in
[screenshots/script-run.png](screenshots/script-run.png) and
[screenshots/script-run-v2.png](screenshots/script-run-v2.png).

---

## Identifying what you have

CRC32 is **useless for identifying a `.bps` file**: every valid BPS patch
self-checks to `2144DF1C` by construction, so every BPS below shows the same
value. Use SHA-1.

| File | Size | SHA-1 |
|---|---:|---|
| `dqvi-noprgress-menufix-v1.bps` | 126 | `be1b972e179ee7bf76e7512b925195c1e8a7479b` |
| `dqvi-noprgress-menufix-v1.ips` | 106 | `7f34a16e83a2d40934652311dedcecc6ac0b4f12` |
| `dqvi-noprgress-menufix-v2.bps` | 208 | `54f97e60e9038ecaae7d22b623aa757a63293a99` |
| `dqvi-noprgress-menufix-v2.ips` | 241 | `1c6921aa886d1799a33d000c33f51fda3c7a12bd` |
| `dqvi-noprgress-menufix-v3.bps` | 233 | `45f1f42f68df186b5c835a198c5a5062b68f5099` |
| `dqvi-noprgress-menufix-v3.ips` | 279 | `c66eb3a7e40328023f6c697af08179ad485a993a` |
| `dqvi-noprgress-menufix-v4.bps` | 340 | `7ce5dd6ba324188a4a04b9c3c4f1926ddb9588cb` |
| `dqvi-noprgress-menufix-v4.ips` | 387 | `4fff01da97631d183c810429ee5c8b39745d0457` |

And the ROMs they produce:

| Output | Size | CRC32 | SHA-1 |
|---|---:|---|---|
| v1, `DQVI_NoPrgress_MenuFix.sfc` | 4,194,304 | `174D40F8` | `01e417a0036db27fc5a4102e012ceec82c56ca76` |
| v2, `DQVI_NoPrgress_MenuFix_v2.sfc` | 4,194,304 | `57823516` | `ba222c4b3fcc1c3dbe069272e25bdf33c3fe07a6` |
| v3, `DQVI_NoPrgress_MenuFix_v3.sfc` | 4,194,304 | `DACF8FD7` | `a4175c168ff83e5031f13040d27c2fd259c64047` |
| v4, `DQVI_NoPrgress_MenuFix_v4.sfc` | 4,194,304 | `2FF14A56` | `a9e10407284c911bf832875cb5f92769b8405ec7` |

**v1 changes 88 bytes** against the translated ROM:

```
0x00FFDC - 0x00FFE0    4 bytes    recomputed internal checksum and complement
0x033538 - 0x03358C   84 bytes    the restored instruction, and the 3-byte shift it undoes
```

**v2 changes 128 bytes**:

```
0x00FFDC - 0x00FFE0    4 bytes    recomputed internal checksum and complement
0x033538 - 0x03358C   84 bytes    the Info > All restoration, identical to v1
19 sites in bank $C0  38 bytes    relocated operands, 2 bytes each
0x00FE27, 0x00FF1D     2 bytes    two branch conditions
```

**v3 changes 141 bytes**:

```
0x00FFDC - 0x00FFE0    4 bytes    recomputed internal checksum and complement
0x033538 - 0x03358C   84 bytes    the Info > All restoration, identical to v1
19 sites in bank $C0  38 bytes    relocated operands, identical to v2
0x00FE27, 0x00FF1D     2 bytes    two branch conditions, identical to v2
0x033593 - 0x0335A9   22 bytes    the restored gold draw call
0x057E88 - 0x057E8B    3 bytes    the gold window's position and width
```

**v4 changes 239 bytes**:

```
0x00FFDC - 0x00FFE0    4 bytes    recomputed internal checksum and complement
0x033538 - 0x03358C   84 bytes    the Info > All restoration, identical to v1
19 sites in bank $C0  38 bytes    relocated operands, identical to v2
0x00FE27, 0x00FF1D     2 bytes    two branch conditions, identical to v2
0x033593 - 0x0335A9   22 bytes    the restored gold draw call, identical to v3
0x057E88 - 0x057E8B    3 bytes    the gold window's position and width, as v3
0x031ACA - 0x031AD8   14 bytes    JMP to the equip hook, and NOP padding
0x03FC80 - 0x03FCD4   84 bytes    the equip hook itself, over free space
```

The equip hook goes in free space at `$C3:FC80`, which held `0xFF` filler. The
script checks that it is still filler before writing, so it cannot quietly
overwrite something another patch put there.

Internal checksum goes from `0xD17A` to `0xD208` for v1, `0xD622` for v2,
`0xD501` for v3, and `0xACE5` for v4.
NoPrgress shipped a correct checksum, so recomputing it after changing the ROM
is the right thing to do rather than leaving a stale value behind.

---

## What these patches do not fix

These patches fix specific crashes and hangs. Everything else about the
translation is unchanged, including the following, which are **inherited and out
of scope**.

If you hit any of it, it came with the translation and is not a defect in these
fixes.

### Untranslated text

The NoPrgress translation is roughly 90% complete. Romhacking.net describes the
remainder as "random strings here and there that have no real bearing on the
game."

**These patches change no text whatsoever.** They do not add, alter or complete
any translation. Japanese text you encounter in play is original to the
translation, not caused by these patches.

For what it is worth, the main dialogue is not where the gap is. The message
table holds 870 entries, and all 870 decode to the English glyph set: 123
distinct symbols across roughly 430,000 decoded characters, with no
Japanese-scale symbol set anywhere in it. The untranslated remainder lives in
other text, not in the story script.

### The unbounded fill at `$C0:FDD8`-`$C0:FDF0`

The translation's word-wrap loop appends to its buffer without a length cap, and
was measured writing 136 bytes past the end of it.

**v2 contains this rather than fixing it.** Relocating the buffer moves it
somewhere with 200 bytes of headroom instead of 54, so the overspill no longer
lands on live game state. The unbounded loop itself is still there. It is
documented in [docs/ANALYSIS.md](docs/ANALYSIS.md) and listed as an open defect.

This is also why the advice above is to keep savestates the first time you use
Forget: no test session ever triggered the overrun, so the headroom is insurance
that has not been exercised in practice.

### Anything else inherited

Any other translation bug, typo, formatting oddity, or behavior not specifically
named as fixed here remains exactly as NoPrgress shipped it. These patches
address the defects named above and nothing else.

---

## Testing status

### v1, Info > All

**Confirmed working in game, 2026-08-17.**

Tested on `DQVI_NoPrgress_MenuFix.sfc`, CRC32 `174D40F8`, in **MesenCE**, with a
**solo party at level 1** with no equipment. That is the exact state that used to
reproduce the hang on demand.

- The previously fatal sequence, **enter Info > All and back out before the
  screen finishes drawing**, was repeated and **no longer hangs**.
- The normal path, entering and letting the screen finish before backing out,
  also works.
- **The two phantom empty party windows are gone**, and **the Def column now
  shows a number instead of `?`**.

That last point is the part worth dwelling on. Those two artifacts were the
visible face of the same defect: the slot loop was running past the end of the
party, drawing windows for members that do not exist and reading stats that were
never initialized. They disappear because the loop bound is correct again, which
is evidence the **cause** was fixed rather than the crash merely suppressed. A
guard that only stopped the hang would have left both artifacts on screen.

Confirmed at instruction level on a save with a **full eight-member party**:

- `$C3:3538 STA $3AC2` executes **8 times, writing `$0008`**, the real party
  size. This is the instruction that was deleted.
- `$C3:964A CMP $3AC2` reads **`$0008` at all 8 executions**, never the `$00FF`
  sentinel that caused the hang.
- **7 of those 8 comparisons reject the slot**, with 1 proceeding. That is the
  same ratio the Japanese ROM produces.
- The original developers' assertion at `$C4:560F` executes **once and never with
  `Z` set**, so it is passed harmlessly rather than tripped.

Info > All has been exercised at **two party sizes**, solo level 1 and a full
eight-member party, with no hang on either.

### v2, Forget

**Confirmed working in game, 2026-08-17.** The Forget sequence runs to
completion with no hang, no garbled text and no visible corruption. Ordinary
dialogue, menus, shops and battle all behave normally.

Verified at instruction level across **two independent traced sessions**, 90 GB
and 58.75 GB, the second spanning roughly 23,000 frames on a different save.
Coverage includes battle, running from battle, spells, NPC and field dialogue,
shops, buying, menus, Info > All, Equip and Forget.

In both sessions:

- No underflow at the arithmetic that used to receive a corrupted value.
- No read of an uninitialized buffer slot.
- No execution outside legitimate banks, and none in open bus.
- No fabricated message ID.
- **The relocated storage is touched only by the code that allocates it.** In the
  second session that is 8,727 writes and 13,420 reads across nineteen
  instruction sites, with **zero foreign accesses**, and each of the three
  variables stays in its own set of sites.
- **No original-game code touches the relocated region, and no translation code
  touches the original game's block any more.** A static scan of every
  instruction the translation added returns zero references into it.

One WRAM snapshot was captured mid-message and shows the relocation live: the
new location holding a real length and real glyph data, the old location dead,
and the original game's block untouched.

**Not verified:** a full playthrough, and emulators other than MesenCE. The two
branch-condition changes in v2 were not individually isolated: they are in the
build that was tested, and both are provable no-ops on a healthy path, but no
build was made with the relocation alone. Reports welcome in the issues.

### v4, the Tactics-equip hang

**Confirmed working in game, 2026-08-20.** Cycling in and out of equipment
through the Tactics menu, the sequence that used to lock the game, **no longer
hangs**, and there is **no visual artifact** - which matters, because five
earlier attempts that patched the wrong end of the problem each left a cursor
drawn on top of the item text. A build that stops the hang and leaves a stray
cursor has moved the fault, not fixed it.

Verified afterwards from an instruction-level trace of the fixed build, checking
the things that would have to be true if the cause were gone rather than
suppressed:

- **The new search runs and succeeds.** 61 entries, 61 taken `BCC` exits: the
  carry that the old code ignored is now honoured on every call.
- **The out-of-range sentinel reaches none of its four consumers.** Zero.
- **The ordinal never goes negative.** Observed values 0, 1, 4, 5, 8.
- **Nothing writes row 28**, and `$376B` - the byte in the cursor bitmap that the
  bad write used to corrupt - holds `$0000` throughout.
- **The scan that used to spin terminates every time**: 286 reads across 20
  clean exits, against 122 across 9 for the Japanese ROM on the same activity.

The Japanese ROM was traced alongside as a control. It never enters the failing
state at all, which is consistent with a defect that has been in the game since
1995 and that only English data reaches.

**Not verified:** a full playthrough, and emulators other than MesenCE. The
behavioural change described above is deliberate and is what `$C3:1D0E` does, but
if you see the cursor land somewhere unexpected after a Tactics-equip cycle, that
is the change and not a new fault.

---

## Reporting a problem

Open a [GitHub issue](../../issues). Please include:

1. **The SHA-1 of the ROM you are running.** Not the CRC32, and not the name of
   the file. This identifies which patch you applied, or whether a patch applied
   correctly at all, and it is the first thing that will be asked.
2. **The SHA-1 of the ROM you patched from**, if you still have it.
3. **Steps to reproduce**, including where you were and what you did
   immediately before.
4. Which emulator and version.

A savestate or an emulator trace log is welcome but not expected. Please do not
attach ROMs.

If the text is in Japanese, or something looks odd but nothing crashed, read
"What these patches do not fix" above first.

---

## Contents

```
README.md                          this file
DQVI_NoPrgress_Menu_Crash_Fix.py   builds any of the four versions from both ROMs, stdlib only
dqvi-noprgress-menufix-v1.bps      v1 patch, targets the translated ROM B545C548
dqvi-noprgress-menufix-v1.ips      v1 patch as IPS, for older tools
dqvi-noprgress-menufix-v2.bps      v2 patch, targets the translated ROM B545C548
dqvi-noprgress-menufix-v2.ips      v2 patch as IPS, for older tools
dqvi-noprgress-menufix-v3.bps      v3 patch, targets the translated ROM B545C548
dqvi-noprgress-menufix-v3.ips      v3 patch as IPS, for older tools
dqvi-noprgress-menufix-v4.bps      v4 patch, targets the translated ROM B545C548
dqvi-noprgress-menufix-v4.ips      v4 patch as IPS, for older tools
docs/ANALYSIS.md                   how all four were found, and why the fixes are safe
LICENSE
```

---

## License

See [LICENSE](LICENSE). The script and the documentation are the original work
here. The patches are differences against NoPrgress's translation and restore or
rearrange bytes that Square Enix now holds the rights to; they are published in
the same spirit as the translation they correct, and they are useless without a
ROM you already have.
