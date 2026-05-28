# Summary

<!-- One paragraph: what does this PR change and why? Link to the relevant
issue, phase plan section, or interview-guide answer. -->

## Changes

<!-- Bullet list of the noteworthy changes. Group by layer when helpful. -->

- Backend:
- Frontend:
- Infra / CI:
- Docs:

## Tests run

- [ ] `make lint`
- [ ] `make format-check`
- [ ] `make test-backend` (≥ 65 % coverage)
- [ ] `make build-frontend`
- [ ] `make precommit`
- [ ] `make readiness-check`
- [ ] `make smoke-full` (against `make docker-up`)

## Screenshots

<!-- Drop dashboard / Grafana / Prefect screenshots here when the change is
user-visible. Keep them in ``docs/assets/screenshots/`` so the README can
reference them later. -->

## Checklist

- [ ] No real secrets, parquet datasets, or model artifacts added to git
- [ ] `.env.example` updated if a new environment variable was introduced
- [ ] Docs touched: `README.md`, `docs/architecture.md`, `docs/phase-plan.md`, or others
- [ ] Backwards-compatible (or migration plan documented)
- [ ] Port 8001 (Docker host mapping) discipline preserved

## Notes for the reviewer

<!-- Anything that needs a closer look — surprising design choices, known
limitations, follow-up tickets. -->
