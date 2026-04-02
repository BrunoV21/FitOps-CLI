from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from fitops.db.base import Base


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strava_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    firstname: Mapped[str | None] = mapped_column(Text, nullable=True)
    lastname: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    sex: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    premium: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    birthday: Mapped[str | None] = mapped_column(Text, nullable=True)
    bikes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    shoes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def bikes(self) -> list[dict]:
        if self.bikes_json:
            return json.loads(self.bikes_json)
        return []

    @property
    def shoes(self) -> list[dict]:
        if self.shoes_json:
            return json.loads(self.shoes_json)
        return []

    @property
    def age(self) -> int | None:
        if not self.birthday:
            return None
        try:
            from datetime import date

            bday = date.fromisoformat(self.birthday)
            today = date.today()
            return (
                today.year
                - bday.year
                - ((today.month, today.day) < (bday.month, bday.day))
            )
        except ValueError:
            return None

    def get_gear_name(self, gear_id: str) -> str | None:
        for item in self.bikes + self.shoes:
            if item.get("id") == gear_id:
                return item.get("name")
        return None

    def get_gear_type(self, gear_id: str) -> str | None:
        for item in self.bikes:
            if item.get("id") == gear_id:
                return "bike"
        for item in self.shoes:
            if item.get("id") == gear_id:
                return "shoes"
        return None

    @classmethod
    def from_strava_data(cls, data: dict) -> Athlete:
        bikes = [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "distance_m": b.get("distance", 0),
                "primary": b.get("primary", False),
            }
            for b in data.get("bikes", [])
        ]
        shoes = [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "distance_m": s.get("distance", 0),
                "primary": s.get("primary", False),
            }
            for s in data.get("shoes", [])
        ]
        return cls(
            strava_id=data["id"],
            username=data.get("username"),
            firstname=data.get("firstname"),
            lastname=data.get("lastname"),
            city=data.get("city"),
            country=data.get("country"),
            sex=data.get("sex"),
            weight_kg=data.get("weight"),
            profile_url=data.get("profile"),
            premium=data.get("premium", False),
            birthday=data.get("birthday"),
            bikes_json=json.dumps(bikes),
            shoes_json=json.dumps(shoes),
        )

    def update_from_strava_data(self, data: dict) -> None:
        bikes = [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "distance_m": b.get("distance", 0),
                "primary": b.get("primary", False),
            }
            for b in data.get("bikes", [])
        ]
        shoes = [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "distance_m": s.get("distance", 0),
                "primary": s.get("primary", False),
            }
            for s in data.get("shoes", [])
        ]
        self.username = data.get("username", self.username)
        self.firstname = data.get("firstname", self.firstname)
        self.lastname = data.get("lastname", self.lastname)
        self.city = data.get("city", self.city)
        self.country = data.get("country", self.country)
        self.sex = data.get("sex", self.sex)
        self.weight_kg = data.get("weight", self.weight_kg)
        self.profile_url = data.get("profile", self.profile_url)
        self.premium = data.get("premium", self.premium)
        self.birthday = data.get("birthday", self.birthday)
        self.bikes_json = json.dumps(bikes)
        self.shoes_json = json.dumps(shoes)
        self.updated_at = datetime.now(UTC)
