#!/usr/bin/env python3
"""xtf_build.py — Xteink 純正ファーム用フォント (.xtf) を TTF/OTF から生成する

Xteink X4 Pro（純正ファーム 7.5.x）は独自のビットマップフォント形式 `.xtf` (magic "XTF0") を
使う。この形式は公式ツールが公開されていないため、端末に入っている既存フォント
（例: MiSans Demibold）を「参照パッケージ」として読み、そのグリフ集合・interval 表・
スロット配置をそのまま流用してビットマップだけを差し替える、という方法で生成する。

    python xtf_build.py --ttf BIZUDMincho-Regular.ttf --ref /path/to/misans-demibold --out out/

参照パッケージは SD カードの `XTData/system_fonts/<font_id>/`（system_small.xtf /
system_medium.xtf などが入ったフォルダ）か、`XTCache/system_font_downloads/*.xtfont`
（無圧縮 ZIP）を指定する。

出力:
  out/<name>-20.xtf, out/<name>-24.xtf   … SD の `Font/` に置いて本の中で選ぶ読書用フォント
  out/package/                            … システムフォント用パッケージ一式（--package 指定時）

フォーマットの詳細は FORMAT.md を参照。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import struct
import sys
import zipfile

try:
    import freetype
except ImportError:
    sys.exit("freetype-py が必要です: pip install freetype-py")

# ---------------------------------------------------------------- 参照パッケージ

REF_FILES = ('system_small.xtf', 'system_medium.xtf',
             'system_small.hot.xtfp', 'system_medium.hot.xtfp',
             'system_small.base.xtfp', 'system_medium.base.xtfp',
             'manifest.json', 'preview.xic')


def load_reference(path):
    """フォルダ or .xtfont(ZIP) から参照ファイルを dict[name] = bytes で返す。"""
    files = {}
    if os.path.isdir(path):
        for n in REF_FILES:
            p = os.path.join(path, n)
            if os.path.exists(p):
                files[n] = open(p, 'rb').read()
    else:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                n = os.path.basename(info.filename)
                if n in REF_FILES:
                    files[n] = z.read(info)
    for must in ('system_small.xtf', 'system_medium.xtf'):
        if must not in files:
            sys.exit(f'参照パッケージに {must} がありません: {path}')
    return files


def parse_xtf(d):
    if d[:4] != b'XTF0':
        sys.exit('XTF0 マジックがありません')
    n_iv = struct.unpack_from('<I', d, 20)[0]
    n = struct.unpack_from('<I', d, 24)[0]
    iv_off = struct.unpack_from('<I', d, 28)[0]
    bmp_off = struct.unpack_from('<I', d, 36)[0]
    bmp_size = struct.unpack_from('<I', d, 44)[0]
    cw, ch = d[10], d[11]
    ivs = [struct.unpack_from('<III', d, iv_off + i * 16) for i in range(n_iv)]
    return dict(n=n, bmp_off=bmp_off, slot=bmp_size // n, cw=cw, ch=ch, ivs=ivs,
                ascii_off=struct.unpack_from('<I', d, 56)[0])


# ---------------------------------------------------------------- ラスタライズ

class Rasterizer:
    """1 本の TTF/OTF。fallbacks に渡した Rasterizer を順に試す。"""

    def __init__(self, ttf, fallbacks=()):
        self.face = freetype.Face(ttf)
        self.name = os.path.basename(ttf)
        self.fallbacks = list(fallbacks)

    def set_px(self, px):
        self.face.set_pixel_sizes(0, px)
        for fb in self.fallbacks:
            fb.set_px(px)

    def slot(self, cp, cw, ch, slot_len, baseline, h_byte):
        """1 コードポイントを cw×ch の 1bpp セルに置き、(スロット bytes, 使ったフォント名) を返す。
        どのフォントにもグリフが無ければ (None, None)。"""
        s = self._render(cp, cw, ch, slot_len, baseline, h_byte)
        if s is not None:
            return s, self.name
        for fb in self.fallbacks:
            s, who = fb.slot(cp, cw, ch, slot_len, baseline, h_byte)
            if s is not None:
                return s, who
        return None, None

    def _render(self, cp, cw, ch, slot_len, baseline, h_byte):
        gi = self.face.get_char_index(cp)
        if gi == 0:
            return None
        self.face.load_glyph(gi, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
        g = self.face.glyph
        b = g.bitmap
        stride = (cw + 7) // 8
        adv = int(round(g.advance.x / 64))
        w = max(1, min(cw, adv))
        left = g.bitmap_left
        top_row = baseline - g.bitmap_top
        bottom_row = top_row + b.rows - 1
        xshift = 0
        if left < 0:                       # 負の左ベアリング（'j' など）
            xshift = left
            left = 0
        yshift = 0
        if bottom_row > ch - 1:            # ディセンダがセルを越える（'g','p' など）
            yshift = bottom_row - (ch - 1)
            top_row -= yshift
        rows = bytearray(ch * stride)
        for y in range(b.rows):
            cy = top_row + y
            if cy < 0 or cy >= ch:
                continue
            for x in range(b.width):
                if (b.buffer[y * b.pitch + x // 8] >> (7 - x % 8)) & 1:
                    cx = left + x
                    if 0 <= cx < cw:
                        rows[cy * stride + cx // 8] |= 0x80 >> (cx % 8)
        s = bytes([w, h_byte, xshift & 0xff, yshift & 0xff]) + bytes(rows)
        assert len(s) == slot_len
        return s


# ---------------------------------------------------------------- 生成

def build_xtf(src, ras, px, baseline, log, keep_ref=True):
    """参照 xtf(bytes) と同じ集合で新しい xtf(bytes) を返す。mapping も返す。"""
    info = parse_xtf(src)
    cw, ch, slot, bmp_off = info['cw'], info['ch'], info['slot'], info['bmp_off']
    ras.set_px(px)
    out = bytearray(src)
    mapping = {}
    counts = {}
    for f, c, s in info['ivs']:
        for k in range(c):
            g, cp = s + k, f + k
            p = bmp_off + g * slot
            orig = bytes(src[p:p + slot])
            new, who = ras.slot(cp, cw, ch, slot, baseline, orig[1])
            if new is None:
                if keep_ref:
                    new, who = orig, '(参照パッケージのビットマップ)'
                else:
                    new, who = orig[:4] + bytes(slot - 4), '(空白)'
            counts[who] = counts.get(who, 0) + 1
            out[p:p + slot] = new
            mapping.setdefault(orig, new)
    # ASCII 高速参照表（先頭 95 グリフの送り幅）
    a = info['ascii_off']
    for g in range(95):
        out[a + g] = out[bmp_off + g * slot]
    log(f'  {px}px: ' + ' / '.join(f'{k} {v}' for k, v in counts.items()))
    return bytes(out), mapping, slot


def patch_xtfp(xd, mapping, slot, old_sha, new_sha):
    """hot/base .xtfp 内の 64B/76B スロットを差し替え、親 xtf の sha256 参照を更新。"""
    xd = bytearray(xd)
    first = None
    for orig in mapping:
        if orig[4:].strip(b'\0'):
            q = xd.find(orig)
            if q >= 0:
                first = q % slot
                break
    if first is None:
        return bytes(xd), 0
    replaced = 0
    pos = first
    while pos + slot <= len(xd):
        cur = bytes(xd[pos:pos + slot])
        if cur in mapping:
            xd[pos:pos + slot] = mapping[cur]
            replaced += 1
        pos += slot
    if bytes(xd[0x34:0x54]) == old_sha:
        xd[0x34:0x54] = new_sha
    return bytes(xd), replaced


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ttf', required=True, help='元にする TTF/OTF')
    ap.add_argument('--ref', required=True, help='参照パッケージ（system_fonts/<id>/ フォルダ か .xtfont）')
    ap.add_argument('--fallback-ttf', action='append', default=[], metavar='TTF',
                    help='--ttf に無い文字をこのフォントで補う。複数指定可（指定順に試す）。'
                         '例: --fallback-ttf NotoSansJP[wght].ttf --fallback-ttf NotoSansSC[wght].ttf')
    ap.add_argument('--no-ref-fallback', action='store_true',
                    help='どのフォントにも無い文字を、参照パッケージのビットマップではなく空白にする'
                         '（配布物を参照フォントに依存させたくない場合）')
    ap.add_argument('--out', default='out', help='出力先フォルダ')
    ap.add_argument('--name', default=None, help='読書用 .xtf のファイル名の元（既定: TTF のファイル名）')
    ap.add_argument('--baseline-small', type=int, default=17, help='20px セルのベースライン行（既定 17）')
    ap.add_argument('--baseline-medium', type=int, default=21, help='24px セルのベースライン行（既定 21）')
    ap.add_argument('--package', action='store_true', help='システムフォント用パッケージ一式も出力する')
    ap.add_argument('--font-id', default=None, help='--package 時の font_id（既定: name を小文字化）')
    ap.add_argument('--display', default=None, help='--package 時の表示名')
    ap.add_argument('--family', default=None)
    ap.add_argument('--style', default='Regular')
    args = ap.parse_args()

    log = lambda s: print(s, file=sys.stderr)
    name = args.name or os.path.splitext(os.path.basename(args.ttf))[0]
    ref = load_reference(args.ref)
    ras = Rasterizer(args.ttf, [Rasterizer(fb) for fb in args.fallback_ttf])
    os.makedirs(args.out, exist_ok=True)

    results = {}
    for role, px, base, suffix in (('system_small', 20, args.baseline_small, '20'),
                                   ('system_medium', 24, args.baseline_medium, '24')):
        src = ref[f'{role}.xtf']
        log(f'{role}:')
        new, mapping, slot = build_xtf(src, ras, px, base, log, keep_ref=not args.no_ref_fallback)
        results[role] = (src, new, mapping, slot)
        fn = os.path.join(args.out, f'{name}-{suffix}.xtf')
        open(fn, 'wb').write(new)
        log(f'  -> {fn}')

    if args.package:
        pk = os.path.join(args.out, 'package')
        os.makedirs(pk, exist_ok=True)
        for role, (src, new, mapping, slot) in results.items():
            open(os.path.join(pk, f'{role}.xtf'), 'wb').write(new)
            old_sha, new_sha = hashlib.sha256(src).digest(), hashlib.sha256(new).digest()
            for kind in ('hot', 'base'):
                k = f'{role}.{kind}.xtfp'
                if k in ref:
                    patched, n = patch_xtfp(ref[k], mapping, slot, old_sha, new_sha)
                    open(os.path.join(pk, k), 'wb').write(patched)
                    log(f'  {k}: {n} スロット差し替え')
        if 'preview.xic' in ref:
            open(os.path.join(pk, 'preview.xic'), 'wb').write(ref['preview.xic'])
        if 'manifest.json' in ref:
            m = json.loads(ref['manifest.json'])
            fid = args.font_id or name.lower().replace(' ', '-')
            m['font_id'] = fid
            m['display_name'] = args.display or name
            m['family'] = args.family or name
            m['style'] = args.style
            m['description'] = f'{name} converted by xtf_build.py'

            def walk(o):
                if isinstance(o, dict):
                    if 'path' in o and 'sha256' in o:
                        fp = os.path.join(pk, os.path.basename(o['path']))
                        if os.path.exists(fp):
                            data = open(fp, 'rb').read()
                            o['sha256'] = hashlib.sha256(data).hexdigest()
                            o['size'] = len(data)
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(m)
            for role in m.get('roles', {}).values():
                if 'hot' in role and 'font' in role:
                    role['hot']['source_xtf_sha256'] = role['font']['sha256']
            json.dump(m, open(os.path.join(pk, 'manifest.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
            sm = hashlib.sha256(open(os.path.join(pk, 'system_small.xtf'), 'rb').read()).hexdigest()
            md = hashlib.sha256(open(os.path.join(pk, 'system_medium.xtf'), 'rb').read()).hexdigest()
            open(os.path.join(pk, 'selection.config'), 'w').write(
                f'format_version=1\nmode=external\nfont_id={fid}\nsmall_asset_id={sm}\nbody_asset_id={md}\n')
            log(f'  package -> {pk} (font_id={fid})')
            log('  注意: システムフォントとして入れると本文で不具合が出ることがあります。'
                '読書用 (Font/ に .xtf を置く) を推奨します。')


if __name__ == '__main__':
    main()
