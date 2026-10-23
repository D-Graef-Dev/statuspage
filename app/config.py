# tomllib reads TOML
# Literal means: only the listed values are allowed
# Annotated adds extra info to a type
# BaseModel is the base class for everything Pydantic should check
import tomllib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


# Classes for the 3 check types:
# StrictModel with extra="forbid": unknown fields are not allowed. All other classes inherit from it.
# name: str means: this field must exist and must be a string.
# type: Literal["http"]: only "http" is allowed, Pydantic uses it to pick the class.
# states: a dict, the keys are strings, the values can only be "up", "maintenance" or "down".
# Field(gt=0, lt=65536): the port must be greater than 0 and less than 65536. gt = greater than, lt = less than.
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")



class HttpCheck(StrictModel):
    type: Literal["http"]
    name: str
    public: bool
    url: str
    expect_status: int



class JsonCheck(StrictModel):
    type: Literal["json"]
    name: str
    public: bool
    url: str
    field: str
    states: dict[str, Literal["up", "maintenance", "down"]]



class TlsCheck(StrictModel):
    type: Literal["tls"]
    name: str
    public: bool
    host: str
    port: int = Field(gt=0, lt=65536)
    min_days_valid: int = Field(gt=0)


# Check is HTTP, JSON or TLS. Which one is decided by the field "type".
# Config mirrors the file: title, settings and the check list.
# The names must match the names in the TOML file.
Check = Annotated[HttpCheck | JsonCheck | TlsCheck, Field(discriminator="type")]



class Settings(StrictModel):
    interval_seconds: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    failures_before_down: int = Field(gt=0)



class Config(StrictModel):
    title: str
    settings: Settings
    check: list[Check]



# with open(...) opens the file and closes it at the end, even if an error happens.
# "rb" means binary mode, tomllib needs it.
# model_validate(data) takes the dict and checks it against Config. If it is valid, it returns an object.
# If not, the error says which field is wrong.
# "-> Config" is a type hint.
def load_config(path: str) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config.model_validate(data)