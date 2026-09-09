# xteink-xtf-fonts

Xteink X4 Pro の**純正ファームウェア**で使える日本語フォント（`.xtf`）を、手持ちの TTF/OTF から作るツールです。
カスタムファームウェア（CrossPoint など）は不要です。

Xteink X4 Pro には日本語の書体が入っておらず、純正のフォントダウンロードにも日本語フォントはありません。
入っている MiSans（中国語向け）でも日本語は表示できますが、字形が中国語のものになります。
このツールで BIZ UD明朝 / BIZ UDゴシックなどを `.xtf` に変換して `Font/` フォルダに置くと、
本の中の「Font」メニューから選べるようになります。

**動作確認**: Xteink X4 Pro / 純正ファーム 7.5.4（英語版 Factory Firmware）/ BIZ UDMincho, BIZ UDGothic

> [English] Build `.xtf` bitmap fonts for the Xteink X4 Pro **stock firmware** from any TTF/OTF.
> The `.xtf` format was reverse-engineered from the bundled MiSans package; see `FORMAT.md`.
> Put the generated `.xtf` files into the `Font/` folder of the SD card (via USB Mode) and pick them
> from the reader's Font menu.

## 仕組み

`.xtf` の公式な変換ツールは公開されていません。そこで、端末に入っている既存フォントパッケージ
（MiSans Demibold）を「参照」として読み込み、**グリフ集合・interval 表・スロット配置をそのまま流用して、
ビットマップだけを FreeType でラスタライズしたものに差し替える**という方法をとっています。
集合を変えないので、パッケージ内の各種ハッシュを再計算する必要がありません。

変換元フォントに無いグリフ（BIZ UD の場合 32,129 字。主に簡体字と記号）は、`--fallback-ttf` で指定した
フォントから順に補います。どのフォントにも無い字は参照側（MiSans）のビットマップがそのまま残るので
豆腐にはなりません（`--no-ref-fallback` を付けると空白にします）。

フォーマットの詳細は [FORMAT.md](FORMAT.md) を参照してください。

## 使い方

### 1. 参照パッケージを SD カードから取り出す

端末のホーム画面右上メニューから **USB Mode** に入り、Mac/PC に SD カードをマウントします。

```
XTData/system_fonts/misans-demibold/     ← このフォルダごとコピー
```

（`XTCache/system_font_downloads/misans-demibold-r1.xtfont` でも可。無圧縮 ZIP です）

MiSans が入っていない場合は、端末の 設定 → システムフォント → フォント取得 から
先に MiSans をダウンロードしてください。

### 2. 変換

```sh
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

./venv/bin/python xtf_build.py \
  --ttf BIZUDMincho-Regular.ttf \
  --fallback-ttf "NotoSansJP[wght].ttf" \
  --fallback-ttf "NotoSansSC[wght].ttf" \
  --ref /path/to/misans-demibold \
  --out out/
```

`out/BIZUDMincho-Regular-20.xtf` と `out/BIZUDMincho-Regular-24.xtf` ができます（1 サイズ 1 分ほど）。
標準エラー出力に、どのフォントから何グリフ取ったかが出ます。

BIZ UD 系フォント・Noto Sans JP / SC は [Google Fonts](https://github.com/google/fonts/tree/main/ofl) から取得できます（いずれも SIL OFL 1.1）。
`--fallback-ttf` を省略すると、BIZ UD に無い字は参照パッケージ（MiSans）のビットマップになります。

### 3. 端末に入れる

再び USB Mode に入り、SD カードのルートに `Font` フォルダを作って `.xtf` を置きます。
USB Mode を抜けて本を開き、読書画面の **Font** から選択してください。

```
SD カード/
└── Font/
    ├── BIZUDMincho-Regular-20.xtf
    └── BIZUDMincho-Regular-24.xtf
```

### グリフの確認

```sh
./venv/bin/python xtf_dump.py out/BIZUDMincho-Regular-20.xtf あ 漢 A
```

```
U+3042 あ  glyph #3004  w=20 h=18 xshift=0 yshift=0
   ·······██···········
   ········██··········
   ····█···█··███······
   ····████████········
   ········█···········
   ...
```

## システムフォント（メニュー・本棚）として入れる場合

`--package` を付けると `out/package/` に `XTData/system_fonts/<font_id>/` 用の一式
（xtf, hot/base .xtfp, manifest.json, selection.config）も出力します。
`XTData/system_fonts/` 配下に置くと 設定 → システムフォント の一覧に現れ、そこから選択できます。

ただし **この方法で切り替えると本文表示に不具合が出ることを確認しています**
（漢字の一部が表示されない）。本文用途には `Font/` に置く読書用フォントを使ってください。
`selection.config` を直接書き換える方法は無視されます。

## 制限・注意

- 参照パッケージのグリフ集合（43,101 字）の範囲でしか文字を持てません。JIS 第1・第2水準はすべて含まれています
- 小サイズ（20px）で濁点付きの一部の文字（ぱ・ぼ・ぽ・ゾ・ダ・ヅ・デ・プ・ヴ）は濁点が 1 行欠けます
- ヘッダ内の 8 バイト ID など、正体不明のフィールドは参照側の値をそのまま使っています（実機で動作しています）
- 自己責任でお使いください。フォントが読めない場合、純正ファームは組み込みフォントにフォールバックします
- MiSans / BIZ UD などフォント自体のライセンスは各フォントの規約に従ってください。このリポジトリにはフォントファイルを含みません

## 生成した .xtf のライセンスについて

- BIZ UDGothic / BIZ UDMincho、Noto Sans JP / SC はいずれも **SIL Open Font License 1.1** です。ビットマップへの変換や
  サブセット化は OFL が認める「改変版」にあたり、自分の端末で使う分には制約はありません
- 改変版を**配布**する場合は、OFL の本文と元フォントの著作権表示を同梱し、フォント単体で販売しないでください。
  BIZ UD には Reserved Font Name の宣言がなく、Noto Sans JP / SC の Reserved Font Name は `Source` だけなので、
  `BIZUDMincho-20.xtf` のような名前はそのまま使えます
- `--fallback-ttf` を指定せずに作った .xtf には、参照パッケージ（MiSans, Xiaomi）のビットマップが混ざります。
  配布するなら Noto Sans などの OFL フォントをフォールバックに指定するか、`--no-ref-fallback` を付けてください

## License

MIT
