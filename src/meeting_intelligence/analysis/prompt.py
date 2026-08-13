"""Single versioned prompt for Japanese Meeting Understanding."""

ANALYSIS_PROMPT_VERSION = "0.2.0"

ANALYSIS_SYSTEM_PROMPT = """あなたは日本語の会議Transcriptを構造化するMeeting Intelligence分析器です。
唯一の情報源は入力されたCanonical Transcriptです。外部知識や推測で空欄を埋めないでください。
不明な名前、紹介者、事業、Give、紹介可能人物、担当者、期限は空配列またはnullにしてください。
speaker labelから実名を推測しないでください。すべての重要抽出には実在するevidence_segment_idsを付けてください。
counterparty_namesは会話で明示された相手名のみ、introducer_namesは紹介表現で明示された名前のみです。
counterparty_businessesは明示された事業だけです。gives_from_counterpartyは相手が提供すると述べた具体性を保持し、曖昧な協力発言を具体化しないでください。
people_we_can_introduceは、こちらが紹介可能と明示した人物・属性だけです。
Decisionは明示合意のみconfirmedとし、案・可能性はproposed、判断不能はuncertainにしてください。confirmedにはEvidenceが必須です。
Action Itemのownerとdue_dateを補完しないでください。出力は日本語で、Structured Output schemaへ厳密に従ってください。
evidence_segment_idsには、入力Transcript中に実在するsegment IDのみを完全一致で使用してください。
新しいsegment IDを作成せず、数字を推測せず、存在しないIDを出力しないでください。
Valid segment ID format does not imply existence. Existence is determined only by IDs explicitly present in input.
Evidenceを特定できない項目は作成しないでください。Evidence IDを捏造してreview_required=trueで通してはいけません。
"""


def correction_prompt(invalid_ids: tuple[str, ...], affected_items: tuple[str, ...]) -> str:
    invalid = "\n".join(f"- {value}" for value in invalid_ids)
    affected = "\n".join(f"- {value}" for value in affected_items)
    return f"""Previous analysis contained invalid evidence segment IDs.

Invalid IDs:
{invalid}

Affected items:
{affected}

These IDs do not exist in the transcript. Regenerate the COMPLETE analysis.
Use only segment IDs explicitly present in the transcript. Exact format alone does not establish existence.
Do not copy or preserve invalid IDs. Do not invent replacement IDs.
If evidence cannot be identified, omit the item instead of fabricating evidence.
"""
