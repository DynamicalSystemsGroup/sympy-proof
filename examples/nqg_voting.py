#!/usr/bin/env python3
"""Hidden-assumption hunt in Neural Quorum Governance (Stellar SCF).

Canonical companion to ``examples/nqg_voting.ipynb`` — same proofs,
no narrative.  Each proof seals into a deterministic bundle hash.

Target system:
    https://github.com/stellar/stellar-community-fund-contracts
    (the off-chain ``neurons/`` Rust crate)

Three sealed bundles:
    REQ-RATIO-FLOOR        active-votes ratio is at least 0.5
    REQ-TRUST-MONO         trust-graph bonus is monotone (load-bearing fire)
    REQ-TELEPORT-POS       PageRank teleport (1-d)/N is positive (helper-symbol fix)

Run::

    uv run python examples/nqg_voting.py
"""

import sympy
from sympy import Rational, Symbol

import symproof
from symproof import (
    Axiom,
    AxiomSet,
    LemmaKind,
    ProofBuilder,
    seal,
    unevaluated,
)
from symproof.library.core import max_ge_first

print(f"symproof {symproof.__version__}, sympy {sympy.__version__}")
print()

# ---------------------------------------------------------------------------
# Symbols — names mirror the Rust source where reasonable
# ---------------------------------------------------------------------------
ratio       = Symbol("ratio",     nonnegative=True)
score       = Symbol("score",     nonnegative=True)
bonus_pct   = Symbol("bonus_pct", positive=True)
d           = Symbol("d",         positive=True)
N           = Symbol("N",         positive=True, integer=True)

MIN_RATIO   = Rational(1, 2)   # ACTIVE_VOTES_MIN_RATIO in prior_voting_history.rs

# ---------------------------------------------------------------------------
# Axiom set — the design context every NQG proof in this file lives in
# ---------------------------------------------------------------------------
with unevaluated():
    nqg_axioms = AxiomSet(
        name="nqg_neurons",
        axioms=(
            Axiom(name="ratio_nonneg", expr=ratio >= 0,
                  description="N1: vote-count ratio is non-negative"),
            Axiom(name="score_nonneg", expr=score >= 0,
                  description="N2: PageRank score is non-negative "
                              "(min-max normalisation forces it into [0,1])"),
            Axiom(name="bonus_pct_pos", expr=bonus_pct > 0,
                  description="N3: HIGHLY_TRUSTED_PERCENT_BONUS > 0 "
                              "(constant 15.0 in trust_graph.rs)"),
            Axiom(name="damping_pos", expr=d > 0,
                  description="N4: PageRank damping factor strictly positive"),
            Axiom(name="damping_lt_1", expr=d < 1,
                  description="N5: PageRank damping factor strictly below 1 "
                              "(load-bearing for ergodicity)"),
            Axiom(name="N_pos", expr=N > 0,
                  description="N6: at least one node in the trust graph"),
        ),
    )

print(f"Axiom set hash: {nqg_axioms.axiom_set_hash}")
print(f"Axioms:         {len(nqg_axioms.axioms)}")
print()

# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------
score_new = score + (score / 100) * bonus_pct
teleport  = (1 - d) / N

h_mono = nqg_axioms.hypothesis(
    "trust_bonus_monotone",
    expr=sympy.Ge(score_new, score),
    description="score' = score*(1 + bonus_pct/100) >= score "
                "(highly-trusted bonus never decreases anyone's score)",
)
h_teleport = nqg_axioms.hypothesis(
    "teleport_positive",
    expr=teleport > 0,
    description="PageRank teleport (1-d)/N > 0",
)

# ---------------------------------------------------------------------------
# Proof 1 — REQ-RATIO-FLOOR (warm-up via the library)
# ---------------------------------------------------------------------------
ratio_bundle = max_ge_first(nqg_axioms, MIN_RATIO, ratio)
print(f"REQ-RATIO-FLOOR")
print(f"  hash:   {ratio_bundle.bundle_hash}")
print(f"  status: {ratio_bundle.proof_result.status.value}")
print()

# ---------------------------------------------------------------------------
# Failure-and-fix #1 — the load-bearing check fires
#
# Drop the score_nonneg axiom from the set, but keep the symbol's
# nonnegative=True constructor flag.  seal() must refuse: the lemma
# would be using an undeclared assumption.
# ---------------------------------------------------------------------------
with unevaluated():
    broken_axioms = AxiomSet(
        name="nqg_neurons_broken",
        axioms=tuple(a for a in nqg_axioms.axioms if a.name != "score_nonneg"),
    )

broken_h = broken_axioms.hypothesis(
    "trust_bonus_monotone",
    expr=sympy.Ge(score_new, score),
)
broken_script = (
    ProofBuilder(broken_axioms, broken_h.name,
                 name="trust_mono_broken",
                 claim="(broken) score' >= score with axiom set MISSING score_nonneg")
    .lemma(
        # EQUALITY using `score` — load-bearing audit flags by presence, no
        # assumptions-dict patch.  Mirrors the structure that fires in
        # examples/conviction_voting.ipynb.
        "rewrite_factored",
        LemmaKind.EQUALITY,
        expr=score + (score / 100) * bonus_pct,
        expected=score * (1 + bonus_pct / 100),
        description="score + (score/100)*bonus_pct == score*(1 + bonus_pct/100)",
    )
    .lemma(
        "diff_nonneg",
        LemmaKind.QUERY,
        expr=sympy.Q.nonnegative((score / 100) * bonus_pct),
        assumptions={"score": {"nonnegative": True}, "bonus_pct": {"positive": True}},
        depends_on=["rewrite_factored"],
        description="(score/100)*bonus_pct >= 0 if score>=0 and bonus_pct>0",
    )
    .build()
)
try:
    seal(broken_axioms, broken_h, broken_script)
    raise AssertionError("expected seal() to refuse")
except ValueError as e:
    msg = str(e)
    assert "load-bearing" in msg, f"expected load-bearing diagnostic, got: {msg}"
    print("Failure-and-fix #1 — seal() refused the broken axiom set:")
    print(f"  {msg.splitlines()[0]}")
    print()

# Now seal correctly with the full axiom set.  Same lemma chain.
mono_script = (
    ProofBuilder(nqg_axioms, h_mono.name,
                 name="trust_mono_proof",
                 claim="score' >= score via factor (1 + bonus_pct/100)")
    .lemma(
        "rewrite_factored",
        LemmaKind.EQUALITY,
        expr=score + (score / 100) * bonus_pct,
        expected=score * (1 + bonus_pct / 100),
        description="score + (score/100)*bonus_pct == score*(1 + bonus_pct/100)",
    )
    .lemma(
        "diff_nonneg",
        LemmaKind.QUERY,
        expr=sympy.Q.nonnegative((score / 100) * bonus_pct),
        assumptions={"score": {"nonnegative": True}, "bonus_pct": {"positive": True}},
        depends_on=["rewrite_factored"],
        description="(score/100)*bonus_pct >= 0 if score>=0 and bonus_pct>0",
    )
    .build()
)
mono_bundle = seal(nqg_axioms, h_mono, mono_script)
print(f"REQ-TRUST-MONO")
print(f"  hash:   {mono_bundle.bundle_hash}")
print(f"  status: {mono_bundle.proof_result.status.value}")
print()

# ---------------------------------------------------------------------------
# Failure-and-fix #2 — bounded-interval blind spot, helper-symbol fix
#
# Claim: (1-d)/N > 0 from d<1, N>0.  A naive single-shot BOOLEAN with
# Implies(And(...), (1-d)/N > 0) often fails because SymPy's refine()
# doesn't chain the strict inequality d<1 through the division.
#
# Fix: introduce e = 1-d as a positive helper; prove e/N > 0 directly.
# ---------------------------------------------------------------------------
naive_teleport_script = (
    ProofBuilder(nqg_axioms, h_teleport.name,
                 name="teleport_naive",
                 claim="(1-d)/N > 0 via single-shot BOOLEAN implication (will fail)")
    .lemma(
        "teleport_implication",
        LemmaKind.BOOLEAN,
        expr=sympy.Implies(
            sympy.And(d > 0, d < 1, N > 0),
            (1 - d) / N > 0,
        ),
        description="single-shot BOOLEAN attempt",
    )
    .build()
)
naive_failed = False
try:
    seal(nqg_axioms, h_teleport, naive_teleport_script)
except ValueError as e:
    naive_failed = True
    print("Failure-and-fix #2 — naive BOOLEAN attempt did not seal:")
    print(f"  {str(e).splitlines()[0]}")
    print()

if not naive_failed:
    # SymPy got smart enough this version. Note it but continue with helpers
    # to keep the helper-symbol pattern visible.
    print("Failure-and-fix #2 — naive BOOLEAN happened to verify in this SymPy version.")
    print("  The helper-symbol form below is still the recommended pattern.")
    print()

# Helper-symbol form
e_sym = Symbol("e", positive=True)   # e := 1 - d  (positive iff d < 1, i.e., axiom N5)
teleport_factored = e_sym / N

teleport_script = (
    ProofBuilder(nqg_axioms, h_teleport.name,
                 name="teleport_positive_proof",
                 claim="(1-d)/N > 0 via helper e = 1 - d positive (uses N5)")
    .lemma(
        "rewrite_with_helper",
        LemmaKind.EQUALITY,
        expr=(1 - d) / N,
        expected=teleport_factored.subs(e_sym, 1 - d),
        description="(1-d)/N == e/N with e := 1-d",
    )
    .lemma(
        "factored_form_positive",
        LemmaKind.QUERY,
        expr=sympy.Q.positive(teleport_factored),
        assumptions={"e": {"positive": True}, "N": {"positive": True}},
        depends_on=["rewrite_with_helper"],
        description="e/N > 0 when e>0 and N>0; e>0 *is* axiom N5",
    )
    .build()
)
teleport_bundle = seal(nqg_axioms, h_teleport, teleport_script)
print(f"REQ-TELEPORT-POS")
print(f"  hash:   {teleport_bundle.bundle_hash}")
print(f"  status: {teleport_bundle.proof_result.status.value}")
print()

# ---------------------------------------------------------------------------
# Regime visualization — what happens when N5 (d < 1) is violated
# ---------------------------------------------------------------------------
print("=" * 72)
print("  Parameter regime check: what if axiom N5 (d < 1) is violated?")
print("=" * 72)
for damp in [Rational(85, 100), Rational(99, 100), Rational(1, 1), Rational(11, 10)]:
    teleport_value = (1 - damp) / 5  # 5-node graph
    sign = ">  0" if teleport_value > 0 else ("== 0" if teleport_value == 0 else "<  0")
    flag = "ok" if teleport_value > 0 else "BREAKS PageRank"
    print(f"  d = {str(damp):<6}  (1-d)/N = {teleport_value!s:<6}  {sign}   {flag}")
print()
print("  d >= 1 collapses or inverts the teleport, which:")
print("    - removes the per-iteration baseline that makes every node reachable,")
print("    - violates the ergodicity premise of Perron-Frobenius,")
print("    - leaves the PageRank stationary distribution undefined.")
print("  Axiom N5 buys all three guarantees; only the first is proved here.")
print("  The other two require a foundation bundle that imports Perron-Frobenius.")
print()

# ---------------------------------------------------------------------------
# Requirements traceability matrix
# ---------------------------------------------------------------------------
print("=" * 72)
print("  NQG — Requirements Traceability Matrix")
print("=" * 72)
print(f"  AxiomSet hash: {nqg_axioms.axiom_set_hash}")
print()
rtm = [
    ("REQ-RATIO-FLOOR",  "active_votes_ratio >= 0.5",        ratio_bundle),
    ("REQ-TRUST-MONO",   "trust-graph bonus is monotone",    mono_bundle),
    ("REQ-TELEPORT-POS", "PageRank teleport (1-d)/N > 0",    teleport_bundle),
]
for req, claim, b in rtm:
    print(f"  {req:<18s} {claim}")
    print(f"    hash:   {b.bundle_hash}")
    print(f"    lemmas: {len(b.proof.lemmas)}")
    print()

print("Framed but not proved in this notebook (need a Perron-Frobenius foundation):")
print("  REQ-PR-IRREDUCIBLE   PageRank's transition matrix is irreducible under N5")
print("  REQ-PR-UNIQUE        Stationary distribution is unique")
print("  REQ-PR-CONVERGES     Power iteration converges to it")
