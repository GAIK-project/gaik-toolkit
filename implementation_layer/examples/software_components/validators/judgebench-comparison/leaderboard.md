# JudgeBench prompt comparison

- **Dataset**: [ScalerLab/JudgeBench](https://hf.co/datasets/ScalerLab/JudgeBench) (split `gpt`)
- **Rows**: 50
- **Judge**: `google/gemini-3-flash-preview`
- **Position-bias mitigation**: swap-and-average = `True`

## Aggregate scores

| Prompt | Accuracy | Position-bias flips | Ties | Mean cost (USD) | Mean latency (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `naive` | 64.0% | 26.0% | 13 | 0.0017 | 13.85 |
| `research` | 66.0% | 22.0% | 14 | 0.0023 | 16.45 |

## Score distribution (per response, summed across rows)

- `naive`: `2` × 9, `3` × 4, `4` × 14, `5` × 6, `6` × 15, `7` × 3, `8` × 9, `9` × 14, `10` × 26
- `research`: `1` × 3, `2` × 36, `3` × 7, `4` × 21, `5` × 33
