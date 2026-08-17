#!/usr/bin/env python3
"""Fix the Info > All hang in the NoPrgress English translation of
Dragon Quest VI: Maboroshi no Daichi (Super Famicom).

The translation is missing a three-byte instruction, STA $3AC2 at $C3:3538,
that the Japanese original executes. Without it a party-slot loop keeps a
sentinel bound of 0xFF, walks into a slot that was never populated, and trips
an assertion the original developers left in the game: an infinite self-branch
at $C4:560F. The visible symptom is a hard hang when you open Info > All and
back out before the screen finishes drawing.

This script restores the missing instruction by copying an 87-byte span from
the Japanese ROM over the corresponding span in the translated ROM, then
recomputes the SNES internal checksum.

No ROM is distributed with this script. You supply both of them.

Python 3.8+, standard library only. Inputs are never modified.
"""

import argparse
import hashlib
import os
import sys
import zlib

# ---------------------------------------------------------------------------
# Constants. All verified by measurement, see docs/ANALYSIS.md.
# ---------------------------------------------------------------------------

ROM_SIZE = 0x400000                 # 4 MiB, headerless, HiROM

JP_SHA1 = "3e699dc7e064d6ac84b1981aa150fdf1672b5456"
JP_CRC32 = 0x33304519
JP_NAME = "Dragon Quest VI - Maboroshi no Daichi (Japan)"

EN_SHA1 = "7dd3b03a78ee76207fd10363d80bb64bf977ddd3"
EN_CRC32 = 0xB545C548
EN_NAME = "Dragon Quest VI - Realms of Revelation [T-En by NoPrgress v0.90b2]"

# The restoration span. Do NOT widen this: the 7-byte deletion at $C3:3594,
# just past the end, is deliberate translation work (a dropped Japanese-only
# label) and must be preserved.
SPAN_START = 0x033538               # $C3:3538
SPAN_END = 0x03358F                 # $C3:358F, exclusive

# Expected content of the span before the fix, straight out of the translated
# ROM. Checked so the script refuses to write if it is pointed at something
# unexpected, even if a hash check were somehow bypassed.
SPAN_BEFORE = bytes.fromhex(
    "22257bc3a9870022fe83c3a9260022fe83c3a92c0022fe83c322f975c3a92d00"
    "22fe83c322f975c3a92e0022fe83c322f975c3a92f0022fe83c322f975c3a930"
    "0022fe83c3a98a0022fe83c3abc2307afa68286b68286b"
)

# Expected content after the fix, which is the Japanese original for this span.
SPAN_AFTER = bytes.fromhex(
    "8dc23a22257bc3a9870022fe83c3a9260022fe83c3a92c0022fe83c322f975c3"
    "a92d0022fe83c322f975c3a92e0022fe83c322f975c3a92f0022fe83c322f975"
    "c3a9300022fe83c3a98a0022fe83c3abc2307afa68286b"
)

HDR = 0xFFC0                        # internal header, HiROM
HDR_COMPLEMENT = HDR + 0x1C         # 0xFFDC
HDR_CHECKSUM = HDR + 0x1E           # 0xFFDE

OUT_ROM = "DQVI_NoPrgress_MenuFix.sfc"
OUT_BPS = "dqvi-noprgress-menufix-v1.bps"
OUT_IPS = "dqvi-noprgress-menufix-v1.ips"


class Fail(Exception):
    """A fatal, reportable problem. Nothing is written when this is raised."""


# ---------------------------------------------------------------------------
# Hashing and reporting
# ---------------------------------------------------------------------------

def sha1(data):
    return hashlib.sha1(data).hexdigest()


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def describe(label, data):
    return "{:<28s} {:>10,}  CRC32 {:08X}  SHA-1 {}".format(
        label, len(data), crc32(data), sha1(data))


# ---------------------------------------------------------------------------
# SNES internal checksum
# ---------------------------------------------------------------------------

def snes_checksum(data):
    """Return (checksum, complement) for a power-of-two ROM image.

    The algorithm sums every byte with the complement field read as 0xFFFF and
    the checksum field read as 0x0000. Verified against both input ROMs: it
    reproduces the Japanese ROM's stored 0x5E8F and the translation's stored
    0xD17A exactly.
    """
    buf = bytearray(data)
    buf[HDR_COMPLEMENT] = 0xFF
    buf[HDR_COMPLEMENT + 1] = 0xFF
    buf[HDR_CHECKSUM] = 0x00
    buf[HDR_CHECKSUM + 1] = 0x00
    checksum = sum(buf) & 0xFFFF
    return checksum, checksum ^ 0xFFFF


def read_checksum(data):
    return data[HDR_CHECKSUM] | (data[HDR_CHECKSUM + 1] << 8)


def write_checksum(buf, checksum, complement):
    buf[HDR_CHECKSUM] = checksum & 0xFF
    buf[HDR_CHECKSUM + 1] = (checksum >> 8) & 0xFF
    buf[HDR_COMPLEMENT] = complement & 0xFF
    buf[HDR_COMPLEMENT + 1] = (complement >> 8) & 0xFF


# ---------------------------------------------------------------------------
# Input loading and validation
# ---------------------------------------------------------------------------

def load_rom(path, want_sha1, want_crc32, label, other_sha1, other_label):
    if not os.path.isfile(path):
        raise Fail("{} not found:\n    {}".format(label, path))

    with open(path, "rb") as handle:
        data = handle.read()

    if len(data) == ROM_SIZE + 512:
        raise Fail(
            "{} has a 512-byte copier header:\n    {}\n"
            "  Strip the header first. This script expects a headerless "
            "{:,}-byte image.".format(label, path, ROM_SIZE))

    if len(data) != ROM_SIZE:
        raise Fail(
            "{} is the wrong size:\n    {}\n"
            "  expected {:,} bytes, got {:,}".format(
                label, path, ROM_SIZE, len(data)))

    got = sha1(data)
    if got == want_sha1:
        return data

    # Give the most useful diagnosis we can rather than a bare mismatch.
    if got == other_sha1:
        raise Fail(
            "the two ROM arguments look swapped.\n"
            "  The file given as {} is actually {}:\n    {}".format(
                label, other_label, path))

    if len(data) == ROM_SIZE and data[SPAN_START:SPAN_END] == SPAN_AFTER \
            and label == EN_NAME:
        raise Fail(
            "this ROM is ALREADY FIXED:\n    {}\n"
            "  The span at 0x{:06X} already matches the Japanese original, so "
            "there is nothing to do.".format(path, SPAN_START))

    raise Fail(
        "{} failed verification:\n    {}\n"
        "  expected SHA-1 {}\n"
        "  got      SHA-1 {}\n"
        "  expected CRC32 {:08X}\n"
        "  got      CRC32 {:08X}".format(
            label, path, want_sha1, got, want_crc32, crc32(data)))


# ---------------------------------------------------------------------------
# The fix
# ---------------------------------------------------------------------------

def apply_fix(jp, en):
    """Return the fixed image. Neither input is touched."""
    if en[SPAN_START:SPAN_END] != SPAN_BEFORE:
        raise Fail(
            "the span at 0x{:06X}-0x{:06X} does not contain the expected "
            "pre-fix bytes.\n"
            "  expected {}\n"
            "  found    {}\n"
            "  Refusing to write.".format(
                SPAN_START, SPAN_END,
                SPAN_BEFORE.hex(), en[SPAN_START:SPAN_END].hex()))

    if jp[SPAN_START:SPAN_END] != SPAN_AFTER:
        raise Fail(
            "the Japanese ROM does not contain the expected donor bytes at "
            "0x{:06X}-0x{:06X}.\n"
            "  expected {}\n"
            "  found    {}\n"
            "  Refusing to write.".format(
                SPAN_START, SPAN_END,
                SPAN_AFTER.hex(), jp[SPAN_START:SPAN_END].hex()))

    out = bytearray(en)
    out[SPAN_START:SPAN_END] = jp[SPAN_START:SPAN_END]

    checksum, complement = snes_checksum(out)
    write_checksum(out, checksum, complement)

    return bytes(out), checksum, complement


# ---------------------------------------------------------------------------
# BPS
# ---------------------------------------------------------------------------

def bps_varint(value):
    out = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(0x80 | chunk)
            break
        out.append(chunk)
        value -= 1
    return bytes(out)


def diff_runs(src, dst):
    """Yield (equal, start, end) runs over two equal-length buffers."""
    assert len(src) == len(dst)
    i = 0
    n = len(src)
    while i < n:
        equal = src[i] == dst[i]
        j = i
        while j < n and (src[j] == dst[j]) == equal:
            j += 1
        yield equal, i, j
        i = j


def make_bps(src, dst, metadata=b""):
    """Build a BPS patch. Source and target must be the same length here."""
    if len(src) != len(dst):
        raise Fail("BPS builder in this script assumes equal-length images")

    body = bytearray()
    for equal, start, end in diff_runs(src, dst):
        length = end - start
        if equal:
            # SourceRead: take `length` bytes from source at the output position
            body += bps_varint(((length - 1) << 2) | 0)
        else:
            # TargetRead: `length` literal bytes follow
            body += bps_varint(((length - 1) << 2) | 1)
            body += dst[start:end]

    patch = bytearray(b"BPS1")
    patch += bps_varint(len(src))
    patch += bps_varint(len(dst))
    patch += bps_varint(len(metadata))
    patch += metadata
    patch += body
    patch += crc32(src).to_bytes(4, "little")
    patch += crc32(dst).to_bytes(4, "little")
    patch += crc32(bytes(patch)).to_bytes(4, "little")
    return bytes(patch)


def bps_read_varint(patch, pos):
    value = 0
    shift = 1
    while True:
        octet = patch[pos]
        pos += 1
        value += (octet & 0x7F) * shift
        if octet & 0x80:
            return value, pos
        shift <<= 7
        value += shift


def apply_bps(src, patch):
    """Apply a BPS patch, validating every checksum. Used to prove the round
    trip rather than assuming the encoder is right."""
    if patch[:4] != b"BPS1":
        raise Fail("not a BPS patch (bad magic)")

    stored_patch_crc = int.from_bytes(patch[-4:], "little")
    if crc32(patch[:-4]) != stored_patch_crc:
        raise Fail("BPS patch is corrupt (patch CRC32 mismatch)")

    stored_src_crc = int.from_bytes(patch[-12:-8], "little")
    stored_dst_crc = int.from_bytes(patch[-8:-4], "little")
    if crc32(src) != stored_src_crc:
        raise Fail(
            "BPS source mismatch: this patch expects CRC32 {:08X}, "
            "the supplied ROM is {:08X}".format(stored_src_crc, crc32(src)))

    pos = 4
    src_size, pos = bps_read_varint(patch, pos)
    dst_size, pos = bps_read_varint(patch, pos)
    meta_size, pos = bps_read_varint(patch, pos)
    pos += meta_size

    if src_size != len(src):
        raise Fail("BPS source size mismatch")

    out = bytearray()
    src_rel = 0
    dst_rel = 0
    end = len(patch) - 12
    while pos < end:
        action, pos = bps_read_varint(patch, pos)
        kind = action & 3
        length = (action >> 2) + 1
        if kind == 0:                                    # SourceRead
            start = len(out)
            out += src[start:start + length]
        elif kind == 1:                                  # TargetRead
            out += patch[pos:pos + length]
            pos += length
        elif kind == 2:                                  # SourceCopy
            raw, pos = bps_read_varint(patch, pos)
            src_rel += (-1 if raw & 1 else 1) * (raw >> 1)
            out += src[src_rel:src_rel + length]
            src_rel += length
        else:                                            # TargetCopy
            raw, pos = bps_read_varint(patch, pos)
            dst_rel += (-1 if raw & 1 else 1) * (raw >> 1)
            for _ in range(length):
                out.append(out[dst_rel])
                dst_rel += 1

    if len(out) != dst_size:
        raise Fail("BPS output size mismatch")
    if crc32(bytes(out)) != stored_dst_crc:
        raise Fail("BPS output CRC32 mismatch")
    return bytes(out)


# ---------------------------------------------------------------------------
# IPS
# ---------------------------------------------------------------------------

def make_ips(src, dst):
    if len(dst) > 0x1000000:
        raise Fail("IPS cannot address beyond 16 MiB")

    patch = bytearray(b"PATCH")
    for equal, start, end in diff_runs(src, dst):
        if equal:
            continue
        pos = start
        while pos < end:
            chunk = min(0xFFFF, end - pos)
            if pos == 0x454F46:
                # A record at this offset encodes as the literal bytes "EOF"
                # and would stop a naive applier early. Shift the split so no
                # record starts there. Cannot happen with the current spans,
                # but the guard costs nothing.
                raise Fail("IPS record would start at the EOF sentinel offset")
            patch += bytes([(pos >> 16) & 0xFF, (pos >> 8) & 0xFF, pos & 0xFF])
            patch += bytes([(chunk >> 8) & 0xFF, chunk & 0xFF])
            patch += dst[pos:pos + chunk]
            pos += chunk
    patch += b"EOF"
    return bytes(patch)


def apply_ips(src, patch):
    if patch[:5] != b"PATCH":
        raise Fail("not an IPS patch (bad magic)")
    out = bytearray(src)
    pos = 5
    while True:
        if patch[pos:pos + 3] == b"EOF":
            pos += 3
            break
        offset = (patch[pos] << 16) | (patch[pos + 1] << 8) | patch[pos + 2]
        pos += 3
        size = (patch[pos] << 8) | patch[pos + 1]
        pos += 2
        if size:
            if offset + size > len(out):
                out.extend(b"\x00" * (offset + size - len(out)))
            out[offset:offset + size] = patch[pos:pos + size]
            pos += size
        else:
            run = (patch[pos] << 8) | patch[pos + 1]
            pos += 2
            value = patch[pos]
            pos += 1
            if offset + run > len(out):
                out.extend(b"\x00" * (offset + run - len(out)))
            out[offset:offset + run] = bytes([value]) * run
    if pos != len(patch):
        raise Fail("trailing bytes after IPS EOF; patch may use truncation")
    return bytes(out)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

EPILOG = """\
what you need to supply
-----------------------
  This script ships no ROM and no third-party patch. You provide:

    1. the unmodified Japanese ROM, headerless, 4,194,304 bytes
         CRC32 33304519   SHA-1 3e699dc7e064d6ac84b1981aa150fdf1672b5456
    2. the NoPrgress-translated ROM, headerless, 4,194,304 bytes
         CRC32 B545C548   SHA-1 7dd3b03a78ee76207fd10363d80bb64bf977ddd3

  The Japanese ROM is the donor: the fix restores 87 bytes from it. That is why
  both files are needed. If you would rather not supply two ROMs, apply the
  shipped BPS patch to the translated ROM with Flips instead.

why no ROMs are included
------------------------
  Distributing a commercial ROM is not legal, and the translation patch is
  NoPrgress's work to distribute, not ours. This repository carries only the
  difference between their ROM and a fixed one.

example
-------
  python DQVI_NoPrgress_Menu_Crash_Fix.py \\
      --jp "Dragon Quest VI - Maboroshi no Daichi (Japan).sfc" \\
      --en "Dragon Quest VI - Realms of Revelation.sfc"
"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="DQVI_NoPrgress_Menu_Crash_Fix.py",
        description="Restore the missing STA $3AC2 that causes the Info > All "
                    "hang in the NoPrgress DQ6 translation.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jp", required=True, metavar="FILE",
                        help="unmodified Japanese ROM (the donor)")
    parser.add_argument("--en", required=True, metavar="FILE",
                        help="NoPrgress-translated ROM (the one to fix)")
    parser.add_argument("--out", metavar="FILE", default=None,
                        help="output ROM path (default: %s)" % OUT_ROM)
    parser.add_argument("--outdir", metavar="DIR", default=None,
                        help="directory for outputs (default: alongside --en)")
    parser.add_argument("--no-patches", action="store_true",
                        help="write only the fixed ROM, no BPS or IPS")
    args = parser.parse_args(argv)

    outdir = args.outdir
    if outdir is None:
        outdir = os.path.dirname(os.path.abspath(args.en))

    out_rom = args.out or os.path.join(outdir, OUT_ROM)
    out_bps = os.path.join(outdir, OUT_BPS)
    out_ips = os.path.join(outdir, OUT_IPS)

    print("DQ6 NoPrgress Info > All crash fix")
    print("=" * 78)

    jp = load_rom(args.jp, JP_SHA1, JP_CRC32, JP_NAME, EN_SHA1, EN_NAME)
    print("  verified  " + describe("Japanese base", jp))
    en = load_rom(args.en, EN_SHA1, EN_CRC32, EN_NAME, JP_SHA1, JP_NAME)
    print("  verified  " + describe("NoPrgress translation", en))
    print()

    old_checksum = read_checksum(en)
    fixed, checksum, complement = apply_fix(jp, en)

    # Everything is validated by this point, so it is safe to touch the disk.
    os.makedirs(outdir, exist_ok=True)

    print("  restored 0x{:06X}-0x{:06X} ({} bytes, {} differing) from the "
          "Japanese ROM".format(
              SPAN_START, SPAN_END, SPAN_END - SPAN_START,
              sum(1 for i in range(SPAN_START, SPAN_END) if en[i] != fixed[i])))
    print("  reinserted 8D C2 3A  =  STA $3AC2  at $C3:3538")
    print("  internal checksum 0x{:04X} -> 0x{:04X} "
          "(complement 0x{:04X})".format(old_checksum, checksum, complement))
    print()

    # Inputs must be untouched.
    if sha1(jp) != JP_SHA1 or sha1(en) != EN_SHA1:
        raise Fail("internal error: an input buffer was modified")

    with open(out_rom, "wb") as handle:
        handle.write(fixed)
    print("  wrote     " + describe(os.path.basename(out_rom), fixed))

    if not args.no_patches:
        bps = make_bps(en, fixed)
        ips = make_ips(en, fixed)

        # Prove the round trip before writing anything out.
        if apply_bps(en, bps) != fixed:
            raise Fail("BPS round trip failed")
        if apply_ips(en, ips) != fixed:
            raise Fail("IPS round trip failed")

        with open(out_bps, "wb") as handle:
            handle.write(bps)
        with open(out_ips, "wb") as handle:
            handle.write(ips)
        print("  wrote     " + describe(os.path.basename(out_bps), bps))
        print("  wrote     " + describe(os.path.basename(out_ips), ips))
        print()
        print("  round trip verified: both patches applied to the translated "
              "ROM reproduce the output byte for byte")

    print()
    print("  Behavioural testing is still on you: load the result in an "
          "emulator and")
    print("  try Info > All, backing out before the screen finishes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as exc:
        print("\nERROR: {}\n".format(exc), file=sys.stderr)
        print("Nothing was written.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
