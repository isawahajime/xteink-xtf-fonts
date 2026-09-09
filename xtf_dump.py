#!/usr/bin/env python3
"""xtf_dump.py — .xtf のヘッダ表示とグリフの ASCII アート描画

    python xtf_dump.py system_small.xtf            # ヘッダと interval 表の要約
    python xtf_dump.py system_small.xtf あ 漢 A     # 指定文字のビットマップを描画
"""
import struct, sys

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    d = open(sys.argv[1], 'rb').read()
    if d[:4] != b'XTF0':
        sys.exit('XTF0 ではありません')
    n_iv = struct.unpack_from('<I', d, 20)[0]
    n = struct.unpack_from('<I', d, 24)[0]
    iv_off = struct.unpack_from('<I', d, 28)[0]
    bmp_off = struct.unpack_from('<I', d, 36)[0]
    slot = struct.unpack_from('<I', d, 44)[0] // n
    cw, ch = d[10], d[11]
    ivs = [struct.unpack_from('<III', d, iv_off + i * 16) for i in range(n_iv)]
    print(f'{sys.argv[1]}: {len(d)} B  cell {cw}x{ch}  advance_y {d[12]}  glyphs {n}  intervals {n_iv}  slot {slot} B')
    print(f'  interval 表 @{iv_off}, ビットマップ @{bmp_off}, ID {d[48:56].hex()}')
    if len(sys.argv) == 2:
        for f, c, s in ivs[:8]:
            print(f'  U+{f:04X}.. x{c:5d} -> glyph #{s}')
        print('  ...')
        return
    stride = (cw + 7) // 8
    for ch_ in ' '.join(sys.argv[2:]).replace(' ', ''):
        cp = ord(ch_)
        g = next((s + cp - f for f, c, s in ivs if f <= cp < f + c), None)
        if g is None:
            print(f'\nU+{cp:04X} {ch_}: この xtf に無い'); continue
        p = bmp_off + g * slot
        w, h, xs, ys = d[p], d[p + 1], struct.unpack_from('<b', d, p + 2)[0], d[p + 3]
        print(f'\nU+{cp:04X} {ch_}  glyph #{g}  w={w} h={h} xshift={xs} yshift={ys}')
        for r in range(ch):
            row = int.from_bytes(d[p + 4 + r * stride:p + 4 + (r + 1) * stride], 'big') >> (stride * 8 - cw)
            print('   ' + format(row, f'0{cw}b').replace('0', '·').replace('1', '█'))

if __name__ == '__main__':
    main()
