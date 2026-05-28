# Documentation assets

This folder holds the screenshots and GIFs the main `README.md` and
`docs/demo-script.md` reference. Image files are intentionally **not**
checked in by default — the `.gitkeep` files mark the folder structure so
git keeps it around, and you drop real screenshots in once the stack is
running locally.

## Expected files

Add these to `docs/assets/screenshots/` (use exact filenames so the
README links resolve):

| Filename | What to capture | Where |
| --- | --- | --- |
| `dashboard-home.png` | Overview page with non-zero KPI cards + recent predictions table | http://localhost:3000/ |
| `predict-page.png` | Predict page after submitting the high-risk fraud example — shows the red FRAUD badge + risk meter | http://localhost:3000/predict |
| `monitoring-page.png` | Monitoring page with at least one drift report and the drift-score timeseries chart populated | http://localhost:3000/monitoring |
| `mlflow-runs.png` | MLflow `fraud-detection` experiment with 3+ runs ranked by PR-AUC, champion alias visible | http://localhost:5000/ |
| `grafana-dashboard.png` | Grafana "FraudShield — Model Behavior" dashboard with traffic from `make load-test` | http://localhost:3001/ |
| `prefect-flow.png` | Prefect UI showing the `fraud-monitoring` + `fraud-retraining` deployments registered | http://localhost:4200/ |
| `architecture.png` | Architecture diagram (export from `architecture-diagram.md` if you want a PNG of the Mermaid) | — |

Add to `docs/assets/gifs/`:

| Filename | What to record |
| --- | --- |
| `demo.gif` | Full 90-second walkthrough — see [`docs/demo-script.md`](../demo-script.md) for the script |

## Capture tips

* Use a 1440 × 900 window with the OS dark theme so the dashboard's dark
  surfaces don't fight the browser chrome.
* Hide your cursor and your bookmark bar before capturing.
* Run `make load-test` once before recording so the dashboards have data
  to show; otherwise the charts read "No data".
* PNGs over ~500 KB will trip the `check-added-large-files` pre-commit
  hook — compress with `oxipng` or `pngquant` first.
