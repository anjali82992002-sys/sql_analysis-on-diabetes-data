# sql & statistical analysis-on-diabetes-data
SQL &amp; statistical analysis of 130-US-hospitals diabetes encounters. 

In a large real-world hospital-encounter dataset for diabetic patients this analysis answers following questions: 
(1) What do medication and dosage-adjustment patterns look like for readmitted patients, and does that differ by how soon they're readmitted
(2) Do demographic factors (gender, age, race), lab results (glucose, HbA1c), or weight meaningfully associate with readmission or dosing
(3) Where an association is found, is it large enough to matter clinically, or just large enough to be statistically detectable in a sample this size? 

Data quality handling

1. '?' sentinel values (race, weight, payer_code, medical_specialty, diagnosis codes) converted to true nulls at ingest, then re-labeled as a visible 'Not Recorded' category rather than silently dropped.
2. Two medication columns (examide, citoglipton) are 'No' for every row, which made the CSV auto-type-detector misread them as BOOLEAN -- fixed by explicitly declaring all 23 medication columns as text.
3. A1Cresult / max_glu_serum encode 'not tested' as the literal string 'None' (not a true null) -- confirmed and handled explicitly so untested encounters aren't silently dropped.
4. Weight is 96.86% missing (98,569 of 101,766 encounters) -- any weight-based finding, including the overweight/obese comparison, is flagged everywhere it appears.
5. Encounters are not independent observations of distinct patients (patient_nbr repeats) -- counts are reported at both the encounter and distinct-patient level.

Key findings from Statistical Analysis

1- Prior inpatient history is the strongest signal associated with 30-day readmission -- patients readmitted within 30 days averaged 1.22 prior inpatient visits vs. 0.38 for those never readmitted (Cohen's d = 0.746, a medium effect -- the largest found anywhere in this analysis).
2- Gender, age, race, A1C, and glucose testing were all "statistically significant" (p<0.001, N>100k) but every one had a negligible-to-small Cramer's V (0.016-0.062); diabetesMed had the largest association found, at V=0.062 -- still below the conventional "small effect" threshold.
3- A descriptive weight/dosage-adjustment pattern did not survive formal testing (chi-square p=0.761) -- the "overweight/obese" proxy bucket has only 21 usable prescription-level records, illustrating why small subgroup patterns need statistical testing before being treated as real.
