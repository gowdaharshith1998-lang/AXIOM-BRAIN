# AXIOM

**AXIOM Control** builds AXIOM: the company brain. Pulls knowledge from fragmented sources, structures it, keeps it current, and turns it into executable skills for AI agents — with signed governance on every action.

**Repo name:** AXIOM-BRAIN (GitHub repo only; not user-facing)

**Status:**
- Phase 0 ✅ (design recon; see `DESIGN.md`)
- Phase 1 ✅ (skeleton + deps + stubs + CI)
- Phase 2 ⏳ (schema + storage)
- Phases 3–15 ⏳

**Architecture:** AXIOM imports Calibra (external Python package) for Bayesian belief calibration. AXIOM's runtime governance layer (also called AXIOM) signs every agent action with hybrid Ed25519 + ML-DSA-65 (FIPS 204) and enforces a three-mode policy: ALLOW / CORRECT / DENY (plus PAUSE when uncertain).

**Hosted demo:** `https://axiomctrl.com` (placeholder until Phase 11)

**Calibra:** Integration lands in Phase 7. Phases 1–2 do not import or install Calibra.
