// Host tests for BootLog.h: the boot counter as an append-only log in one flash sector.
// Bench 2026-11-15 (validacao-2026-11-15/relatorio-sensores-painel.md, gap 1): the tilt node's
// boot numbers ran 4, 7, 9, 8, 10, 11, 1, 2, so the per-boot erase-then-write of the EEPROM
// emulation lost or reverted the count. These tests pin the behaviour that replaces it.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "BootLog.h"

using habitat::BootLog;

// A 4 KB sector that behaves like NOR flash: programming only clears bits, erase sets all ones.
// die_after >= 0 cuts the power during the next program() after that many bytes; the node then
// stays off (program() refused) until the test sets power_on().
struct FakeFlash {
  uint8_t mem[BootLog::kSectorBytes];
  int die_after = -1;
  bool power_dies = true;  // false: the cut write is a brown-out, the node stays up
  bool off = false;
  bool refuse_erase = false;
  int erases = 0;
  int programs = 0;

  FakeFlash() { memset(mem, 0xFF, sizeof mem); }
  void power_on() { off = false; }

  bool read(uint32_t off_, void* buf, uint32_t len) {
    memcpy(buf, mem + off_, len);
    return true;
  }
  bool program(uint32_t off_, const void* buf, uint32_t len) {
    ++programs;
    if (off) return false;
    const uint8_t* b = static_cast<const uint8_t*>(buf);
    for (uint32_t i = 0; i < len; ++i) {
      if (die_after >= 0 && static_cast<int>(i) == die_after) {
        die_after = -1;
        off = power_dies;
        return false;
      }
      mem[off_ + i] &= b[i];
    }
    return true;
  }
  bool erase() {
    if (refuse_erase) return false;
    memset(mem, 0xFF, sizeof mem);
    ++erases;
    return true;
  }
};

static void put32(FakeFlash& f, uint32_t off, uint32_t v) { memcpy(f.mem + off, &v, 4); }

int main() {
  {  // a fresh sector counts 1, 2, 3 without ever erasing
    FakeFlash f;
    assert(BootLog::bump(f) == 1);
    assert(BootLog::bump(f) == 2);
    assert(BootLog::bump(f) == 3);
    assert(f.erases == 0);
  }
  {  // the old EEPROM image (the number at offset 0, the rest erased) is one torn slot: 2, then 3
    FakeFlash f;
    put32(f, 0, 9);
    assert(BootLog::bump(f) == 2);
    assert(BootLog::bump(f) == 3);
  }
  {  // power lost half-way through the write: the next boot still gets a higher number
    FakeFlash f;
    assert(BootLog::bump(f) == 1);
    f.die_after = 4;  // the number is in flash, its check word is not
    assert(BootLog::bump(f) == 2);
    f.power_on();
    assert(BootLog::bump(f) == 3);
    assert(BootLog::bump(f) == 4);
  }
  {  // a write that fails while the node stays up is retried in the next slot, and counts once
    FakeFlash f;
    assert(BootLog::bump(f) == 1);
    f.die_after = 4;
    f.power_dies = false;
    int before = f.programs;
    uint32_t n = BootLog::bump(f);
    assert(n == 2 && f.programs - before == 2);
    assert(BootLog::bump(f) == 3);
  }
  {  // residual: power lost before any bit was cleared repeats the number (nothing to read back)
    FakeFlash f;
    assert(BootLog::bump(f) == 1);
    f.die_after = 0;
    assert(BootLog::bump(f) == 2);
    f.power_on();
    assert(BootLog::bump(f) == 2);
  }
  {  // a blank gap inside the log does not hide the slots after it
    FakeFlash f;
    assert(BootLog::bump(f) == 1);
    assert(BootLog::bump(f) == 2);
    memset(f.mem, 0xFF, BootLog::kSlotBytes);  // slot 0 wiped, slot 1 still holds 2
    assert(BootLog::bump(f) == 3);
  }
  {  // the count never goes backwards, even if a later slot holds a smaller valid number
    FakeFlash f;
    put32(f, 0, 9);
    put32(f, 4, ~9u);
    put32(f, 8, 4);
    put32(f, 12, ~4u);
    assert(BootLog::bump(f) > 9);
  }
  {  // a full sector is erased once and the count carries on
    FakeFlash f;
    for (uint32_t i = 1; i <= BootLog::kSlots; ++i) assert(BootLog::bump(f) == i);
    assert(f.erases == 0);
    assert(BootLog::bump(f) == BootLog::kSlots + 1);
    assert(f.erases == 1);
    assert(BootLog::bump(f) == BootLog::kSlots + 2);
    assert(f.erases == 1);
  }
  {  // a refused erase on a full sector still returns the right number for this boot
    FakeFlash f;
    for (uint32_t i = 1; i <= BootLog::kSlots; ++i) BootLog::bump(f);
    f.refuse_erase = true;
    assert(BootLog::bump(f) == BootLog::kSlots + 1);
  }
  std::puts("ok");
  return 0;
}
