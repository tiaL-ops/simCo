
=================================================================
STEP 1 — JSON AGGREGATION (median of 3 raters)
=================================================================
Model         A_ER  A_IN  A_EX  B_ER  B_IN  B_EX
-----------------------------------------------------------------
Claude_E         2     2     2     2     2     1
Claude_N         2     1     2     2     2     2
Gemini_E         2     2     2     2     2     1
Gemini_N         1     1     1     1     1     0
GPT_E            2     2     1     1     2     0
GPT_N            0     1     1     0     0     0
Grok_E           2     2     2     2     2     2
Grok_N           2     1     1     2     1     1

=================================================================
STEP 2 — RATER 4 (column D) scores for items A and B
=================================================================
Model         A_ER  A_IN  A_EX  B_ER  B_IN  B_EX
-----------------------------------------------------------------
Claude_E         1     2     1     2     2     1
Claude_N         1     1     1     0     1     1
Gemini_E         0     0     0     2     2     1
Gemini_N         1     1     1     1     1     0
GPT_E            1     2     1     0     0     0
GPT_N            0     0     1     0     0     0
Grok_E           1     1     1     2     2     2
Grok_N           0     0     1     0     1     1

=================================================================
STEP 3 — COMPARISON: Aggregate (median) vs Rater 4
=================================================================
Model         Dim      Agg    R4   Diff  Match
-----------------------------------------------------------------
Claude_E      A_ER       2     1     -1  ↓
Claude_E      A_IN       2     2      0  ✓
Claude_E      A_EX       2     1     -1  ↓
Claude_E      B_ER       2     2      0  ✓
Claude_E      B_IN       2     2      0  ✓
Claude_E      B_EX       1     1      0  ✓
Claude_N      A_ER       2     1     -1  ↓
Claude_N      A_IN       1     1      0  ✓
Claude_N      A_EX       2     1     -1  ↓
Claude_N      B_ER       2     0     -2  ↓
Claude_N      B_IN       2     1     -1  ↓
Claude_N      B_EX       2     1     -1  ↓
Gemini_E      A_ER       2     0     -2  ↓
Gemini_E      A_IN       2     0     -2  ↓
Gemini_E      A_EX       2     0     -2  ↓
Gemini_E      B_ER       2     2      0  ✓
Gemini_E      B_IN       2     2      0  ✓
Gemini_E      B_EX       1     1      0  ✓
Gemini_N      A_ER       1     1      0  ✓
Gemini_N      A_IN       1     1      0  ✓
Gemini_N      A_EX       1     1      0  ✓
Gemini_N      B_ER       1     1      0  ✓
Gemini_N      B_IN       1     1      0  ✓
Gemini_N      B_EX       0     0      0  ✓
GPT_E         A_ER       2     1     -1  ↓
GPT_E         A_IN       2     2      0  ✓
GPT_E         A_EX       1     1      0  ✓
GPT_E         B_ER       1     0     -1  ↓
GPT_E         B_IN       2     0     -2  ↓
GPT_E         B_EX       0     0      0  ✓
GPT_N         A_ER       0     0      0  ✓
GPT_N         A_IN       1     0     -1  ↓
GPT_N         A_EX       1     1      0  ✓
GPT_N         B_ER       0     0      0  ✓
GPT_N         B_IN       0     0      0  ✓
GPT_N         B_EX       0     0      0  ✓
Grok_E        A_ER       2     1     -1  ↓
Grok_E        A_IN       2     1     -1  ↓
Grok_E        A_EX       2     1     -1  ↓
Grok_E        B_ER       2     2      0  ✓
Grok_E        B_IN       2     2      0  ✓
Grok_E        B_EX       2     2      0  ✓
Grok_N        A_ER       2     0     -2  ↓
Grok_N        A_IN       1     0     -1  ↓
Grok_N        A_EX       1     1      0  ✓
Grok_N        B_ER       2     0     -2  ↓
Grok_N        B_IN       1     1      0  ✓
Grok_N        B_EX       1     1      0  ✓
-----------------------------------------------------------------
Exact match rate: 28/48 = 58.3%

=================================================================
STEP 4 — MODEL-LEVEL SUMMARY (mean of medians vs mean of R4)
=================================================================
Model         Agg_Mean   R4_Mean    Diff
-----------------------------------------------------------------
Claude_E          1.83       1.5   -0.33
Claude_N          1.83      0.83    -1.0
Gemini_E          1.83      0.83    -1.0
Gemini_N          0.83      0.83     0.0
GPT_E             1.33      0.67   -0.67
GPT_N             0.33      0.17   -0.17
Grok_E            2.00       1.5    -0.5
Grok_N            1.33       0.5   -0.83
