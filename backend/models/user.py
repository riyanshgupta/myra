from datetime import datetime
from db.base_model import BaseModel, IntBaseModel
from sqlalchemy import DateTime
from sqlmodel import Field, Index

import uuid

class User(BaseModel, table=True):
    """ Represents a user in the system."""
    __tablename__ = "users"

    username: str = Field(index=True, unique=True, max_length=30)
    pin_hash: str

    # brute-force protection (a 6-digit PIN only has 1M combinations)
    failed_attempts: int = Field(default=0)
    locked_until: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    
class UserMetadata(IntBaseModel, table=True):
    """ Represents metadata about a user's interaction with tracks """
    __tablename__ = "user_metadata"

    # Keep foreign keys, but we can drop individual indexes if the composite cover them
    user_id: uuid.UUID = Field(foreign_key="users.id", description="ID of the user")
    track_id: int = Field(foreign_key="tracks.id", index=True, description="ID of the track")

    cnt: int = Field(default=0, description="Number of times the track has been played by the user")
    last_played: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), description="Timestamp of the last time the track was played by the user")

    # Define the composite index for filtering by user and sorting by count
    __table_args__ = (
        Index("idx_user_cnt", "user_id", "cnt"),
    )
    
    
