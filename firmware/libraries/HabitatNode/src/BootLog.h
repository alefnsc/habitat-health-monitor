// Boot counter kept as an append-only log in one flash sector.
//
// Why not the EEPROM emulation: on the ESP8266, EEPROM.commit() erases the whole sector and
// writes it back on every boot. Lose power between the two and the sector is blank, so the
// next boot starts again at 1; a failed erase or write keeps the old value, so a number
// repeats. The bench saw both on 2026-11-15 (tilt-1 boots 4, 7, 9, 8, 10, 11, 1, 2 within an
// hour; validacao-2026-11-15/relatorio-sensores-painel.md, gap 1) and the hub, keyed on
// (node, boot, seq), dropped valid readings of the repeated boots.
//
// Here the sector is a log of 8-byte slots (n, ~n). A boot reads the whole log, takes the
// highest valid number, adds one for itself and one for every non-blank slot written after
// that number, and programs the next free slot. NOR flash programming only clears bits, so
// nothing is erased until all 512 slots are used; that one erase every 512 boots is the only
// moment a power loss can lose the count. A torn write (power lost mid-slot) fails the check
// word and still counts as a boot that happened, so the next number is higher. Each write is
// read back; one that does not verify is retried in the next slot. The residual: power lost
// before the first bit was cleared, or a flash that refuses to program at all, repeats the
// number. The hub tolerates that (hub/store.py, the `clash` column).
//
// Pure C++. Flash is any type with
//   bool read(uint32_t off, void* buf, uint32_t len);
//   bool program(uint32_t off, const void* buf, uint32_t len);  // clears bits only
//   bool erase();                                                // whole sector to 0xFF
// so test/test_boot.cpp runs it on the host against a NOR flash model.
#pragma once

#include <stdint.h>

namespace habitat {

struct BootLog {
  static const uint32_t kSectorBytes = 4096;
  static const uint32_t kSlotBytes = 8;
  static const uint32_t kSlots = kSectorBytes / kSlotBytes;
  static const int kAttempts = 3;

  struct Slot {
    uint32_t n;
    uint32_t check;
  };

  static bool blank(const Slot& s) { return s.n == 0xFFFFFFFFu && s.check == 0xFFFFFFFFu; }
  static bool valid(const Slot& s) { return s.check == ~s.n; }

  template <class Flash>
  static bool readSlot(Flash& flash, uint32_t i, Slot& s) {
    return flash.read(i * kSlotBytes, &s, kSlotBytes);
  }

  // Reads the log, claims the next boot number, writes it and returns it (first ever boot: 1).
  template <class Flash>
  static uint32_t bump(Flash& flash) {
    uint32_t best = 0;  // highest valid number in the log
    uint32_t after = 0;  // non-blank slots written after it (torn writes, each one a boot)
    uint32_t next = 0;  // the slot after the last non-blank one
    for (uint32_t i = 0; i < kSlots; ++i) {
      Slot s;
      if (!readSlot(flash, i, s) || blank(s)) continue;
      next = i + 1;
      if (valid(s) && s.n >= best) {
        best = s.n;
        after = 0;
      } else {
        ++after;
      }
    }
    uint32_t n = best + after + 1;
    if (next >= kSlots) {  // full: the one erase; power lost right here loses the count
      flash.erase();
      next = 0;
    }
    Slot w = {n, ~n};
    for (int attempt = 0; attempt < kAttempts && next < kSlots; ++attempt, ++next) {
      flash.program(next * kSlotBytes, &w, kSlotBytes);
      Slot back;
      if (readSlot(flash, next, back) && valid(back) && back.n == n) break;
    }
    return n;
  }
};

}  // namespace habitat
