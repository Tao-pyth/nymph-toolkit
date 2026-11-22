# v1.1.0のインストールと最初の実行

対象は、公開済みのNTK Coreを初めて試す人。ここでは **v1.1.0のwheelを通常インストール**し、同じ版のsdistに含まれるダミー例を実行する。NTKはCore・Contractsと最小Memoryのライブラリであり、この版に常駐アプリ・GUI・会話相手としてのNymphは含まれない。例は処理と後処理を終えると終了する。

## 用意するもの

- CPython 3.12以上。v1.1.0で検証済みの範囲はWindows／Linux × CPython 3.12〜3.15。下限の指定は、将来の全Python版を検証済みという意味ではない。
- `venv`と`pip`を使えるPython、インターネット接続、書き込める作業フォルダ。Linuxではこの手順に`curl`・`sha256sum`・`tar`も使う。
- Pythonが未導入なら[Python公式のダウンロード](https://www.python.org/downloads/)または利用OSの配布元から用意する。既存の古いPythonを上書きする必要はない。

実行時の外部Python依存はない。MemoryにはCPythonのsqlite3モジュールが必要。Git、開発用ビルドツール、GitHub認証はこの導入には不要。Windowsで`python --version`が3.8などを示す場合は、用意した3.12以上の実行ファイルを指定するか、インストール済みなら`py -3.12`を使う。以下の最初の`python`を、そのコマンドへ置き換える。

作業場所は任意。以下では現在のフォルダに新しい`ntk-v1.1.0`を作る。同名フォルダが既にある場合は別名を使い、既存環境へ混在させない。各段階で失敗したら[トラブルシューティング](troubleshooting.md)へ進む。

## Windows / PowerShell

### 1. Pythonと仮想環境

```powershell
python --version
New-Item -ItemType Directory -Path ntk-v1.1.0
Set-Location -LiteralPath ntk-v1.1.0
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
```

以後はこのフォルダで実行する。仮想環境のactivateやPowerShell実行ポリシーの変更は不要。

### 2. 公開ファイルを取得して照合

[v1.1.0 Release](https://github.com/Tao-pyth/nymph-toolkit/releases/tag/v1.1.0)の添付から、wheel、sdist、`SHA256SUMS`を取得する。wheelに実行例は入っていないため、同版のsdistも用意する。GitHubが自動生成する「Source code」アーカイブと、ここで使う添付sdistは別のファイルである。

```powershell
$ErrorActionPreference = 'Stop'
$releaseUrl = 'https://github.com/Tao-pyth/nymph-toolkit/releases/download/v1.1.0'
$packages = @('nymph_toolkit-1.1.0-py3-none-any.whl', 'nymph_toolkit-1.1.0.tar.gz')
foreach ($file in ($packages + @('SHA256SUMS'))) {
    Invoke-WebRequest -UseBasicParsing -Uri "$releaseUrl/$file" -OutFile $file
}
foreach ($file in $packages) {
    $pattern = '^[0-9a-f]{64}  ' + [regex]::Escape($file) + '$'
    $entries = @(Get-Content SHA256SUMS | Where-Object { $_ -match $pattern })
    if ($entries.Count -ne 1) { throw "Checksum entry missing or duplicated: $file" }
    $expected = $entries[0].Split(' ')[0]
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    if ($actual -ine $expected) { throw "Checksum mismatch: $file" }
    Write-Output "SHA256 OK: $file"
}
```

2件とも`SHA256 OK`になったら進む。チェックサムは取得ファイルと公開された一覧の一致を確認するもので、別途の署名検証ではない。

### 3. wheelを導入し、版とimport元を確認

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps .\nymph_toolkit-1.1.0-py3-none-any.whl
if ($LASTEXITCODE -ne 0) { throw 'wheel installation failed' }
.\.venv\Scripts\python.exe -I -c "import sys, importlib.metadata as m, nymph_toolkit.core as c; print(sys.executable); print(m.version('nymph-toolkit')); print(c.__file__)"
.\.venv\Scripts\python.exe -m tarfile -e .\nymph_toolkit-1.1.0.tar.gz .
if ($LASTEXITCODE -ne 0) { throw 'sdist extraction failed' }
```

表示される版は`1.1.0`、import元はこの環境の`.venv\Lib\site-packages\nymph_toolkit\core\__init__.py`となる。展開先は`nymph_toolkit-1.1.0`。sdistは例の取得に使い、その中の`src`をPythonの検索パスに加えない。

### 4. 最初の例を実行

```powershell
.\.venv\Scripts\python.exe -I -W error .\nymph_toolkit-1.1.0\examples\runtime_demo.py
if ($LASTEXITCODE -ne 0) { throw 'runtime demo failed' }
```

## Linux / Bash

`python3 --version`が3.12以上であることを確認する。複数版がある場合は、最初の2つの`python3`を`python3.12`などに置き換える。`venv`や`ensurepip`がない場合は、同じPython版のvenv用パッケージをOSの手順に従って導入する。

```bash
set -e
python3 --version
mkdir ntk-v1.1.0
cd ntk-v1.1.0
python3 -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip --version

release_url='https://github.com/Tao-pyth/nymph-toolkit/releases/download/v1.1.0'
for file in nymph_toolkit-1.1.0-py3-none-any.whl nymph_toolkit-1.1.0.tar.gz SHA256SUMS; do
    curl --fail --location "$release_url/$file" --output "$file"
done
sha256sum --check --ignore-missing SHA256SUMS

.venv/bin/python -m pip install --no-index --no-deps ./nymph_toolkit-1.1.0-py3-none-any.whl
.venv/bin/python -I -c "import sys, importlib.metadata as m, nymph_toolkit.core as c; print(sys.executable); print(m.version('nymph-toolkit')); print(c.__file__)"
tar -xzf nymph_toolkit-1.1.0.tar.gz
.venv/bin/python -I -W error nymph_toolkit-1.1.0/examples/runtime_demo.py
```

チェックサムでwheelとsdistの2件が`OK`になり、版が`1.1.0`、import元がこの`.venv/lib/python3.x/site-packages`配下になることを確認する。`--ignore-missing`は取得していない引継ぎ書を照合対象から外すために使う。2件のどちらかが表示されなければ取得を確認する。

## 正常終了の確認と次の手順

両OSとも、最初の例は次を出力して終了コード0で戻る。

```json
{"state": "stopped", "result": "dummy-result", "events": ["start", "run", "stop"], "remaining_tasks": 0}
```

これはダミーの起動・実行・停止を確認した結果。プロセスが終了しているため、バックグラウンドでNymphが活動し続けている状態ではない。`-I`は呼出時の`PYTHONPATH`やユーザーサイト等の影響を避け、`-W error`は警告も失敗として見つける検証用指定である。

続いて[8つの実行例ガイド](tutorials.md)で登録、接続、活動変更、別プロセス実行を確認する。コードを修正する場合は[開発手順](development.md)で別の開発環境を用意する。`pip install -e .`は作業ツリーを読む開発用導入であり、この手順の通常導入とは区別する。

R32・[#110](https://github.com/Tao-pyth/nymph-toolkit/issues/110)でv1.1.0向けに更新した。本版の受入は[B01記録](validation/v1.1.md)、公開後取得の結果は#110で追跡する。過去の[文書整備](validation/docs-onboarding.md)・[v1.0契約受入](validation/v1.0.md)は当時の記録として保持し、公開済みタグ・添付は更新しない。
