# Eval report: rag-faithfulness

- Cases: 20
- Pass rate: 90.0%
- Mean weighted score: 0.873

| Case | Verdict | Score | Rubrics |
| --- | --- | --- | --- |
| cite-01 | pass | 1.000 | faithfulness=1.00; groundedness=0.85 |
| cite-02 | pass | 1.000 | faithfulness=1.00; groundedness=0.92 |
| cite-03 | pass | 0.960 | faithfulness=1.00; groundedness=0.88 |
| cite-04 | pass | 1.000 | faithfulness=1.00; groundedness=0.80 |
| cite-05 | fail | 0.500 | faithfulness=1.00; groundedness=0.35 |
| math-01 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| math-02 | pass | 1.000 | faithfulness=1.00; groundedness=0.95 |
| math-03 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| math-04 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| math-05 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| class-01 | pass | 0.900 | faithfulness=1.00; groundedness=0.60 |
| class-02 | pass | 0.900 | faithfulness=1.00; groundedness=0.60 |
| class-03 | fail | 0.450 | faithfulness=0.50; groundedness=0.40 |
| class-04 | pass | 0.910 | faithfulness=1.00; groundedness=0.62 |
| class-05 | pass | 0.870 | faithfulness=1.00; groundedness=0.55 |
| ext-01 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| ext-02 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| ext-03 | pass | 0.880 | faithfulness=1.00; groundedness=0.56 |
| ext-04 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |
| ext-05 | pass | 1.000 | faithfulness=1.00; groundedness=1.00 |

## Regression against `reports/baseline.json`

- Baseline mean: 0.880
- Current mean:  0.873
- Drop: 0.007 (within tolerance 0.01)
- Verdict: no regression
