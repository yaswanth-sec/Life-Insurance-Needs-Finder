# CyberNex Needs Finder — Full-stack hackathon MVP

## What is included
- Responsive web frontend (HTML/CSS/JavaScript)
- Python FastAPI backend
- SQLite database created automatically on first run
- Account registration/sign-in (passwords hashed with PBKDF2; demo session tokens)
- Customer profile save/load
- Illustrative life-cover needs calculator
- Product catalogue and sample recommendation endpoint
- Dataset-backed advisor directory and available sample slots
- Booking records saved to the database; slots are marked booked
- Demo customer profiles and customer goals imported from the supplied dataset
- Premium-rate, rider, ULIP fund and mortality-charge tables imported for future calculation extensions

## Run on Windows
1. Install Python 3.10 or newer from https://www.python.org/downloads/
2. Extract this ZIP.
3. Open the extracted `CyberNex_Full_Working_MVP` folder.
4. Double-click `run_windows.bat`.
5. Open http://127.0.0.1:8000 in Chrome.

## Run on macOS/Linux
```bash
cd CyberNex_Full_Working_MVP
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Then open http://127.0.0.1:8000

## API documentation
When the server is running, open http://127.0.0.1:8000/docs

## Demo flow for judges
1. Create a demo account.
2. Open Needs planner and enter age, income, expenses, dependents, loans, existing cover and savings.
3. Calculate the illustrative protection gap.
4. Click Find matching products and inspect product details.
5. Open Advisors, choose an advisor, select an available slot and confirm.
6. Open My bookings to show the saved booking.
7. Refresh the browser and sign in again to show persistence.

## Dataset and limitations
The supplied Saffron Life dataset is synthetic/fictional. Product records and sample advisors are for demonstration only. The cover estimator is a simplified educational illustration, and the match score is a transparent demo filter. The app does not provide regulated financial advice, real insurer quotes, policy issuance, payment processing, KYC, underwriting, or real advisor notifications. Demo advisor booking is stored locally in SQLite.

Before a real public launch: use authorized insurer/product data; have actuarial, legal, privacy and security specialists review calculations and disclosures; add verified identity/authentication, rate limiting, audit logs, backups, consent and data-retention controls; deploy a managed database over HTTPS; and connect authorized insurer/advisor systems.
