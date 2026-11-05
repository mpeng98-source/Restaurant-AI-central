"""Synthetic-only credentials and stable identities shared with the HTTPS verifier."""
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAMESPACE = uuid.UUID("6d7feb9d-04b0-4dd1-b4c1-6a245f24a280")


def identity(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


class TestAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str = Field(min_length=32, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def synthetic_email(cls, value):
        if not re.fullmatch(r"[a-z0-9_.-]+@demo\.example", value):
            raise ValueError("Use synthetic @demo.example accounts only")
        return value


class DemoAccounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: TestAccount
    gm: TestAccount
    employee: TestAccount
