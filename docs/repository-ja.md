# リポジトリへの反映

対象：`https://github.com/akihotsuji/fx-lab`

実装の保存時に、GitHub接続アプリから `403 Resource not accessible by integration` が返りました。そのためリモートへのコミット、ブランチ、PRは作成できていません。ユーザー自身のリポジトリ権限と、接続アプリの書き込み権限は別です。

GitHubのInstalled GitHub AppsとChatGPT側のGitHub接続設定で、`fx-lab` がアクセス対象に含まれているか、書き込み対応の接続かを確認してください。読み取り用の接続ではソースの保存はできません。認証トークンをチャットやソースへ貼り付けないでください。

手動で反映する場合は、ZIPを展開した `fx-lab` フォルダーを用います。GitHubへの認証が済んだ自分の端末で、以下を実行すると空のリポジトリのmainを初期化できます。実行前にリモートがまだ空か確認してください。

```sh
cd fx-lab
git init -b main
git add .
git commit -m "Add WEMOF JForex tick observer and parity tests"
git remote add origin https://github.com/akihotsuji/fx-lab.git
git push -u origin main
```

ZIPには認証情報、運用ログ、API jarを含めていません。`.github`、`.gitignore` も含めて反映してください。以後の変更は作業ブランチとPRで管理できます。
