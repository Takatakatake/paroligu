# Spomenka Esperanto TTS

エスペラント文を RHVoice の Spomenka 音声で WAV 化する Streamlit アプリです。生成した音声はブラウザ上で再生でき、WAV ファイルとして保存できます。

## ローカル実行

Ubuntu/Debian 系の環境では先に RHVoice を入れます。

```bash
sudo apt-get update
sudo apt-get install -y rhvoice rhvoice-esperanto
```

Python 環境を作って Streamlit を起動します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

リポジトリ直下の `requirements.txt` と `packages.txt` をそのまま GitHub に置いてください。

- `requirements.txt`: Streamlit をインストールします。
- `packages.txt`: RHVoice の実行に必要な `main` 側の共有ライブラリだけを apt でインストールします。

RHVoice 本体と Spomenka 音声は Debian 公式の `non-free` `.deb` をアプリ起動時にユーザー領域へダウンロードし、SHA256 を検証してから展開します。Streamlit Community Cloud では `non-free` リポジトリ追加に失敗するため、この方式で回避しています。

Streamlit Community Cloud では、New app でこの GitHub リポジトリを選び、メインファイルに `app.py` を指定します。

## 入力表記

通常の Unicode 表記に加えて、`cx`, `gx`, `hx`, `jx`, `sx`, `ux` を `ĉ`, `ĝ`, `ĥ`, `ĵ`, `ŝ`, `ŭ` に変換する x 記法にも対応しています。

## テスト

```bash
python -m unittest discover
```
