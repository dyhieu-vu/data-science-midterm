# Data quality and chart eligibility

This report describes the current 20-record snapshot only; it is not representative of all AI/Data Science programs.

- Expanded: 20 rows, 20 unique IDs, 33 columns.
- Clean: 20 rows; ID sets match expanded: True.
- Official evidence ledger: 69 rows; verified official rows: 69.
- Status counts: needs_manual_review=4, source_error=10, verified_identity=6.
- Country values: Vietnam.

## Six added attributes

| Field | Present | Missing |
|---|---:|---:|
| `duration_range_years` | 2 | 18 |
| `total_credits` | 3 | 17 |
| `credit_system` | 3 | 17 |
| `award_title` | 3 | 17 |
| `instruction_language_share` | 1 | 19 |
| `curriculum_course_list` | 5 | 15 |

## Chart eligibility

Counts distinguish programs, links (edges), and observations. `program_count` is not an edge count.

| Chart | Programs eligible | Programs excluded | Edges | Observations | Status | Limitation |
|---|---:|---:|---:|---:|---|---|
| Histogram: scalar duration | 16 | 4 | 0 | 16 | available | 16 verified scalar values; interval durations excluded. Descriptive subset only. |
| Boxplot: scalar duration | 16 | 4 | 0 | 16 | available | Same small scalar-duration subset; interval durations remain separate. |
| Violin: scalar duration | 16 | 4 | 0 | 16 | exploratory | Kernel density is unstable for this small, discrete sample; label exploratory. |
| Scatter + regression: duration vs credits | 0 | 20 | 0 | 2 | insufficient | Only 2 paired IDs; largest single credit-system subset has 1. Fewer than 5 comparable pairs. |
| Correlation heatmap | 0 | 20 | 0 | 0 | insufficient | No adequate matrix of comparable numeric attributes with sufficient pairwise coverage; mixed credit systems excluded. |
| Sunburst: identity status to program | 20 | 0 | 0 | 20 | available | Record-level snapshot counts; each listed program contributes one record. |
| Network: program to evidenced course names | 5 | 15 | 21 | 21 | available | Only captured course-list excerpts; edge_count counts program-course links, not programs. Lists are partial, not full curricula. |
| Missing attribute values | 20 | 0 | 0 | 20 | available | Missingness describes this snapshot only; missing does not mean false or absent from the program. |
| Line/area: change over time | 0 | 20 | 0 | 0 | insufficient | Verified evidence is recorded on 1 distinct date(s); insufficient comparable repeated observations for a trend. |

## Collection and analysis limitations

All current program rows are located in Vietnam. A foreign awarding partner does not change the listed delivery-country field. No geographic coordinates are present.
Tuition, confirmed curriculum_text, and most language/award/credit values remain missing. Course lists are partial evidence excerpts, not complete curricula.
Scalar durations exclude range-valued durations. Credit totals remain in their original credit systems and are not combined.
Collection and evidence timestamps do not form a repeated, comparable time series; a line/area trend is withheld.
Values used for attribute charts require matching verified evidence with source URL and excerpt. Missing values remain missing.
Cleaning normalizes whitespace and blank strings to NA, removes only exact duplicate rows, then fails on remaining duplicate program_id rather than silently choosing a record. It does not impute missing values. Error-only collection_error blanks mean no exception was recorded; source_error and DNS failures do not establish that a page or program is absent.
duration_valid and tuition_valid are nullable checks: missing inputs remain NA; out-of-range values are flagged rather than dropped. tuition amount 0 is distinct from missing. has_tuition is tri-state and unknown amounts remain NA.
The current quality checks use the saved snapshot and collector/parser rules. They cannot establish source completeness, detect every semantic anomaly, or make the 20 records representative. Identity verification is separate from per-attribute evidence verification.
