# Xteink `.xtf` / `.xtfp` / `.xtfont` フォーマットメモ

Xteink X4 Pro 純正ファーム 7.5.4 に入っていた MiSans Demibold パッケージ
（`XTData/system_fonts/misans-demibold/`）を解析した結果。公式資料はなく、すべて実機の
ファイルから読み取ったもの。値はリトルエンディアン。

## パッケージ構成（`XTData/system_fonts/<font_id>/`）

| ファイル | 役割 |
|---|---|
| `manifest.json` | メタデータ。各アセットの `path` / `size` / `sha256`（ファイルそのものの SHA-256） |
| `system_small.xtf` | 20×20 セルのビットマップフォント（UI 小・本文小） |
| `system_medium.xtf` | 24×24 セルのビットマップフォント（本文） |
| `system_*.hot.xtfp` | 使用頻度上位グリフの常駐キャッシュ（配布パッケージに含まれる） |
| `system_*.base.xtfp` | 起動時に必要な最小グリフ集合（**ファームがインストール時に生成**） |
| `preview.xic` | 設定画面用サムネイル（320×96, 1bpp） |
| `../selection.config` | 現在の選択。`font_id` と small/body の asset_id（= xtf の SHA-256） |

配布形式 `.xtfont`（`XTCache/system_font_downloads/`）は無圧縮 ZIP。
エントリ順は `manifest.json`, `assets/system_small.xtf`, `assets/system_small.hot.xtfp`,
`assets/system_medium.xtf`, `assets/system_medium.hot.xtfp`, `assets/preview.xic`。
署名・暗号化の類はない。

読書用フォントは同じ `.xtf` を SD ルートの `Font/` に置き、本の中の「Font」メニューで選ぶ
（公式 FAQ に記載の正規ルート。対応形式 XTF / BIN）。

## `.xtf`（magic `XTF0`）

```
offset  size  内容                         MiSans small の値
0       4     magic "XTF0"
4       u16   フォーマット版                 2
6       u16   ?                              320
8       u16   ?                              3
10      u8    セル幅 cw                      20   (medium: 24)
11      u8    セル高 ch                      20   (medium: 24)
12      u8    advance_y                      18   (medium: 22)
13      u8    ?                              20   (medium: 24)
14      u8,u8 ?                              11, 2  (medium: 13, 2)
16      u16   ?                              21   (medium: 26)
18      i16   ? (descender らしい)           -6   (medium: -7)
20      u32   interval 数                    416
24      u32   グリフ数                       43101
28      u32   interval 表オフセット           64
36      u32   ビットマップ領域オフセット      7168
44      u32   ビットマップ領域サイズ          2758464 (= グリフ数 × スロット長)
48      8B    フォント ID（正体不明。ファイルごとに異なる。流用で動作する）
56      u32   ASCII 送り幅表オフセット        6720
60      u32   ASCII 送り幅表の要素数          95
```

### interval 表（offset 64, 16B × interval 数）

```
u32 先頭コードポイント
u32 個数
u32 開始グリフ番号
u16 0
u16 個数（重複）
```

コードポイント昇順。MiSans では開始グリフ番号が累積和になっている（416 個、合計 43,101）。

### ASCII 送り幅表（offset 6720, 448B）

先頭 95 グリフ（U+0020〜U+007E）の送り幅 1B ずつ。残りは 0。

### グリフスロット（offset 7168, 固定長 × グリフ数）

スロット長 = 4 + ch × ceil(cw / 8)。small は 4 + 20×3 = **64B**、medium は 4 + 24×3 = **76B**。

```
u8  w        送り幅（インクは必ず w 列未満に収まる）
u8  h        行高（small は全グリフ 18、medium は 22。advance_y と同じ値）
i8  xshift   負の左ベアリング分だけ右へ寄せた量（'j' で -1）。通常 0
u8  yshift   ディセンダがセルを越える分だけ上へ寄せた量（'g','p','q','y' で 5）。通常 0
ch 行 × ceil(cw/8) B   1bpp ビットマップ。各行 MSB が左端、1 = 黒
```

ベースライン位置（実測）: small は大文字 'A' がおよそ 0〜15 行目、漢字が 1〜19 行目。
medium は 'A' が 0〜18、漢字が 1〜22 行目。生成時は small = 17 行目、medium = 21 行目を
ベースラインにすると MiSans とほぼ同じ位置になる。

圧縮なし。グリフはこの固定長スロットに直接格納されているので、
`slot_offset = 7168 + glyph_index × slot_len` でランダムアクセスできる。

## `.xtfp`（magic `XFP3`）

hot / base とも同じ構造。先頭にヘッダと索引、その後ろに `.xtf` と**同一バイト列のスロット**が
連続して並ぶ（hot small: 7,281 スロット × 64B = 524,232B。manifest の `cumulative_resident_bytes`
と一致）。

判明しているヘッダフィールド:

```
0x00  "XFP3"
0x04  u16 3, u16 3
0x14  u32 親 xtf のファイルサイズ
0x18  8B  親 xtf のフォント ID（xtf +48 の 8B を 4B 単位で入れ替えた並び）
0x20  u32 ?（hot / base で同じ値。crc32 / xxh32 / adler32 のいずれでもない）
0x34  32B 親 xtf の SHA-256
0x54  32B 集合ハッシュ（hot は manifest の hot_package_set_sha256 と一致）
```

親 xtf を差し替えたら 0x34 の SHA-256 を更新する必要がある。

## `.xic`（画像。スクリーンショット / preview / 表紙キャッシュ）

```
0   "XIC\0"
4   u16 幅
6   u16 高さ
8   u8 ×3  ?（1,1,1）
16  u32 データ長
24  1bpp ビットマップ（行 = ceil(幅/8) B）
```

480×800 のスクリーンショットは 24 + 48,000 = 48,024B。ビットは 1 = 白（PIL の '1' モードで
読むと白黒反転して見える）。

## `manifest.json` で参照される集合ハッシュ

`hot.coverage.*_set_sha256` / `ranked_source_sha256` / `hot_package_set_sha256` は
「どのグリフを常駐させるか」の集合に対するハッシュ。**グリフ集合を変えなければ再計算不要**。
このツールはそれを利用して、参照パッケージの集合をそのまま使いビットマップだけを差し替えている。

## 未解明

- xtf +48 の 8B ID と xtfp +0x20 の u32 の算出法（流用で動作するので実害なし）
- xtf ヘッダ +6, +8, +13, +14, +16 の意味
- グリフ集合を増やす方法（interval 表の追加は可能なはずだが未検証）
