"""
Betika balance check via the real (authenticated) REST API.

Discovered by intercepting the Betika SPA network traffic:
    POST https://api.betika.com/v1/login
    body: {"mobile": "<phone>", "password": "<pw>", "remember": true, "src": "MOBILE_WEB"}
    -> 200 {"data": {"user": {"mobile": "254...", "balance": "31.13", "bonus": "8.00", ...}}, "token": "..."}

The login response already contains the live balance, so a single HTTP POST per
account is enough (no browser, no DOM scraping). "Logout" = drop the session/JWT.
This is far faster than the Playwright flow, so it scales to hundreds of accounts.
"""

import requests

LOGIN_URL = "https://api.betika.com/v1/login"
LOGOUT_URL = "https://api.betika.com/v1/logout"
WITHDRAW_URL = "https://api.betika.com/v1/withdraw"

_UA = ("Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36")


def _headers():
    return {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.betika.com",
        "Referer": "https://www.betika.com/en-ke/login?next=%2Fprofile",
        "Accept-Language": "en-KE,en;q=0.9",
    }


def check_account(phone, password, timeout=20):
    """Log in (API) and read the account balance. Returns a dict.

    Quiet by design: this function NEVER prints/logs. The caller decides what
    (and how little) to show in the terminal.
    """
    try:
        s = requests.Session()
        r = s.post(
            LOGIN_URL,
            json={"mobile": phone, "password": password,
                  "remember": True, "src": "MOBILE_WEB"},
            headers=_headers(),
            timeout=timeout,
        )
        if r.status_code == 200:
            j = r.json()
            user = (j.get("data") or {}).get("user") or {}
            # Best-effort logout so the session isn't left dangling.
            try:
                tok = j.get("token")
                if tok:
                    s.post(LOGOUT_URL, headers={**_headers(),
                          "Authorization": f"Bearer {tok}"}, timeout=10)
            except Exception:
                pass
            return {
                "phone": phone,
                "normalized": user.get("mobile"),
                "balance": float(user.get("balance") or 0),
                "bonus": float(user.get("bonus") or 0),
                "ok": True,
                "error": None,
            }
        # Non-200: wrong password / blocked / rate-limited
        msg = ""
        try:
            msg = (r.json().get("message") or r.text)[:120]
        except Exception:
            msg = r.text[:120]
        return {"phone": phone, "normalized": None, "balance": None,
                "bonus": None, "ok": False, "error": f"HTTP {r.status_code} {msg}"}
    except Exception as e:
        return {"phone": phone, "normalized": None, "balance": None,
                "bonus": None, "ok": False, "error": str(e)[:120]}


def check_all(phones, password, on_result=None, timeout=20):
    """Check a list of accounts. on_result(res_dict) is called per account.
    Returns a list of result dicts. Also quiet (no logging here)."""
    out = []
    for ph in phones:
        res = check_account(ph, password, timeout=timeout)
        out.append(res)
        if on_result:
            try:
                on_result(res)
            except Exception:
                pass
    return out


def _extract_withdraw_result(wj):
    """Return (success_bool_or_None, message). Handles a few known shapes."""
    if isinstance(wj.get("success"), dict) and wj["success"].get("message"):
        return True, str(wj["success"]["message"])
    d = wj.get("data")
    if isinstance(d, dict):
        if isinstance(d.get("success"), dict) and d["success"].get("message"):
            return True, str(d["success"]["message"])
        if d.get("message"):
            return False, str(d["message"])
    if wj.get("message"):
        return False, str(wj["message"])
    return None, None


def withdraw_account(phone, password, amount, timeout=20):
    """Log in (API), then request a withdrawal of `amount` KES to the account's
    registered MPESA number via Betika's /v1/withdraw endpoint.

    This moves REAL money. The function itself is quiet (no logging); the caller
    decides what to print. Returns a dict with at least:
        ok, withdrawn, message/error, normalized, phone
    """
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"phone": phone, "normalized": None, "ok": False,
                "error": "bad amount", "withdrawn": 0.0}
    try:
        s = requests.Session()
        r = s.post(
            LOGIN_URL,
            json={"mobile": phone, "password": password,
                  "remember": True, "src": "MOBILE_WEB"},
            headers=_headers(),
            timeout=timeout,
        )
        if r.status_code != 200:
            return {"phone": phone, "normalized": None, "ok": False,
                    "error": f"login HTTP {r.status_code}", "withdrawn": 0.0}
        j = r.json()
        user = (j.get("data") or {}).get("user") or {}
        balance = float(user.get("balance") or 0)
        tok = j.get("token")
        label = user.get("mobile") or phone
        if balance < amount:
            return {"phone": phone, "normalized": label, "ok": False,
                    "error": f"insufficient (bal {balance:,.2f})", "withdrawn": 0.0}
        headers = {**_headers(), "Authorization": f"Bearer {tok}"}
        wr = s.post(
            WITHDRAW_URL,
            json={"amount": amount, "token": tok,
                  "isCashia": True, "app_name": "MOBILE_WEB"},
            headers=headers,
            timeout=timeout,
        )
        try:
            wj = wr.json()
        except Exception:
            wj = {}
        ok, msg = _extract_withdraw_result(wj)
        if ok is True:
            return {"phone": phone, "normalized": label, "ok": True,
                    "withdrawn": amount, "message": msg or "withdrawal initiated"}
        if ok is False:
            return {"phone": phone, "normalized": label, "ok": False,
                    "error": msg or f"HTTP {wr.status_code}", "withdrawn": 0.0}
        # unknown shape: trust HTTP status
        if wr.status_code == 200:
            return {"phone": phone, "normalized": label, "ok": True,
                    "withdrawn": amount, "message": msg or "withdrawal initiated"}
        return {"phone": phone, "normalized": label, "ok": False,
                "error": msg or f"HTTP {wr.status_code}", "withdrawn": 0.0}
    except Exception as e:
        return {"phone": phone, "normalized": None, "ok": False,
                "error": str(e)[:160], "withdrawn": 0.0}
