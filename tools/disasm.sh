#!/usr/bin/env bash
# Disassemble guest code from an image dump (see SyndicateApp::OnPostLoadXexImage).
#
#   tools/disasm.sh out/image_82000000.bin 0x82BD01C0 32    # address, instruction count
set -euo pipefail
img="$1"; addr=$(( $2 )); count="${3:-16}"
off=$(( addr - 0x82000000 ))
for ((i = 0; i < count; i++)); do
  a=$(( addr + 4 * i ))
  bytes=$(od -An -tx1 -j $(( off + 4 * i )) -N4 "$img" | awk '{printf "0x%s 0x%s 0x%s 0x%s", $1, $2, $3, $4}')
  ins=$(echo "$bytes" | llvm-mc-20 --disassemble -triple=powerpc64-unknown-linux-gnu 2>/dev/null \
        | sed -n 's/^\t//p' | tr '\t' ' ' | head -1)
  printf '%08X  %s  %s\n' "$a" "$(echo "$bytes" | tr -d ' ' | sed 's/0x//g')" "${ins:-.long}"
done
