"""OFAC SDN screening service."""
import csv
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .matching import screen
from .sdn import load_sdn

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_accounts(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def create_app(sdn_path: str | None = None, accounts_path: str | None = None) -> FastAPI:
    sdn_path = sdn_path or os.getenv("SDN_PATH", DATA_DIR / "sdn.xml")
    accounts_path = accounts_path or os.getenv("ACCOUNTS_PATH", DATA_DIR / "accounts.csv")

    app = FastAPI(title="OFAC SDN Screening")
    entries = load_sdn(sdn_path)  # parsed once at startup

    @app.post("/screenings")
    def screen_all(matches_only: bool = False) -> list[dict]:
        results = screen(load_accounts(accounts_path), entries)
        if matches_only:
            results = [r for r in results if r["matches"]]
        return results

    @app.get("/screenings/{account_id}")
    def screen_one(account_id: str) -> dict:
        for account in load_accounts(accounts_path):
            if account["account_id"] == account_id:
                return screen([account], entries)[0]
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), port=int(os.getenv("PORT", "8000")))
