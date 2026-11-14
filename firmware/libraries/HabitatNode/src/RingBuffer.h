// Fixed-size FIFO ring buffer. Header-only, no heap, no Arduino includes.
// When full, push() overwrites the oldest item and counts it as dropped.
#pragma once
#include <stddef.h>
#include <stdint.h>

template <typename T, size_t N>
class RingBuffer {
 public:
  // Returns false when the oldest item was overwritten to make room.
  bool push(const T& item) {
    bool kept_all = true;
    if (count_ == N) {
      head_ = (head_ + 1) % N;
      --count_;
      ++dropped_;
      kept_all = false;
    }
    items_[(head_ + count_) % N] = item;
    ++count_;
    return kept_all;
  }
  // Returns false when empty.
  bool peekOldest(T& out) const {
    if (count_ == 0) return false;
    out = items_[head_];
    return true;
  }
  void popOldest() {
    if (count_ == 0) return;
    head_ = (head_ + 1) % N;
    --count_;
  }
  size_t size() const { return count_; }
  uint32_t dropped() const { return dropped_; }

 private:
  T items_[N];
  size_t head_ = 0;
  size_t count_ = 0;
  uint32_t dropped_ = 0;
};
