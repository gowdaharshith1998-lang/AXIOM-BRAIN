# AXIOM

The company brain. Pulls knowledge from fragmented sources, structures it, keeps it current, and turns it into executable skills for AI agents — with signed governance on every action and Bayesian confidence calibration on every fact.

**Status:** Phase 0 — design recon complete. See `DESIGN.md`.

**Architecture:** AXIOM imports Calibra (external Python package) for Bayesian belief calibration. AXIOM's runtime governance layer (also called AXIOM) signs every agent action with hybrid Ed25519 + ML-DSA-65 (FIPS 204) and enforces a three-mode policy: ALLOW / CORRECT / DENY (plus PAUSE when uncertain).

**Hosted demo:** TBD (Phase 11)
