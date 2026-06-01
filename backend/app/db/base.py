from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from ..storage_config import POSTGRES_SCHEMA

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_metadata_kwargs = {"naming_convention": NAMING_CONVENTION}
if POSTGRES_SCHEMA and POSTGRES_SCHEMA != "public":
    _metadata_kwargs["schema"] = POSTGRES_SCHEMA


class Base(DeclarativeBase):
    metadata = MetaData(**_metadata_kwargs)

