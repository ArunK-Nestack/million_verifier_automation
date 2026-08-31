# MillionVerifier Verification Agent — Continuous Folder Automation

Automated continuous watcher agent to process email files from an **Input Folder**, clean and deduplicate them, verify them via the **MillionVerifier Bulk API**, and categorize the results into **Good**, **Bad**, and **Risky** folders inside a **Destination Folder**.


---

> **Official Documentation:** For the complete technical guide, architectural diagrams, API reference, and classification rules, see [DOCUMENTATION.md](file:///c:/Users/test/Desktop/projects/millionverifier_agent_step1/DOCUMENTATION.md).

---

## Configured Google Drive Paths

- **Input Folder:** `G:\My Drive\million automation\million input`
- **Output Folder:** `G:\My Drive\million automation\million output`

---

## Automated Continuous Workflow

When the agent is active (`python -m app.main` or `python -m app.main watch`):

1. **Continuous Queue Detection:** Monitors `million input` folder. Whenever a file is detected, it immediately picks it up.
2. **Clean & Prepare:** Normalizes emails, removes syntax errors/blanks, and removes duplicates.
3. **Upload to MillionVerifier:** Uploads cleaned list to Bulk API.
4. **Verification Polling (50-60s):** Checks job progress every 60 seconds with live console feedback until `status = finished`.
5. **Download & Categorization:** Downloads complete results and categorizes directly into `good`, `bad`, and `risky` folders:
   - `million output/good/<file_name> - good - <good> good - <total> total.csv`
   - `million output/bad/<file_name> - bad.csv`
   - `million output/risky/<file_name> - risky.csv`
   - `million output/summaries/<file_name>_run_summary.json`
6. **Auto-Deletion of Input File:** Once verified and saved in `million output`, the source file is automatically deleted from `million input`.
7. **Immediate Next File:** Checks for the next file in the input folder immediately and begins processing without delay.

---

## How to Run

### Start Continuous Automation (Recommended)
```powershell
python -m app.main
```
*(or `python -m app.main watch`)*

### Run Single Batch (Once)
```powershell
python -m app.main process --once
```

### Check Settings & Paths
```powershell
python -m app.main config
```

### Offline Column Restore / Re-merge (No API credits used)
If you place original CSV files into the input folder to restore columns from previous runs:
```powershell
python restore_columns.py
```
*(Or specify custom folders with `python restore_columns.py -i "path/to/inputs" -o "path/to/outputs"`)*

### Clean Local Cache (Free Up Disk Space)
To manually purge temporary files in `prepared/` and `results/`:
```powershell
python clean_cache.py
```
*(Or with skip-prompt: `python clean_cache.py -y` or `python -m app.main clean-cache`)*
