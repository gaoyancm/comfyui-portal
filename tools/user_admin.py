import argparse
import csv
import hashlib
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(__file__))
CSV_PATH = os.path.join(ROOT, os.environ.get("USERS_CSV", "users.csv"))


def load_rows():
    if not os.path.isfile(CSV_PATH):
        return []
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r)


def save_rows(rows):
    fields = ["username", "password_hash", "expire_at", "role", "active"]
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            out = {k: str(row.get(k, "") or "") for k in fields}
            if out.get("role", "").strip() == "":
                out["role"] = "user"
            if out.get("active", "").strip() == "":
                out["active"] = "true"
            w.writerow(out)
    os.replace(tmp, CSV_PATH)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def cmd_add(args):
    rows = load_rows()
    if any(r.get("username") == args.username for r in rows):
        raise SystemExit("user already exists")
    rows.append({
        "username": args.username,
        "password_hash": sha256_hex(args.password),
        "expire_at": args.expire or "2099-12-31",
        "role": args.role,
        "active": "true",
    })
    save_rows(rows)
    print("OK: added", args.username)


def cmd_set_password(args):
    rows = load_rows()
    found = False
    for r in rows:
        if r.get("username") == args.username:
            r["password_hash"] = sha256_hex(args.password)
            found = True
    if not found:
        raise SystemExit("user not found")
    save_rows(rows)
    print("OK: password updated")


def cmd_set_expire(args):
    rows = load_rows()
    found = False
    for r in rows:
        if r.get("username") == args.username:
            r["expire_at"] = args.date
            found = True
    if not found:
        raise SystemExit("user not found")
    save_rows(rows)
    print("OK: expire date updated")


def cmd_activate(args, active: bool):
    rows = load_rows()
    found = False
    for r in rows:
        if r.get("username") == args.username:
            r["active"] = "true" if active else "false"
            found = True
    if not found:
        raise SystemExit("user not found")
    save_rows(rows)
    print("OK: active=", active)


def cmd_list(args):
    rows = load_rows()
    for r in rows:
        print(r.get("username"), r.get("expire_at"), r.get("role", "user"), r.get("active", "true"))


def main():
    p = argparse.ArgumentParser(description="Manage users.csv")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add-user")
    a.add_argument("username")
    a.add_argument("--password", required=True)
    a.add_argument("--expire", dest="expire")
    a.add_argument("--role", default="user", choices=["user", "admin"])
    a.set_defaults(func=cmd_add)

    sp = sub.add_parser("set-password")
    sp.add_argument("username")
    sp.add_argument("--password", required=True)
    sp.set_defaults(func=cmd_set_password)

    se = sub.add_parser("set-expire")
    se.add_argument("username")
    se.add_argument("--date", required=True, help="YYYY-MM-DD")
    se.set_defaults(func=cmd_set_expire)

    da = sub.add_parser("deactivate")
    da.add_argument("username")
    da.set_defaults(func=lambda args: cmd_activate(args, False))

    ac = sub.add_parser("activate")
    ac.add_argument("username")
    ac.set_defaults(func=lambda args: cmd_activate(args, True))

    ls = sub.add_parser("list")
    ls.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

