# Storytelling report: AI & Data Science programs in Vietnam

## A small registry, a large verification gap

### Executive summary

This project builds an auditable snapshot of **20 AI and Data Science program records in Vietnam**. It is a registry of records gathered for this project—not a census of all programs in Vietnam, and not a representative sample. The current snapshot shows both useful structure in the available evidence and a substantial verification gap: **6 records (30%) have a matched program-and-university identity, 4 (20%) need manual identity review, and 10 (50%) have a recorded source/collection error**.

The main finding is therefore not a ranking of universities. It is that a useful comparison requires evidence at the level of each attribute, while access errors and missing values must remain visible rather than being treated as proof that a program or feature does not exist.

### What the snapshot says

- **20 records, 20 unique program IDs.** All 20 records currently carry `country = Vietnam`; this describes the registry design and contents, not the geographic distribution of all AI/Data Science programs.
- **Verification status is uneven.** Six records are marked `verified_identity`, four `needs_manual_review`, and ten `source_error`. A verified identity means the program and university were matched using saved evidence; it does **not** mean every field about that program has been verified. A source error means collection could not be completed as recorded; it does **not** prove that the program is nonexistent.
- **Duration is the most analysable numeric attribute in this snapshot.** Sixteen records have a scalar duration from 3.0 to 4.5 years. Two additional records preserve a duration interval (3.5–4 years and 4–4.5 years); the intervals are kept separate rather than silently converted to point estimates. Four records have no scalar duration.
- **Credit totals need context.** The registry contains 17 numeric total-credit values, but their stated credit systems are not fully comparable. A raw total should not be used to rank programs or combined into a regression without confirming compatible units and scope.
- **Tuition is not currently suitable for comparison.** Tuition amount and currency are missing across this snapshot. No price comparison or affordability conclusion can responsibly be drawn from these records.
- **Curriculum evidence is partial.** Five records have captured course-list excerpts, producing 21 program–course links in the network view. Those links are not 21 programs and the excerpts should not be interpreted as complete curricula.

### How to read the dashboard

The dashboard is designed as an evidence explorer, not a league table:

1. **Overview and status counts** show the composition of this registry snapshot and its verification state.
2. **Duration distribution** describes only the 16 records with scalar durations. The violin view is exploratory because the sample is small and values are discrete.
3. **Program–course network** shows only the course names captured in the available excerpts. It is a partial-evidence view, not a measure of curriculum completeness.
4. **Missingness and evidence sections** show where comparisons are blocked. Missing values are unknown in this dataset; they are not equivalent to zero, false, or “not offered.”
5. **Real-data relationship analyses** remain withheld where the current data do not support a defensible conclusion: there are only two duration–credit pairs before applying credit-system comparability, and the largest single credit-system group has one pair. Evidence timestamps represent one distinct date, not a repeated time series. To demonstrate the required visualization methods without misrepresenting evidence, the dashboard now has a separate, clearly labeled **synthetic demo area** with interactive Plotly Scatter + OLS regression, Correlation Heatmap, and Line/Area charts. These are teaching examples only and are not findings about real universities.

### Data quality and method

The collection and processing pipeline separates raw inputs, expanded records, cleaned records, and an attribute-level evidence ledger. Attribute claims should be traced to `data/processed/official_attribute_evidence.csv`, including source URL, checked time, excerpt, status, and scope notes. The cleaner preserves duration intervals separately and does not convert incompatible credit systems.

Interpret the statuses narrowly:

- `verified_identity`: identity checks passed; other attributes still need their own evidence.
- `needs_manual_review`: identity has not been accepted as verified.
- `source_error`: a recorded collection/source-access problem; not evidence of nonexistence.

The dataset is small and dependent on which official pages could be reached and what evidence those pages exposed at collection time. Any percentages in this report are **percentages of the 20 records in this snapshot only**.

### Recommended next steps

1. **Resolve collection failures safely.** Review the ten `source_error` records one by one, retry only when appropriate, and document whether the issue is transient, a moved page, a blocked request, or another cause. Do not repeatedly hammer a failing site.
2. **Manually resolve four identity reviews.** Save official-source excerpts and the exact page URL before changing a status.
3. **Prioritise attribute-level evidence.** Tuition and currency are currently unavailable; duration, award title, language, credit system, and curriculum each need their own supporting evidence rather than inheriting confidence from identity verification.
4. **Keep real and synthetic analyses separate.** Only draw conclusions about actual programs when enough comparable observations exist. Synthetic values may illustrate chart mechanics in a separate, prominent demo area, but must be labeled and must never be mixed into the real-data findings.
5. **Re-run validation and tests after changes.** Record the actual command and result, and distinguish local test results from browser interaction checks.

### Conclusion

The project’s strongest result is a transparent, traceable registry with explicit uncertainty—not a claim that it describes the entire Vietnamese higher-education market. Its next improvement should be better source coverage and attribute verification. Until then, the most responsible story is about **what is known, what remains unknown, and why those distinctions matter**. The dashboard also includes three clearly labeled synthetic interactive charts to demonstrate the required techniques; their companion CSV files explicitly mark every row as synthetic and are not part of the real registry.

---

*Snapshot basis: repository CSVs and `reports/eda/chart_eligibility.csv` on the audit branch at the time this report was prepared. Counts are descriptive of that snapshot; no unsupported national estimates are made.*
