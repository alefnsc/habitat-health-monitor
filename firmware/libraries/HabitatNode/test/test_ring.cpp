#include <cassert>
#include <cstdio>

#include "RingBuffer.h"

int main() {
  {  // test_ring_fifo
    RingBuffer<int, 32> rb;
    rb.push(1); rb.push(2); rb.push(3);
    int v = 0;
    assert(rb.peekOldest(v) && v == 1);
    rb.popOldest();
    assert(rb.peekOldest(v) && v == 2);
    assert(rb.size() == 2);
  }
  {  // test_ring_overwrite
    RingBuffer<int, 32> rb;
    for (int i = 1; i <= 32; ++i) assert(rb.push(i));
    assert(!rb.push(33));
    int v = 0;
    assert(rb.size() == 32);
    assert(rb.peekOldest(v) && v == 2);
    assert(rb.dropped() == 1);
  }
  {  // test_ring_empty_peek
    RingBuffer<int, 32> rb;
    int v = 99;
    assert(!rb.peekOldest(v));
    assert(rb.size() == 0);
  }
  {  // test_ring_wraps_many
    RingBuffer<int, 32> rb;
    for (int i = 1; i <= 1000; ++i) {
      rb.push(i);
      if (i % 2 == 0) rb.popOldest();
    }
    assert(rb.size() == 31);
    assert(rb.dropped() == 469);
    int prev = 0, v = 0;
    while (rb.peekOldest(v)) {
      assert(v > prev);
      prev = v;
      rb.popOldest();
    }
  }
  std::puts("ok");
  return 0;
}
