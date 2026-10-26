-- ===========================================================================
-- LOAD + ONE-TIME CLEANUP
-- ===========================================================================
=============================== DATA CLEANING 01 =============================
-- '?' is this dataset's sentinel string for "missing" (race, weight,
-- payer_code, medical_specialty, diag_1/2/3). nullstr='?' converts every '?'
-- to a true SQL NULL at ingest time.
  CREATE OR REPLACE TABLE diabetic_data AS
SELECT *
FROM read_csv_auto(
    'diabetes_data_1999-2008/diabetic_data.csv',
    header = True,
    nullstr = '?',
    sample_size = -1,
    types = {
        'metformin': 'VARCHAR', 'repaglinide': 'VARCHAR', 'nateglinide': 'VARCHAR',
        'chlorpropamide': 'VARCHAR', 'glimepiride': 'VARCHAR', 'acetohexamide': 'VARCHAR',
        'glipizide': 'VARCHAR', 'glyburide': 'VARCHAR', 'tolbutamide': 'VARCHAR',
        'pioglitazone': 'VARCHAR', 'rosiglitazone': 'VARCHAR', 'acarbose': 'VARCHAR',
        'miglitol': 'VARCHAR', 'troglitazone': 'VARCHAR', 'tolazamide': 'VARCHAR',
        'examide': 'VARCHAR', 'citoglipton': 'VARCHAR', 'insulin': 'VARCHAR',
        'glyburide-metformin': 'VARCHAR', 'glipizide-metformin': 'VARCHAR',
        'glimepiride-pioglitazone': 'VARCHAR', 'metformin-rosiglitazone': 'VARCHAR',
        'metformin-pioglitazone': 'VARCHAR'
    }
);
=============================== DATA CLEANING 02 ===================================
-- Reusable long-format view: one row per (encounter x medication), for all 23
-- diabetes-medication columns. 
CREATE OR REPLACE VIEW med_long AS
SELECT *
FROM (
    UNPIVOT diabetic_data
    ON
        "metformin","repaglinide","nateglinide","chlorpropamide","glimepiride",
        "acetohexamide","glipizide","glyburide","tolbutamide","pioglitazone",
        "rosiglitazone","acarbose","miglitol","troglitazone","tolazamide",
        "examide","citoglipton","insulin","glyburide-metformin",
        "glipizide-metformin","glimepiride-pioglitazone",
        "metformin-rosiglitazone","metformin-pioglitazone"
    INTO NAME medication VALUE status
);
-- ============================================================================
-- SECTION 1 -- READMISSION & MEDICATION PROFILES
-- ============================================================================

-- 1.1 Most frequently prescribed medications, patients readmitted <= 30 days
SELECT
    medication,
    COUNT(*)                              AS n_prescriptions,
    COUNT(DISTINCT patient_nbr)           AS n_distinct_patients,
    RANK() OVER (ORDER BY COUNT(*) DESC)  AS prescription_rank
FROM med_long
WHERE readmitted = '<30'
  AND status <> 'No'
GROUP BY medication
ORDER BY n_prescriptions DESC;

-- 1.2 Medication profiles, patients readmitted > 30 days
SELECT
    medication,
    COUNT(*)                              AS n_prescriptions,
    COUNT(DISTINCT patient_nbr)           AS n_distinct_patients,
    RANK() OVER (ORDER BY COUNT(*) DESC)  AS prescription_rank
FROM med_long
WHERE readmitted = '>30'
  AND status <> 'No'
GROUP BY medication
ORDER BY n_prescriptions DESC;

-- 1.3a Readmission tier distribution, encounter-level (exact partition --
-- every encounter has exactly one readmitted value)
SELECT
    readmitted                                         AS readmission_tier,
    COUNT(*)                                            AS n_encounters,
    COUNT(DISTINCT patient_nbr)                         AS n_distinct_patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS pct_of_encounters
FROM diabetic_data
GROUP BY readmitted
ORDER BY n_encounters DESC;

-- 1.3b Readmission tier distribution, patient-level (mutually exclusive:
-- any <30 encounter wins, else any >30 encounter wins, else NO)
WITH patient_tier AS (
    SELECT
        patient_nbr,
        CASE
            WHEN MAX(CASE WHEN readmitted = '<30' THEN 1 ELSE 0 END) = 1 THEN '<30'
            WHEN MAX(CASE WHEN readmitted = '>30' THEN 1 ELSE 0 END) = 1 THEN '>30'
            ELSE 'NO'
        END AS readmission_tier
    FROM diabetic_data
    GROUP BY patient_nbr
)
SELECT
    readmission_tier,
    COUNT(*)                                            AS n_patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS pct_of_patients
FROM patient_tier
GROUP BY readmission_tier
ORDER BY n_patients DESC;


-- ============================================================================
-- SECTION 2 -- DOSAGE DYNAMICS & CHANGES
-- ============================================================================

-- 2.1a Dosage adjustment direction, instance-level (per prescribed drug x encounter)
SELECT
    CASE status
        WHEN 'Up'     THEN 'Up'
        WHEN 'Down'   THEN 'Down'
        WHEN 'Steady' THEN 'No Change'
    END                                                  AS dosage_direction,
    COUNT(*)                                             AS n_prescriptions,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)   AS pct_of_prescriptions
FROM med_long
WHERE status <> 'No'
GROUP BY dosage_direction
ORDER BY n_prescriptions DESC;

-- 2.1b Dosage adjustment direction, patient-level (MECE: Up > Down > No Change priority)
WITH patient_direction AS (
    SELECT
        patient_nbr,
        CASE
            WHEN MAX(CASE WHEN status = 'Up'     THEN 1 ELSE 0 END) = 1 THEN 'Up'
            WHEN MAX(CASE WHEN status = 'Down'   THEN 1 ELSE 0 END) = 1 THEN 'Down'
            WHEN MAX(CASE WHEN status = 'Steady' THEN 1 ELSE 0 END) = 1 THEN 'No Change'
        END AS dosage_direction
    FROM med_long
    WHERE status <> 'No'
    GROUP BY patient_nbr
)
SELECT
    dosage_direction,
    COUNT(*)                                            AS n_patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS pct_of_patients
FROM patient_direction
GROUP BY dosage_direction
ORDER BY n_patients DESC;

-- 2.2 Medications ranked by Up-adjustment frequency
  SELECT
    medication,
    COUNT(*)                              AS n_up_adjustments,
    COUNT(DISTINCT patient_nbr)           AS n_distinct_patients,
    RANK() OVER (ORDER BY COUNT(*) DESC)  AS up_rank
FROM med_long
WHERE status = 'Up'
GROUP BY medication
ORDER BY n_up_adjustments DESC;

-- 2.2 Medications ranked by Down-adjustment frequency
SELECT
    medication,
    COUNT(*)                              AS n_down_adjustments,
    COUNT(DISTINCT patient_nbr)           AS n_distinct_patients,
    RANK() OVER (ORDER BY COUNT(*) DESC)  AS down_rank
FROM med_long
WHERE status = 'Down'
GROUP BY medication
ORDER BY n_down_adjustments DESC;

-- ============================================================================
-- SECTION 3 -- LAB BIOMARKER STRATIFICATION
-- ============================================================================
  -- 3.1a Top prescribed medications, by glucose category (>200 / >300 are
-- mutually-exclusive RESULT BUCKETS as coded in this dataset, not cumulative
-- thresholds)
SELECT
    max_glu_serum                         AS glucose_category,
    medication,
    COUNT(*)                              AS n_prescriptions,
    COUNT(DISTINCT patient_nbr)           AS n_distinct_patients,
    RANK() OVER (
        PARTITION BY max_glu_serum ORDER BY COUNT(*) DESC
    )                                      AS rank_within_glucose_category
FROM med_long
WHERE max_glu_serum IN ('>200', '>300')
  AND status <> 'No'
GROUP BY max_glu_serum, medication
QUALIFY rank_within_glucose_category <= 10
ORDER BY max_glu_serum, rank_within_glucose_category;

-- 3.1b Dosage-change breakdown, by glucose category
SELECT
    max_glu_serum                                                 AS glucose_category,
    status                                                        AS dosage_change,
    COUNT(*)                                                      AS n_prescriptions,
    ROUND(100.0 * COUNT(*)
          / SUM(COUNT(*)) OVER (PARTITION BY max_glu_serum), 2)   AS pct_within_glucose_category
FROM med_long
WHERE max_glu_serum IN ('>200', '>300')
  AND status <> 'No'
GROUP BY max_glu_serum, status
ORDER BY max_glu_serum, n_prescriptions DESC;

-- 3.2a Top prescribed medications, by HbA1c category (same mutually-exclusive
-- bucket caveat: '>7' = measured >7% but <8%, '>8' = measured >=8%)
SELECT
    "A1Cresult"                           AS a1c_category,
    medication,
    COUNT(*)                              AS n_prescriptions,
    COUNT(DISTINCT patient_nbr)           AS n_distinct_patients,
    RANK() OVER (
        PARTITION BY "A1Cresult" ORDER BY COUNT(*) DESC
    )                                      AS rank_within_a1c_category
FROM med_long
WHERE "A1Cresult" IN ('>7', '>8')
  AND status <> 'No'
GROUP BY "A1Cresult", medication
QUALIFY rank_within_a1c_category <= 10
ORDER BY a1c_category, rank_within_a1c_category;

-- 3.2b Dosage-change breakdown, by HbA1c category
SELECT
    "A1Cresult"                                                    AS a1c_category,
    status                                                        AS dosage_change,
    COUNT(*)                                                      AS n_prescriptions,
    ROUND(100.0 * COUNT(*)
          / SUM(COUNT(*)) OVER (PARTITION BY "A1Cresult"), 2)     AS pct_within_a1c_category
FROM med_long
WHERE "A1Cresult" IN ('>7', '>8')
  AND status <> 'No'
GROUP BY "A1Cresult", status
ORDER BY a1c_category, n_prescriptions DESC;


-- ============================================================================
-- SECTION 4 -- DEMOGRAPHICS & WEIGHT CORRELATION ANALYSIS
-- ============================================================================

-- 4.1 Gender distribution by readmission tier (encounter-level)
SELECT
    readmitted                                  AS readmission_tier,
    gender,
    COUNT(*)                                    AS n_encounters,
    COUNT(DISTINCT patient_nbr)                 AS n_distinct_patients,
    ROUND(100.0 * COUNT(*)
          / SUM(COUNT(*)) OVER (PARTITION BY readmitted), 2)  AS pct_within_tier
FROM diabetic_data
GROUP BY readmitted, gender
ORDER BY readmission_tier, n_encounters DESC;

-- 4.2 Age bracket distribution (sorted by the bracket's numeric lower bound,
-- not the raw string, via REGEXP_EXTRACT + CAST)
SELECT
    age                                                   AS age_bracket,
    COUNT(*)                                               AS n_encounters,
    COUNT(DISTINCT patient_nbr)                            AS n_distinct_patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)     AS pct_of_encounters
FROM diabetic_data
GROUP BY age
ORDER BY CAST(REGEXP_EXTRACT(age, '\d+') AS INTEGER);

-- 4.3a Weight tier distribution. weight is ~97% NULL in this dataset;
-- COALESCE surfaces that explicitly as its own 'Not Recorded' row.
SELECT
    COALESCE(weight, 'Not Recorded')                     AS weight_tier,
    COUNT(*)                                              AS n_encounters,
    COUNT(DISTINCT patient_nbr)                           AS n_distinct_patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)    AS pct_of_encounters
FROM diabetic_data
GROUP BY weight_tier
ORDER BY n_encounters DESC;

-- 4.3b Up-adjustment rate by weight class.
-- CAVEAT: this dataset has weight IN POUNDS ONLY, no height field, so a true
-- BMI-based "overweight/obese" classification is not computable. The CASE
-- below uses a pragmatic, clearly-labeled weight-only proxy (>=175 lb).
WITH weight_class AS (
    SELECT
        encounter_id,
        CASE
            WHEN weight IN ('[175-200)', '>200') THEN 'Overweight/Obese (proxy: weight >=175 lb)'
            WHEN weight IS NULL                  THEN 'Not Recorded'
            ELSE 'Other recorded weight tiers (<175 lb)'
        END AS weight_class
    FROM diabetic_data
)
SELECT
    wc.weight_class,
    COUNT(*)                                                       AS n_prescriptions,
    SUM(CASE WHEN ml.status = 'Up' THEN 1 ELSE 0 END)              AS n_up_adjustments,
    ROUND(100.0 * SUM(CASE WHEN ml.status = 'Up' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                                           AS pct_up_adjustment_rate
FROM weight_class wc
JOIN med_long ml ON ml.encounter_id = wc.encounter_id
WHERE ml.status <> 'No'
GROUP BY wc.weight_class
ORDER BY pct_up_adjustment_rate DESC;
-- CAVEAT: the 'Overweight/Obese' proxy bucket covers only 14 of 101,766
-- encounters (11 in '[175-200)' + 3 in '>200') -- any rate computed on it is
-- not statistically reliable. This reflects the source data's ~96.9%
-- missingness on weight, not an error in the query.

-- 4.3c Top prescribed medications: overweight/obese proxy vs. non-overweight.
WITH weight_class AS (
    SELECT
        encounter_id,
        CASE
            WHEN weight IN ('[175-200)', '>200') THEN 'Overweight/Obese (proxy: weight >=175 lb)'
            ELSE 'Other recorded weight tiers (<175 lb)'
        END AS weight_class
    FROM diabetic_data
    WHERE weight IS NOT NULL
)
SELECT
    wc.weight_class,
    ml.medication,
    COUNT(*)                                                        AS n_prescriptions,
    RANK() OVER (
        PARTITION BY wc.weight_class ORDER BY COUNT(*) DESC
    )                                                                AS rank_within_weight_class
FROM weight_class wc
JOIN med_long ml ON ml.encounter_id = wc.encounter_id
WHERE ml.status <> 'No'
GROUP BY wc.weight_class, ml.medication
QUALIFY rank_within_weight_class <= 10
ORDER BY wc.weight_class, rank_within_weight_class;


-- ============================================================================
-- SECTION 5 -- PRESCRIBING PREVALENCE
-- ============================================================================

-- 5. Rank all medications across the overall patient population, by how many
-- DISTINCT patients each drug reaches (not raw prescription count -- see
-- explanation doc)
SELECT
    medication,
    COUNT(*)                                              AS n_prescriptions,
    COUNT(DISTINCT patient_nbr)                           AS n_distinct_patients,
    RANK() OVER (ORDER BY COUNT(DISTINCT patient_nbr) DESC) AS prevalence_rank
FROM med_long
WHERE status <> 'No'
GROUP BY medication
ORDER BY prevalence_rank;
-- 
  
  
