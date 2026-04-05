from __future__ import annotations

import traceback
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from src.config import settings
from src.data_fetchers import FetchError
from src.pipeline import load_dashboard_payload, run_pipeline
import json

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = settings.secret_key


def _load_or_initialize() -> dict:
    try:
        return load_dashboard_payload()
    except FileNotFoundError:
        if settings.auto_refresh_if_missing:
            run_pipeline()
            return load_dashboard_payload()
        return {
            "generated_at": None,
            "company": {"name": settings.company_name, "symbol": settings.company_symbol},
            "series": [],
            "transactions": [],
            "quick_summary": ["目前尚未產生資料檔。請先設定 API key，然後執行 python refresh_data.py。"],
            "latest": {},
            "date_range": {},
            "methodology": {"notes": []},
        }


@app.route("/")
def index() -> str:
    return render_template("index.html", company=settings.company_name, symbol=settings.company_symbol)


@app.route("/api/data")
def api_data():
    payload = _load_or_initialize()
    return Response(json.dumps(payload, ensure_ascii=False, allow_nan=False), mimetype="application/json")


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    auth_token = request.headers.get("X-Refresh-Token") or request.args.get("token")
    if auth_token != settings.refresh_token:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    try:
        result = run_pipeline()
        return jsonify(
            {
                "ok": True,
                "generated_at": result.generated_at,
                "output_path": str(result.output_path),
                "row_count": result.row_count,
            }
        )
    except Exception as exc:  # pragma: no cover - helpful in deployment
        return jsonify({"ok": False, "error": str(exc), "trace": traceback.format_exc()}), 500


@app.route("/health")
def health():
    path_exists = Path(settings.dashboard_path).exists()
    return jsonify({"ok": True, "data_file_exists": path_exists, "data_path": str(settings.dashboard_path)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
