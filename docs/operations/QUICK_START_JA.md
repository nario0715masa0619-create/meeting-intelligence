# Meeting Intelligence 簡易運用手順

## 1. MP4をInboxへ入れる

MTG録画のMP4ファイルを次のInboxへ配置します。サブフォルダを作っても構いません。

```text
D:\work\.meeting-intelligence
```

例：

```text
D:\work\.meeting-intelligence\260813\meeting.mp4
```

コピー中のファイルを処理しないよう、配置後2分以上経過してから実行してください。

## 2. PowerShellを開く

```powershell
cd C:\Users\nario\Documents\meeting-intelligence
.\.venv\Scripts\Activate.ps1
```

## 3. Meeting Intelligenceを実行する

```powershell
meeting-process inbox
```

自動的に次の処理が行われます。

```text
MP4検出
↓
音声抽出
↓
OpenAI文字起こし
↓
MTG内容分析
↓
Evidence検証
↓
詳細議事録生成
↓
Google Sheets記録
```

処理中はPowerShellを閉じないでください。

## 4. 完了を確認する

最後に次のような集計が表示されます。

```text
Inbox summary
Processed: 1
Resumed: 0
Skipped: 0
Failed: 0
```

`Failed: 0`であれば、検出したファイルは正常に処理または安全にスキップされています。

Google Sheetsには、MTG基本情報、ショート要約、主要論点、人物・ビジネス情報、Give情報、決定事項、Action Items、Open Items、詳細議事録への参照が記録されます。

## 5. 詳細議事録を確認する

詳細議事録はGoogle Sheetsへ全文を入れず、次のファイルとして保存されます。

```text
C:\Users\nario\Documents\meeting-intelligence\output\<meeting-id>\meeting-minutes.md
```

一次文字起こしは同じフォルダの`transcript.md`で確認できます。

## 6. 同じMP4をもう一度検出した場合

| 表示 | 動作 |
|---|---|
| `COMPLETE` | 処理済みのためスキップします |
| `TRANSCRIPT_COMPLETE` / `FAILED_RESUMABLE` | 文字起こしをせず分析工程から再開します |
| `NEW` | 最初から処理します |
| `BLOCKED` | 安全に処理できないため処理しません |

処理済みMP4をInboxへ残しても、通常は再課金・二重登録されません。元MP4は自動で移動・変更・削除されません。

## 7. 事前確認だけ行う

対象ファイルと状態だけを確認する場合は、次を実行します。

```powershell
meeting-process inbox --dry-run
```

dry-runでは、ffmpeg、OpenAI API、Google Sheets API、ファイル作成を実行しません。そのため、ローカル議事録まで完成した会議が`ANALYSIS_COMPLETE`と表示される場合があります。通常実行ではGoogle Sheetsをread-only確認し、登録済みなら`COMPLETE`としてスキップします。

## 8. エラーが出た場合

`Failed`が1件以上の場合はPowerShellの表示を保存してください。生成済みのTranscriptがある会議は、次回実行時に分析工程から再開されます。元MP4や生成済みファイルを手動で削除しないでください。

## 普段使うコマンド

```powershell
cd C:\Users\nario\Documents\meeting-intelligence
.\.venv\Scripts\Activate.ps1
meeting-process inbox
```
