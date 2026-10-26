# sql_analysis-on-diabetes-data
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
