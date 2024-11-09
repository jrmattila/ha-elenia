from typing import Union, Optional, Literal, TypedDict
from dataclasses import dataclass, field


class Measurement(TypedDict):
    a: int  # 99220, phases combined
    a1: int  # 15535, phase 1
    a1_: int  # 0,
    a2: int  # 49020, phase 2
    a2_: int  # 0,
    a3: int  # 34664, phase 3
    a3_: int  # 0,
    a_: int  # 0,
    dt: str  # "2024-10-26T11:45:00" slot 11:40-11.45, time in utc
    gsrn: int  # 13 digits string,
    modified: str  # "2024-10-26T16:42:20",
    quality: int  # 0,
    r: int  # 1032,
    r1: int  # null,
    r1_: int  # null,
    r2: int  # null,
    r2_: int  # null,
    r3: int  # null,
    r3_: int  # null,
    r_: int  # null,
    serialnumber: str  # 16-digits string,
    source: str  # "ai"


Measurements = list[Measurement]


@dataclass
class RelayCalendar:
    control_type: Literal["calendar"]
    subtype: Literal["hours"]
    relayname_user: str
    hours_on: list[int] = field(default_factory=list)

    def __post_init__(self):
        if len(self.hours_on) != 24:
            raise ValueError("hours_on must be a list of exactly 24 integers.")
        if any(hour not in (0, 1) for hour in self.hours_on):
            raise ValueError("Each element in hours_on must be either 0 or 1.")


@dataclass
class RelayDynamic:
    control_type: Literal["dynamic"]
    subtype: Literal["market"]
    relayname_user: str
    number_of_hours: int


RelayType = Union[RelayCalendar, RelayDynamic]


@dataclass
class RelayData:
    #   "created_utc": "2024-10-24T09:08:53",
    #   "gsrn": "64345345",
    #   "message_id": "SSD6-SDF9807D",
    #   "modified_utc": "2024-10-24T09:08:00",
    gsrn: str
    serialnumber: str
    relay1: Optional[RelayType]
    relay2: Optional[RelayType]


def parse_relay(relay_data: dict) -> Optional[RelayType]:
    if not relay_data:
        return None

    if relay_data["control_type"] == "calendar":
        return RelayCalendar(
            control_type=relay_data["control_type"],
            subtype=relay_data["subtype"],
            relayname_user=relay_data["relayname_user"],
            hours_on=relay_data["hours_on"],
        )
    elif relay_data["control_type"] == "dynamic":
        return RelayDynamic(
            control_type=relay_data["control_type"],
            subtype=relay_data["subtype"],
            relayname_user=relay_data["relayname_user"],
            number_of_hours=relay_data["number_of_hours"],
        )
    else:
        raise ValueError("Unknown relay control type")
