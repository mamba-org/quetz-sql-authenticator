from typing import List
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.hash import pbkdf2_sha256
from quetz import authorization
from quetz.authorization import SERVER_MAINTAINER, SERVER_OWNER
from quetz.deps import get_db, get_rules
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.session import Session

from .db_models import Credentials

router = APIRouter()
logger = logging.getLogger('quetz')

def _calculate_hash(value: str) -> str:
    """Calculate hash from value."""
    return pbkdf2_sha256.hash(value)


@router.get(
    "/api/sqlauth/credentials/{username}",
    tags=["sqlauth"],
)
def _get(
    username: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    """Verify that a specific user exists."""
    auth.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    # Get user from db
    db_credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if db_credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )

    return username


@router.get(
    "/api/sqlauth/credentials",
    tags=["sqlauth"],
)
def _get_all(
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> List[str]:
    """List all users."""
    auth.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    # Get users from db
    db_credentials = db.query(Credentials)

    return [c.username for c in db_credentials]


@router.post("/api/sqlauth/credentials/{username}", tags=["sqlauth"])
def _create(
    username: str,
    password: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    """Create a new user."""
    auth.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    # Check if user already exists
    db_credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if db_credentials is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User {username} already exists",
        )

    credentials = Credentials(
        username=username, password_hash=_calculate_hash(password)
    )

    db.add(credentials)
    _commit_and_tranform_errors(db)
    return username


@router.put("/api/sqlauth/credentials/{username}", tags=["sqlauth"])
def _update(
    username: str,
    password: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    """Update a user's password."""
    auth.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )
    credentials.password_hash = _calculate_hash(password)
    _commit_and_tranform_errors(db)
    return username


@router.delete("/api/sqlauth/credentials/{username}", tags=["sqlauth"])
def _delete(
    username: str,
    auth: authorization.Rules = Depends(get_rules),
    db: Session = Depends(get_db),
) -> str:
    """Delete a user."""
    auth.assert_server_roles([SERVER_OWNER, SERVER_MAINTAINER])

    credentials = (
        db.query(Credentials).filter(Credentials.username == username).one_or_none()
    )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )
    db.delete(credentials)
    _commit_and_tranform_errors(db)
    return username

def _commit_and_tranform_errors(db):
    """Commit changes to the database and transform errors to HTTP status codes."""
    try:
        db.commit()
    except Exception as e:
        logger.error(f"""
        quetz-sql-authenticator encountered the following error \
        while trying to commit changes to the database:
        {e}
        """)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"""
            An internal error occured.
            """,
        )