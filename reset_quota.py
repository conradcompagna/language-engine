import argparse
import sqlite3

parser = argparse.ArgumentParser(description="Reset lookup quota for one explicitly selected account.")
parser.add_argument("database", help="Path to the account database")
parser.add_argument("email", help="Account email to reset")
args = parser.parse_args()
with sqlite3.connect(args.database) as connection:
    connection.execute(
        "UPDATE lookup_quotas SET count=0 WHERE user_id=(SELECT id FROM users WHERE email=?)",
        (args.email,),
    )
print("done")
