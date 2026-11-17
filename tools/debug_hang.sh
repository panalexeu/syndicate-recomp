#!/usr/bin/env bash
# Run syndicate under gdb. When the game hangs, press Ctrl+C in this terminal:
# all thread stacks are written to out/hang_stacks.txt and the game is closed.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
for seg in /dev/shm/xenia_memory_*; do [ -e "$seg" ] && ! fuser -s "$seg" 2>/dev/null && rm -f "$seg"; done
export __NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only
gdb -q -batch \
  -ex "set debuginfod enabled off" -ex "set pagination off" \
  -ex "handle SIGSEGV nostop noprint pass" -ex "handle SIGUSR1 nostop noprint pass" \
  -ex "run" \
  -ex "set logging file out/hang_stacks.txt" -ex "set logging overwrite on" -ex "set logging redirect on" -ex "set logging enabled on" \
  -ex "thread apply all bt 25" \
  -ex "set logging enabled off" -ex "kill" \
  --args ./out/build/linux-amd64-release/syndicate --game_data_root "$root/syndicate-extract"
echo "Stacks saved to out/hang_stacks.txt"
