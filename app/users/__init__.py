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
from app.users.telegram import (
    DIGEST_REQUIRES_TELEGRAM,
    unlink_telegram_confirm,
)

__all__ = [
    "ACCESS_EMAIL_HEADER",
    "DIGEST_REQUIRES_TELEGRAM",
    "LEGACY_PEOPLE_TABLE",
    "USERS_BACKUP_TABLE",
    "USERS_TABLE",
    "USER_FLAGS",
    "access_email_from_headers",
    "clean_google_email",
    "current_access_user",
    "resolve_people_table",
    "unlink_telegram_confirm",
    "user_for_access_headers",
]
