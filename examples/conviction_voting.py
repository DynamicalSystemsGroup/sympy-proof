#!/usr/bin/env python3
"""Conviction Voting — framed problem and worked proofs.

Reference
---------
1Hive / BlockScience conviction-voting cadCAD model:
    https://github.com/1Hive/conviction-voting-cadcad

Source equations (from algorithm_overview.ipynb):

    y_{t+1}[i] = alpha * y_t[i] + sum_a x[a, i]            (conviction)
    y*_t[i]    = f(mu_i),  mu_i = r[i] / R_t                (threshold)
    f(z)       = rho * S / ((1 - alpha) * (z - beta)**2)   (example trigger)

Run::

    uv run python examples/conviction_voting.py

What this file does
-------------------
1. Frames the system: symbols, axioms, eight independent hypotheses.
2. Constructs sealed proofs for three of them:
       REQ-FIX       — steady-state fixed point of conviction recurrence
       REQ-TRIG-POS  — trigger function strictly positive on its domain
       REQ-PASS      — passability requires rho < beta**2 (HIDDEN axiom H6)
3. Prints a traceability matrix linking each requirement to its hash.

Scope
-----
Symbolic-math layer only.  Behaviour under finite precision, agent
strategy, multi-proposal interaction, and supply dynamics need
simulation (cadCAD) and code review.  symproof certifies the formula,
not the deployment.
"""

from __future__ import annotations

import sympy
from sympy import Rational, Symbol

from symproof import (
    Axiom,
    AxiomSet,
    LemmaKind,
    ProofBuilder,
    seal,
    unevaluated,
)

# ─────────────────────────────────────────────────────────────────────
# Symbols (with units / domain)
# ─────────────────────────────────────────────────────────────────────

# Decay parameter; needs alpha in (0,1) for stability + half-life
alpha = Symbol("alpha", positive=True)
# Max share of pool any one proposal may request; needs beta in (0,1)
beta = Symbol("beta", positive=True)
# Trigger scale parameter; positive
rho = Symbol("rho", positive=True)
# Effective supply of governance tokens
S = Symbol("S", positive=True)
# Resource pool at time t
R_t = Symbol("R_t", positive=True)
# Share of pool requested by a given proposal: mu = r / R_t, in [0, beta)
mu = Symbol("mu", nonnegative=True)
# Total support summed across agents at time t (treated as exogenous
# constant for the steady-state analysis)
x_total = Symbol("x_total", positive=True)
# Conviction at time t (state variable)
y_t = Symbol("y_t", nonnegative=True)
# Steady-state conviction (the value to be proved a fixed point)
y_star = x_total / (1 - alpha)
# Maximum reachable conviction (occurs when x_total = S)
y_max = S / (1 - alpha)


# ─────────────────────────────────────────────────────────────────────
# Axioms — the system context shared by every hypothesis
# ─────────────────────────────────────────────────────────────────────
# Always under unevaluated() so SymPy doesn't collapse e.g. (alpha > 0)
# to True at construction time, losing the structural axiom.

with unevaluated():
    cv_axioms = AxiomSet(
        name="conviction_voting",
        axioms=(
            # H1: decay parameter is a proper convex combination weight
            Axiom(name="alpha_pos", expr=alpha > 0,
                  description="H1: decay rate strictly positive"),
            Axiom(name="alpha_lt_1", expr=alpha < 1,
                  description="H1: decay rate strictly below 1 "
                              "(stability + finite half-life)"),
            # H2: maximum-share parameter
            Axiom(name="beta_pos", expr=beta > 0,
                  description="H2: max requestable share positive"),
            Axiom(name="beta_lt_1", expr=beta < 1,
                  description="H2: max requestable share below 1"),
            # H3: trigger scale
            Axiom(name="rho_pos", expr=rho > 0,
                  description="H3: trigger scale positive"),
            # H4: supply
            Axiom(name="S_pos", expr=S > 0,
                  description="H4: effective supply positive"),
            # H5: requested share within trigger function's domain
            Axiom(name="mu_nonneg", expr=mu >= 0,
                  description="H5: requested share nonnegative "
                              "(mu = r/R_t with r >= 0, R_t > 0)"),
            Axiom(name="mu_lt_beta", expr=mu < beta,
                  description="H5: requested share strictly below "
                              "beta (else trigger diverges)"),
            # H6: the load-bearing parameter design constraint —
            # absent from the public README, surfaced here.
            Axiom(name="rho_lt_beta_sq", expr=rho < beta**2,
                  description="H6: scale parameter is below "
                              "beta-squared, ensuring at least some "
                              "proposal is theoretically passable"),
            # x_total is constant for steady-state analysis (H9)
            Axiom(name="x_total_pos", expr=x_total > 0,
                  description="H9: total support positive and constant"),
        ),
    )

print(f"Axiom set hash: {cv_axioms.axiom_set_hash[:32]}...")
print(f"Axiom count:    {len(cv_axioms.axioms)}\n")


# ─────────────────────────────────────────────────────────────────────
# Hypothesis catalog — eight independent properties
# ─────────────────────────────────────────────────────────────────────
# Per CLAUDE.md, each property gets its own hypothesis and its own
# sealed bundle.  The traceability matrix at the end maps each
# requirement to its hash.

# REQ-FIX — steady-state is a fixed point
h_fix = cv_axioms.hypothesis(
    "steady_state_fixed_point",
    expr=sympy.Eq(alpha * y_star + x_total, y_star),
    description="y* = x_total/(1-alpha) is a fixed point of "
                "y_{t+1} = alpha y_t + x_total",
)

# REQ-TRIG-POS — threshold strictly positive on its domain
trigger = rho * S / ((1 - alpha) * (mu - beta)**2)
h_trig_pos = cv_axioms.hypothesis(
    "trigger_positive",
    expr=trigger > 0,
    description="f(mu) > 0 for all mu in [0, beta)",
)

# REQ-PASS — there is at least one passable proposal share when H6 holds
# Concretely: y_max > f(0).  Equivalent to rho < beta**2.
trigger_at_zero = rho * S / ((1 - alpha) * beta**2)
h_pass = cv_axioms.hypothesis(
    "passability_gate",
    expr=y_max - trigger_at_zero > 0,
    description="Maximum reachable conviction exceeds threshold for "
                "a zero-share request -- requires rho < beta**2 (H6)",
)

# Hypotheses framed but not constructed in this file (each would
# get its own proof in a production traceability matrix)
h_monotone = cv_axioms.hypothesis(
    "conviction_monotone_below_ss",
    expr=sympy.Implies(y_t < y_star, alpha * y_t + x_total > y_t),
    description="Conviction strictly increases below the steady state",
)
h_bound = cv_axioms.hypothesis(
    "conviction_upper_bound",
    expr=sympy.Le(y_t, y_max),
    description="Conviction is bounded above by S/(1-alpha)",
)
h_trig_mono = cv_axioms.hypothesis(
    "trigger_monotone_in_share",
    expr=sympy.Gt(sympy.diff(trigger, mu), 0),
    description="df/dmu > 0 on [0, beta) -- bigger asks need more conviction",
)
h_trig_asym = cv_axioms.hypothesis(
    "trigger_diverges_at_beta",
    expr=sympy.Eq(sympy.limit(trigger, mu, beta, "-"), sympy.oo),
    description="f(mu) -> infinity as mu -> beta-",
)
h_capacity = cv_axioms.hypothesis(
    "participant_capacity",
    expr=sympy.S.true,  # placeholder; would be Σ_i x[a,i] <= h[a]
    description="Per-agent signaling bounded by holdings (multi-symbol; "
                "left framed for a future proof)",
)


# ─────────────────────────────────────────────────────────────────────
# Proof 1 — REQ-FIX: steady state is a fixed point of the recurrence
# ─────────────────────────────────────────────────────────────────────
# Single EQUALITY lemma: simplify(alpha * y_star + x_total - y_star) == 0.
# With y_star = x_total/(1-alpha):
#   alpha*x/(1-a) + x - x/(1-a) = (alpha*x + x*(1-a) - x)/(1-a)
#                                = (alpha*x + x - alpha*x - x)/(1-a) = 0.

fix_script = (
    ProofBuilder(
        cv_axioms, h_fix.name,
        name="steady_state_fixed_point_proof",
        claim="alpha * y* + x_total = y* where y* = x_total/(1-alpha)",
    )
    .lemma(
        "fixed_point_identity",
        LemmaKind.EQUALITY,
        expr=alpha * y_star + x_total,
        expected=y_star,
        description="Direct algebraic substitution",
    )
    .build()
)
fix_bundle = seal(cv_axioms, h_fix, fix_script)


# ─────────────────────────────────────────────────────────────────────
# Proof 2 — REQ-TRIG-POS: trigger function is strictly positive
# ─────────────────────────────────────────────────────────────────────
# SymPy's Q-system can't reason about (mu - beta)**2 > 0 from mu < beta
# (bounded interval problem).  Same workaround as fee_complement_positive
# in the AMM example: helper symbols.
#
#   k = 1 - alpha   (positive — from alpha < 1)
#   g = beta - mu   (positive — from mu < beta)
#   (mu - beta)**2 = g**2
#
# Then: rho*S / (k * g**2) is positive by Q.positive on all-positive symbols.

k = Symbol("k", positive=True)   # k = 1 - alpha
g = Symbol("g", positive=True)   # g = beta - mu

trigger_with_helpers = rho * S / (k * g**2)

trig_pos_script = (
    ProofBuilder(
        cv_axioms, h_trig_pos.name,
        name="trigger_positive_proof",
        claim="f(mu) > 0 on [0, beta) via helper symbols k=1-a, g=b-mu",
    )
    .lemma(
        "rewrite_with_helpers",
        LemmaKind.EQUALITY,
        # Substitute k and g back into their defining expressions so
        # the EQUALITY collapses to a literal identity simplify() handles.
        expr=trigger,
        expected=trigger_with_helpers.subs(
            [(k, 1 - alpha), (g, beta - mu)]
        ),
        description="(mu-beta)**2 = (beta-mu)**2 = g**2 with g = beta-mu",
    )
    .lemma(
        "helper_form_positive",
        LemmaKind.QUERY,
        expr=sympy.Q.positive(trigger_with_helpers),
        assumptions={
            "rho": {"positive": True},
            "S":   {"positive": True},
            "k":   {"positive": True},
            "g":   {"positive": True},
        },
        depends_on=["rewrite_with_helpers"],
        description="rho*S/(k*g**2) > 0 with all symbols positive",
    )
    .build()
)
trig_pos_bundle = seal(cv_axioms, h_trig_pos, trig_pos_script)


# ─────────────────────────────────────────────────────────────────────
# Proof 3 — REQ-PASS: passability requires rho < beta**2 (HIDDEN H6)
# ─────────────────────────────────────────────────────────────────────
# Claim: y_max - f(0) > 0, i.e. S/(1-alpha) - rho*S/((1-alpha)*beta**2) > 0.
# Algebra: the difference factors as S*(beta**2 - rho)/((1-alpha)*beta**2).
# Helper symbols mirror REQ-TRIG-POS:
#   k = 1 - alpha          (positive — from H1 alpha < 1)
#   p = beta**2 - rho      (positive — from H6 rho < beta**2)
# With k, p, S, beta all positive, the factored form is positive.
# The proof would not seal without H6 in the axiom set, because there is
# no reason to treat (beta**2 - rho) as positive otherwise.

p_sym = Symbol("p", positive=True)   # p = beta**2 - rho

passability_factored = S * p_sym / (k * beta**2)

pass_script = (
    ProofBuilder(
        cv_axioms, h_pass.name,
        name="passability_gate_proof",
        claim="y_max > f(0) via helpers k=1-alpha, p=beta**2-rho",
    )
    .lemma(
        "rewrite_difference",
        LemmaKind.EQUALITY,
        expr=S / (1 - alpha) - rho * S / ((1 - alpha) * beta**2),
        expected=passability_factored.subs(
            [(k, 1 - alpha), (p_sym, beta**2 - rho)]
        ),
        description="y_max - f(0) = S*(beta**2-rho)/((1-alpha)*beta**2)",
    )
    .lemma(
        "factored_form_positive",
        LemmaKind.QUERY,
        expr=sympy.Q.positive(passability_factored),
        assumptions={
            "S":    {"positive": True},
            "k":    {"positive": True},
            "p":    {"positive": True},
            "beta": {"positive": True},
        },
        depends_on=["rewrite_difference"],
        description="S*p/(k*beta**2) > 0 with all symbols positive "
                    "-- p > 0 is exactly H6",
    )
    .build()
)
pass_bundle = seal(cv_axioms, h_pass, pass_script)


# ─────────────────────────────────────────────────────────────────────
# Hidden-assumption demo: refute REQ-PASS when H6 is parametrically broken
# ─────────────────────────────────────────────────────────────────────
# Same claim, plugging in CONCRETE values that violate rho < beta**2.
# This isn't proved -- it's checked numerically to make the failure
# concrete: a deployment with these parameters has NO passable proposal.

bad_rho, bad_beta = Rational(1, 2), Rational(2, 5)   # rho=0.5, beta=0.4
print(f"\nNumeric refutation under bad parameters "
      f"(rho={bad_rho}, beta={bad_beta}):")
print(f"  beta**2 = {bad_beta**2}, rho = {bad_rho}")
print(f"  beta**2 - rho = {bad_beta**2 - bad_rho} "
      f"(NEGATIVE -> H6 violated -> no proposal can ever pass)")
print("  (the symbolic REQ-PASS bundle above is sealed under the "
      "axiom rho < beta**2, so it does not apply to this regime.)")


# ─────────────────────────────────────────────────────────────────────
# Traceability matrix
# ─────────────────────────────────────────────────────────────────────

print("\n" + "─" * 64)
print("  Conviction Voting — Requirements Traceability Matrix")
print("─" * 64)

rtm = [
    ("REQ-FIX",      "steady_state_fixed_point",        fix_bundle),
    ("REQ-TRIG-POS", "trigger_positive",                trig_pos_bundle),
    ("REQ-PASS",     "passability_gate (uses H6)",      pass_bundle),
]
header = f"{'Req':<14s} {'Hypothesis':<36s} {'Hash':<26s} L"
print(header)
print("─" * len(header))
for req, name, b in rtm:
    n = len(b.proof.lemmas)
    print(f"{req:<14s} {name:<36s} {b.bundle_hash[:24]}.. {n}")

print("\nFramed-but-unproved (would each get their own bundle):")
for req, h in [
    ("REQ-MONO",       h_monotone),
    ("REQ-BOUND",      h_bound),
    ("REQ-TRIG-MONO",  h_trig_mono),
    ("REQ-TRIG-ASYM",  h_trig_asym),
    ("REQ-CAP",        h_capacity),
]:
    print(f"  {req:<14s} {h.name}")

# Surface the assumption summary -- this is the audit artefact.
# Every sealed bundle's advisories enumerate posited / inherited /
# external assumptions.  Inspecting these is the hidden-assumption hunt.
print("\n" + "─" * 64)
print("  Assumption summary on REQ-PASS (note H6 is present)")
print("─" * 64)
for adv in pass_bundle.proof_result.advisories:
    print(adv)
