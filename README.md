# fx-lab — WEMOF USDJPY observer

5分足のボリンジャーバンド20期間・±3σへの接触を、JForexで受信するティックから観測します。接触後の3pipsの戻り、10pipsの逆行、15分の時間切れを記録する、**実注文を出さない観測用ストラテジー**です。

5分足で表示していても、接触や結果の判定は足の確定を待ちません。今回の版は「3σに初めて触れた価格で仮想エントリーする」基準モデルです。1分足の反転確認、水平線、ラウンドナンバー、ピボットによる阻却条件はまだ加えていません。

## JForexで使う

1. [jforex/WemofObserver.java](jforex/WemofObserver.java) を保存します。
2. JForexデスクトップのローカルストラテジーとして開き、コンパイルします。
3. USD/JPYの5分チャートを開き、デモ口座で開始します。手順・表示・ログの場所は [導入ガイド](docs/jforex-ja.md) を参照してください。

BUY / SELL、RESULT TP / SL / TIME / GAP、SKIP SPREADをチャートに表示します。セッションごとに `events.csv`、`ticks.csv`、`seed.csv`、`config.json` を保存します。

| 標準設定 | 値 |
| --- | --- |
| 基準 | USD/JPY・Bidの5分BB、20期間・±3σ |
| 入場 | 各5分区間の最初の接触のみ、次の足を待たない |
| 価格モデル | BID_ASK：買いAsk→Bid、売りBid→Ask |
| 戻り目標 / 逆行判定 | 3pips / 10pips |
| 観測期限 | 15分 |
| 更新空白 | 60秒超でGAP、損益不明 |
| 追加コスト | 0pips（実スプレッドは価格に含まれる） |
| 入場スプレッド上限 | 0：フィルター無効 |

価格だけの比較には `BID_REFERENCE` を選びます。約定、指値・成行注文、遅延、スリッページ、資金・ロットの管理は再現していません。TP/SLは仮想観測の分類であり、成績は利益を保証しません。

## 検証と再生

Python 3.10以上とJDK 17で、リポジトリのルートから実行します。

```sh
python tools/bundle_strategy.py --check
python -m unittest discover -s tests -v
python tools/check_adapter.py
```

最後のコマンドは公式JForex API 2.13.99を取得してSHA-256を検証し、単体のJavaファイルをコンパイルします。APIのjarはコミットしません。

保存したJForexセッションを独立したPython実装で再生できます。ストラテジーを正常停止してから比較してください。

```sh
python python/replay.py --ticks logs/session/ticks.csv --seed logs/session/seed.csv --config logs/session/config.json --events logs/session/replayed.csv
python tools/compare_events.py logs/session/events.csv logs/session/replayed.csv
```

`logs/session` は実際の保存先に置き換えます。時刻はUTCのUnixミリ秒です。CSV行の順序を維持し、同じ時刻のティックも順序を変更しません。

## 構成

- `src/main/java/`：APIに依存しない観測エンジン
- `src/adapter/`：JForexとの接続・描画・CSV保存
- `jforex/`：JForexに読み込む生成済み単体ファイル
- `python/`：独立した再生用参照実装
- `tests/`：境界・異常データ・価格モデル・Java/Python一致の検証
- `pine/`：移植前のPine v2.1（比較用）
- [判定仕様](docs/semantics-ja.md) / [検証結果](docs/verification-ja.md)

編集対象は `src/` です。変更後に `python tools/bundle_strategy.py` で単体ファイルを再生成します。認証情報、生ティック、大容量データ、運用ログはリポジトリに入れないでください。
