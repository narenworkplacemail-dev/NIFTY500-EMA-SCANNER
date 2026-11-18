# NIFTY 500 Daily EMA 20/50 Scanner

A separate, simple Streamlit app for GitHub and Streamlit Community Cloud.

## Scan rule

- Current NIFTY 500 constituent list, loaded from the NSE CSV.
- Daily Yahoo Finance candles (`interval="1d"`).
- Matches only stocks whose latest close is above EMA 20 and EMA 20 is above EMA 50.
- Shows the most recent daily EMA 20 crossover above EMA 50 found in the past year.

The app downloads tickers in batches and caches a scan for 15 minutes. Matches are sorted by crossover date, newest first, with stocks having no bullish crossover in the one-year lookback at the bottom. It includes a CSV download button. Yahoo Finance or the NSE constituent file may occasionally be unavailable; data issues are counted in the app.

## Deploy online

Upload `app.py` and `requirements.txt` to the top level of a GitHub repository. In Streamlit Community Cloud, create an app from that repository, set the branch to `main`, and set the main file path to `app.py`. The repository can be private if Streamlit is authorized to access it.

## Run locally (optional)

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
