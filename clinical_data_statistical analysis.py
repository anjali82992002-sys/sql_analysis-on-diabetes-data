import os
import duckdb
import numpy as np
import pandas as pd
from scipy import stats

CSV_PATH = "diabetes_data_1999-2008/diabetic_data.csv"
RESULTS_DIR = "./stats_results"
FIG_DIR = "./stats_figures"
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})
COLOR_A = "#4C72B0"   # first/reference group
COLOR_B = "#DD8452"   # second/comparison group
COLOR_C = "#55A868"

# ---------------------------------------------------------------------------
# Load and cleanup 
# ---------------------------------------------------------------------------
MED_COL_NAMES = [
    "metformin", "repaglinide", "nateglinide", "chlorpropamide", "glimepiride",
    "acetohexamide", "glipizide", "glyburide", "tolbutamide", "pioglitazone",
    "rosiglitazone", "acarbose", "miglitol", "troglitazone", "tolazamide",
    "examide", "citoglipton", "insulin", "glyburide-metformin",
    "glipizide-metformin", "glimepiride-pioglitazone",
    "metformin-rosiglitazone", "metformin-pioglitazone",
]
med_types_sql = ", ".join(f"'{c}': 'VARCHAR'" for c in MED_COL_NAMES)

con = duckdb.connect()
con.execute(f"""
    CREATE OR REPLACE TABLE diabetic_data AS
    SELECT *
    FROM read_csv_auto(
        '{CSV_PATH}', header = True, nullstr = '?', sample_size = -1,
        types = {{{med_types_sql}}}
    )
""")
df = con.execute("SELECT * FROM diabetic_data").df()
print(f"Loaded {len(df):,} encounters, {df['patient_nbr'].nunique():,} distinct patients")

# weight class proxy, reused verbatim from project1_sql_analysis.py section 4.3
df["weight_class"] = np.select(
    [df["weight"].isin(["[175-200)", ">200"]), df["weight"].isna()],
    ["Overweight/Obese (proxy)", "Not Recorded"],
    default="Other recorded (<175 lb)",
)


MED_COLS_SQL = ", ".join(f'"{c}"' for c in MED_COL_NAMES)
med_long = con.execute(f"""
    SELECT encounter_id, status
    FROM (UNPIVOT diabetic_data ON {MED_COLS_SQL} INTO NAME medication VALUE status)
    WHERE status <> 'No'
""").df()

chi_rows = []
cont_rows = []

# ===========================================================================
# Chi-square helper
# ===========================================================================
def run_chi_square(label, s1, s2, note=""):
    """s1, s2: two pandas Series of equal length/index (categorical). Builds
    the contingency table, runs chi2_contingency, computes Cramer's V."""
    ct = pd.crosstab(s1, s2)
    chi2, p, dof, expected = stats.chi2_contingency(ct)
    n = ct.values.sum()
    min_dim = min(ct.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * min_dim)) if min_dim > 0 else np.nan

    # flag if Cochran's rule-of-thumb (no more than 20% of cells <5, none <1)
    # is violated, since chi-square's p-value is only reliable when expected
    # counts are large enough
    pct_cells_lt5 = 100 * (expected < 5).sum() / expected.size
    min_expected = expected.min()

    row = {
        "test": label, "n": int(n), "chi2": chi2, "dof": dof, "p_value": p,
        "cramers_v": cramers_v, "pct_expected_cells_lt5": round(pct_cells_lt5, 1),
        "min_expected_count": round(min_expected, 2), "note": note,
    }
    chi_rows.append(row)
    print(f"[chi2] {label}: chi2={chi2:.2f} dof={dof} p={p:.3g} "
          f"Cramer's V={cramers_v:.3f} (n={n:,}, {pct_cells_lt5:.1f}% cells<5)")
    return ct


# ===========================================================================
# Continuous-variable helper
# ===========================================================================
def run_continuous_test(label, col, group_col, group_a, group_b):
    """Two-group comparison for one continuous column. Checks normality in
    BOTH groups (D'Agostino-Pearson, valid at any N, plus Shapiro-Wilk on a
    capped 5,000-row subsample since SciPy's Shapiro implementation is only
    validated up to roughly that size), then runs both Welch's t-test
    (unequal-variance t-test -- the safer default vs. Student's pooled-
    variance t-test when group sizes/variances differ, as they do here) and
    the Mann-Whitney U test, with effect sizes for each."""
    a = df.loc[df[group_col] == group_a, col].dropna()
    b = df.loc[df[group_col] == group_b, col].dropna()
    n_a, n_b = len(a), len(b)

    rng = np.random.default_rng(42)
    a_sub = a.sample(min(5000, n_a), random_state=42) if n_a > 5000 else a
    b_sub = b.sample(min(5000, n_b), random_state=42) if n_b > 5000 else b
    shapiro_a_p = stats.shapiro(a_sub)[1]
    shapiro_b_p = stats.shapiro(b_sub)[1]
    dagostino_a_p = stats.normaltest(a)[1] if n_a >= 20 else np.nan
    dagostino_b_p = stats.normaltest(b)[1] if n_b >= 20 else np.nan
    normal_assumption_met = min(shapiro_a_p, shapiro_b_p, dagostino_a_p, dagostino_b_p) > 0.05

    # Welch's t-test (does NOT assume equal variances between groups)
    t_stat, t_p = stats.ttest_ind(a, b, equal_var=False)
    pooled_sd = np.sqrt(((n_a - 1) * a.var(ddof=1) + (n_b - 1) * b.var(ddof=1)) / (n_a + n_b - 2))
    cohens_d = (a.mean() - b.mean()) / pooled_sd if pooled_sd > 0 else np.nan

    # Mann-Whitney U (rank-based, distribution-free -- valid regardless of
    # the normality finding above)
    u_stat, u_p = stats.mannwhitneyu(a, b, alternative="two-sided")
    # rank-biserial correlation: standard effect size for Mann-Whitney,
    # ranges -1..+1, analogous in spirit to Cohen's d but on ranks
    rank_biserial = 1 - (2 * u_stat) / (n_a * n_b)

    row = {
        "variable": col, "group_a": group_a, "n_a": n_a, "mean_a": a.mean(),
        "median_a": a.median(), "sd_a": a.std(),
        "group_b": group_b, "n_b": n_b, "mean_b": b.mean(),
        "median_b": b.median(), "sd_b": b.std(),
        "shapiro_p_a": shapiro_a_p, "shapiro_p_b": shapiro_b_p,
        "dagostino_p_a": dagostino_a_p, "dagostino_p_b": dagostino_b_p,
        "normal_assumption_met": normal_assumption_met,
        "welch_t_stat": t_stat, "welch_t_p": t_p, "cohens_d": cohens_d,
        "mannwhitney_u": u_stat, "mannwhitney_p": u_p,
        "rank_biserial_r": rank_biserial,
        "recommended_test": "Mann-Whitney U" if not normal_assumption_met else "Welch's t-test",
    }
    cont_rows.append(row)
    print(f"[cont] {col} ({group_a} n={n_a:,} vs {group_b} n={n_b:,}): "
          f"normal={normal_assumption_met} | Welch p={t_p:.3g} d={cohens_d:.3f} | "
          f"MWU p={u_p:.3g} r={rank_biserial:.3f}")
    return a, b


# ===========================================================================
# SECTION A -- Chi-square tests (categorical x categorical)
# ===========================================================================
print("\n" + "=" * 90)
print("CHI-SQUARE TESTS")
print("=" * 90)

ct_gender = run_chi_square(
    "Readmission tier x Gender", df["readmitted"],
    df["gender"].replace("Unknown/Invalid", np.nan),
    note="3 rows with gender='Unknown/Invalid' excluded (negligible n, undefined category)",
)
ct_age = run_chi_square("Readmission tier x Age bracket", df["readmitted"], df["age"])
ct_race = run_chi_square(
    "Readmission tier x Race", df["readmitted"], df["race"],
    note="race is NULL (originally '?') for 2.23% of encounters; chi2_contingency "
         "implicitly drops rows where either variable is NaN via the crosstab step",
)
ct_a1c = run_chi_square(
    "Readmission tier x A1Cresult", df["readmitted"],
    df["A1Cresult"].replace({"None": "Not tested"}),
    note="A1Cresult encodes 'not tested' as the literal string 'None' (not a true "
         "null -- confirmed via .isna().sum()==0), relabeled 'Not tested' and kept "
         "as its own explicit category rather than dropped",
)
ct_glu = run_chi_square(
    "Readmission tier x max_glu_serum", df["readmitted"],
    df["max_glu_serum"].replace({"None": "Not tested"}),
    note="same treatment as A1Cresult: 'not tested' (literal string 'None' in the "
         "source data) relabeled and retained as its own category",
)
ct_dmed = run_chi_square("Readmission tier x diabetesMed", df["readmitted"], df["diabetesMed"])

# Test 7: does the overweight/obese weight-class proxy have a different rate
# of Up dosage adjustments? (follow-up, now as a formal test, on the question
# raised descriptively in project1_sql_analysis.py section 4.3)
wc_up = (
    med_long.merge(df[["encounter_id", "weight_class"]], on="encounter_id", how="left")
)
wc_up = wc_up[wc_up["weight_class"] != "Not Recorded"].copy()
wc_up["is_up"] = np.where(wc_up["status"] == "Up", "Up", "Not Up")
ct_weight_up = run_chi_square(
    "Weight class (overweight/obese proxy vs. other) x Up-adjustment",
    wc_up["weight_class"], wc_up["is_up"],
    note="Scoped to the 3,306 prescribed-drug instances with a RECORDED weight "
         "(excludes the 96.9% with weight='Not Recorded'); of those, only 21 "
         "instances are in the 'Overweight/Obese (proxy)' bucket -- see "
         "min_expected_count/pct_expected_cells_lt5 for why this result is fragile.",
)

chi_df = pd.DataFrame(chi_rows)
chi_df.to_csv(os.path.join(RESULTS_DIR, "chi_square_results.csv"), index=False)

# ===========================================================================
# SECTION B -- Continuous variable tests: <30-day readmission vs. no readmission
# ===========================================================================
print("\n" + "=" * 90)
print("CONTINUOUS-VARIABLE TESTS (<30-day readmission vs. No readmission)")
print("=" * 90)

CONTINUOUS_VARS = [
    "time_in_hospital", "num_medications", "num_lab_procedures", "num_procedures",
    "number_outpatient", "number_emergency", "number_inpatient", "number_diagnoses",
]
for col in CONTINUOUS_VARS:
    run_continuous_test(col, col, "readmitted", "<30", "NO")

cont_df = pd.DataFrame(cont_rows)
cont_df.to_csv(os.path.join(RESULTS_DIR, "continuous_results.csv"), index=False)

# ===========================================================================
# Figures
# ===========================================================================
# Fig 1: readmission tier counts
fig, ax = plt.subplots(figsize=(6, 4))
tier_counts = df["readmitted"].value_counts().reindex(["NO", ">30", "<30"])
ax.bar(tier_counts.index, tier_counts.values, color=[COLOR_A, COLOR_B, COLOR_C])
for i, v in enumerate(tier_counts.values):
    ax.text(i, v + 800, f"{v:,}", ha="center", fontsize=9)
ax.set_ylabel("N encounters")
ax.set_title("Readmission tier distribution (encounter-level)")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig01_readmission_tiers.png"), dpi=160)
plt.close(fig)

# Fig 2: A1Cresult x readmission (stacked %, the strongest categorical result)
ct_pct = pd.crosstab(df["readmitted"], df["A1Cresult"].replace({"None": "Not tested"}), normalize="index") * 100
ct_pct = ct_pct.reindex(["NO", ">30", "<30"])
fig, ax = plt.subplots(figsize=(7, 4.5))
bottom = np.zeros(len(ct_pct))
colors = [COLOR_A, COLOR_B, COLOR_C, "#8C8C8C"]
for i, col in enumerate(["Not tested", "Norm", ">7", ">8"]):
    ax.bar(ct_pct.index, ct_pct[col], bottom=bottom, label=col, color=colors[i % len(colors)])
    bottom += ct_pct[col].values
ax.set_ylabel("% of encounters within tier")
ax.set_title("A1C testing/result by readmission tier")
ax.legend(title="A1Cresult", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig02_a1c_by_tier.png"), dpi=160)
plt.close(fig)

# Fig 3: boxplots for the two continuous variables with the largest effect
# sizes (chosen programmatically after the tests run, see below)
cont_df_sorted = cont_df.reindex(cont_df["rank_biserial_r"].abs().sort_values(ascending=False).index)
top2_vars = cont_df_sorted["variable"].head(2).tolist()
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
for ax, col in zip(axes, top2_vars):
    a = df.loc[df["readmitted"] == "<30", col].dropna()
    b = df.loc[df["readmitted"] == "NO", col].dropna()
    ax.boxplot([a, b], tick_labels=["<30 days", "No readmission"], showfliers=False,
               patch_artist=True,
               boxprops=dict(facecolor=COLOR_A, alpha=0.6))
    ax.set_title(col)
fig.suptitle("Distributions for the two largest-effect-size continuous variables\n"
              "(outlier points hidden for readability; see CSV for full summary stats)")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig03_top_continuous_boxplots.png"), dpi=160)
plt.close(fig)

# Fig 4: histogram showing right-skew (why normality was rejected) for the
# single most-skewed variable
skew_col = cont_df.loc[cont_df["variable"] == "number_inpatient", "variable"].iloc[0] \
    if "number_inpatient" in cont_df["variable"].values else CONTINUOUS_VARS[0]
fig, ax = plt.subplots(figsize=(6, 4))
ax.hist(df[skew_col].dropna(), bins=range(0, int(df[skew_col].max()) + 2), color=COLOR_A,
        edgecolor="white")
ax.set_xlabel(skew_col)
ax.set_ylabel("N encounters")
ax.set_title(f"{skew_col} distribution (illustrates non-normal, right-skewed shape)")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig04_skew_example.png"), dpi=160)
plt.close(fig)

# Fig 5: effect-size summary across all chi-square tests
fig, ax = plt.subplots(figsize=(8, 4.5))
chi_plot = chi_df.sort_values("cramers_v")
ax.barh(chi_plot["test"], chi_plot["cramers_v"], color=COLOR_A)
ax.set_xlabel("Cramer's V (effect size)")
ax.set_title("Chi-square tests: effect size summary")
for y, v in enumerate(chi_plot["cramers_v"]):
    ax.text(v + 0.002, y, f"{v:.3f}", va="center", fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig05_cramers_v_summary.png"), dpi=160)
plt.close(fig)

# Fig 6: effect-size summary across all continuous tests
fig, ax = plt.subplots(figsize=(8, 4.5))
cont_plot = cont_df.sort_values("rank_biserial_r", key=lambda s: s.abs())
ax.barh(cont_plot["variable"], cont_plot["rank_biserial_r"], color=COLOR_B)
ax.set_xlabel("Rank-biserial correlation r (Mann-Whitney effect size)")
ax.set_title("Continuous-variable tests: effect size summary\n(<30-day readmission vs. No readmission)")
for y, v in enumerate(cont_plot["rank_biserial_r"]):
    ax.text(v + (0.003 if v >= 0 else -0.003), y, f"{v:.3f}", va="center",
            ha="left" if v >= 0 else "right", fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig06_rank_biserial_summary.png"), dpi=160)
plt.close(fig)

print(f"\nWrote {RESULTS_DIR}/chi_square_results.csv ({len(chi_df)} tests)")
print(f"Wrote {RESULTS_DIR}/continuous_results.csv ({len(cont_df)} tests)")
print(f"Wrote 6 figures to {FIG_DIR}/")

