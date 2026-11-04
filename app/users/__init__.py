"""משתמשים — טבלה אחת לכל אדם בבית."""
from app.users.emails import clean_google_email
from app.users.flags import USER_FLAGS
from app.users.identity import (
    ACCESS_EMAIL_HEADER,
    access_email_from_headers,
    current_access_user,
    user_for_access_headers,
)
from app.users.table import (
    LEGACY_PEOPLE_TABLE,
    USERS_BACKUP_TABLE,
    USERS_TABLE,
    resolve_people_table,
)

__all__ = [
    "ACCESS_EMAIL_HEADER",
    "LEGACY_PEOPLE_TABLE",
    "USERS_BACKUP_TABLE",
    "USERS_TABLE",
    "USER_FLAGS",
    "access_email_from_headers",
    "clean_google_email",
    "current_access_user",
    "resolve_people_table",
    "user_for_access_headers",
]
