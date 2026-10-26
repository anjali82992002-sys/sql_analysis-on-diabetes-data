# SQL & Statistical Analysis-on-diabetes-data
SQL &amp; statistical analysis of 130-US-hospitals diabetes encounters. 

In a large real-world hospital-encounter dataset for diabetic patients this analysis answers following questions: 
(1) What do medication and dosage-adjustment patterns look like for readmitted patients, and does that differ by how soon they're readmitted
(2) Do demographic factors (gender, age, race), lab results (glucose, HbA1c), or weight meaningfully associate with readmission or dosing
(3) Where an association is found, is it large enough to matter clinically, or just large enough to be statistically detectable in a sample this size? 

### 1. Use Case

### 1.1 What this project is

A two-layer analysis of the **UCI "Diabetes 130-US hospitals (1999–2008)"** dataset:

- **Layer 1 (SQL):** answer 11 descriptive clinical/operational questions about readmission,
  medication prescribing, dosage adjustment, lab-biomarker stratification, and demographics —
  expressed as **real, portable SQL**, not pandas method chains.
- **Layer 2 (Statistics):** promote the descriptive SQL findings into **formal hypothesis tests**
  with **effect sizes**, so that "this group looks different" becomes a defensible claim with a
  measured magnitude.

### 1.2 The questions answered (11 SQL tasks, 5 sections)

| § | Task | Question |
|---|---|---|
| 1.1 | Medication profile, `<30`-day readmits | Which drugs are most prescribed in patients readmitted within 30 days? |
| 1.2 | Medication profile, `>30`-day readmits | Same, for later readmissions (structurally identical for comparability) |
| 1.3a/b | Readmission tier distribution | How are patients distributed across `<30` / `>30` / `NO` — at encounter level and at patient level? |
| 2.1a/b | Dosage direction | How often are dosages increased / decreased / unchanged — per prescription and per patient? |
| 2.2 | Up/Down ranking | Which medications are adjusted up or down most often? |
| 3.1 | High serum glucose (`>200`, `>300`) | What is prescribed, and how are dosages adjusted, in hyperglycaemic patients? |
| 3.2 | Elevated HbA1c (`>7`, `>8`) | Same question, stratified on HbA1c instead |
| 4.1 | Gender × readmission | How does gender distribute across readmission tiers? |
| 4.2 | Age distribution | How are encounters distributed across age brackets? |
| 4.3a/b/c | Weight analysis | Weight-tier distribution, Up-adjustment rate by weight class, top drugs by weight class |
| 5 | Prescribing prevalence | Rank all 23 medications across the whole population |

### 1.3 The statistical layer (15 tests)

- **7 chi-square tests** (categorical × categorical) with **Cramér's V** effect size.
- **8 continuous-variable comparisons** (`<30`-day readmission vs. no readmission) with normality
  testing, **Welch's t-test**, **Mann-Whitney U**, **Cohen's d**, and **rank-biserial r**.

### 1.4 The project's central intellectual finding

**Statistical significance ≠ practical significance.** With N ≈ 101,766 encounters, *every single
test returns p < 0.05* — several at astronomically small p-values (p = 1.2 × 10⁻⁸⁴). Yet the
effect sizes are uniformly tiny:

- Largest Cramér's V = **0.062** (`diabetesMed`) — negligible on any conventional scale.
- Largest rank-biserial r = **−0.287** (`number_inpatient`) — the only variable approaching a
  small-to-moderate effect.

**Interpretation:** at this sample size, p-values are essentially guaranteed and carry almost no
information. The effect sizes are what actually separate signal from noise, and they say that
demographics and lab-test categories are **weak** readmission discriminators, while **prior
inpatient utilization** is the one genuinely useful signal. This finding is what directly motivates
Project 2's predictive-modelling work.

### 1.5 Data quality handling

1. '?' sentinel values (race, weight, payer_code, medical_specialty, diagnosis codes) converted to true nulls at ingest, then re-labeled as a visible 'Not Recorded' category rather than silently dropped.
2. Two medication columns (examide, citoglipton) are 'No' for every row, which made the CSV auto-type-detector misread them as BOOLEAN -- fixed by explicitly declaring all 23 medication columns as text.
3. A1Cresult / max_glu_serum encode 'not tested' as the literal string 'None' (not a true null) -- confirmed and handled explicitly so untested encounters aren't silently dropped.
4. Weight is 96.86% missing (98,569 of 101,766 encounters) -- any weight-based finding, including the overweight/obese comparison, is flagged everywhere it appears.
5. Encounters are not independent observations of distinct patients (patient_nbr repeats) -- counts are reported at both the encounter and distinct-patient level.

### 1.6 Key findings from Statistical Analysis

1- Prior inpatient history is the strongest signal associated with 30-day readmission -- patients readmitted within 30 days averaged 1.22 prior inpatient visits vs. 0.38 for those never readmitted (Cohen's d = 0.746, a medium effect -- the largest found anywhere in this analysis).
2- Gender, age, race, A1C, and glucose testing were all "statistically significant" (p<0.001, N>100k) but every one had a negligible-to-small Cramer's V (0.016-0.062); diabetesMed had the largest association found, at V=0.062 -- still below the conventional "small effect" threshold.
3- A descriptive weight/dosage-adjustment pattern did not survive formal testing (chi-square p=0.761) -- the "overweight/obese" proxy bucket has only 21 usable prescription-level records, illustrating why small subgroup patterns need statistical testing before being treated as real.
