"""One-off: grant / revoke API access for a user via the ``access`` custom claim.

    python set_access.py you@example.com her@example.com     # grant
    python set_access.py --revoke someone@example.com        # revoke
    python set_access.py --list                              # who has it

Needs Application Default Credentials for the project - run it in Cloud Shell, or
locally after `gcloud auth application-default login`. The user must have signed
in to the app at least once (so the account exists). After granting, that user
signs out and back in so their next ID token carries the claim.
"""
import os
import sys

PROJECT = "thermoplan-benetmilian"
# End-user ADC (`gcloud auth application-default login`) has no quota project;
# identitytoolkit needs one. Set it before firebase_admin imports google.auth.
os.environ.setdefault("GOOGLE_CLOUD_QUOTA_PROJECT", PROJECT)

import firebase_admin
from firebase_admin import auth

firebase_admin.initialize_app(options={"projectId": PROJECT})


def set_access(emails, value):
    for email in emails:
        user = auth.get_user_by_email(email)
        claims = dict(user.custom_claims or {})
        if value:
            claims["access"] = True
        else:
            claims.pop("access", None)
        auth.set_custom_user_claims(user.uid, claims)
        print(f"{'granted' if value else 'revoked'}: {email}  ({user.uid})")


def list_access():
    for user in auth.list_users().iterate_all():
        if (user.custom_claims or {}).get("access"):
            print(user.email or user.uid)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    if argv[0] == "--list":
        list_access()
    elif argv[0] == "--revoke":
        set_access(argv[1:], False)
    else:
        set_access(argv, True)


if __name__ == "__main__":
    main(sys.argv[1:])
