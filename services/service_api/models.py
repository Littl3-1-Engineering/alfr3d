"""Pydantic models for ALFR3D API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    type: str
    email: Optional[str] = ""
    about_me: Optional[str] = ""


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    about_me: Optional[str] = None
    type: Optional[str] = None


class DeviceCreate(BaseModel):
    name: str
    type: str
    ip: Optional[str] = "10.0.0.125"
    mac: Optional[str] = "00:00:00:00:00:00"
    user: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    mac: Optional[str] = None
    type: Optional[str] = None
    user: Optional[str] = None
    position: Optional[Dict[str, float]] = None


class QuipCreate(BaseModel):
    type: str
    quips: str
    category: Optional[str] = "custom"


class QuipUpdate(BaseModel):
    type: str
    quips: str
    category: Optional[str] = "custom"


class EnvironmentUpdate(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    ip: Optional[str] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    description: Optional[str] = None
    pressure: Optional[float] = None
    humidity: Optional[float] = None
    subjective_feel: Optional[str] = None


class RoutineCreate(BaseModel):
    name: str
    time: str = "08:00:00"
    enabled: int = 1
    recurrence: str = "daily"
    actions: List[Dict[str, Any]] = []
    triggers: List[Dict[str, Any]] = []
    conditions: List[Dict[str, Any]] = []


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    time: Optional[str] = None
    enabled: Optional[int] = None
    recurrence: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    triggers: Optional[List[Dict[str, Any]]] = None
    conditions: Optional[List[Dict[str, Any]]] = None


class PersonalityUpdate(BaseModel):
    sarcasm: Optional[float] = 0.5
    formality: Optional[float] = 0.5
    warmth: Optional[float] = 0.5
    patience: Optional[float] = 1.0
    linguistic_style: Optional[str] = ""
    forbidden_words: Optional[str] = ""
    verbal_tics: Optional[str] = ""
    name: Optional[str] = "Custom"


class ContextUpdate(BaseModel):
    repeat_count: Optional[int] = None
    hour: Optional[int] = None
    weather: Optional[str] = None
    mood: Optional[str] = None
    last_error_count: Optional[int] = None


class LLMConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    usage_limit: Optional[int] = None
    model: Optional[str] = None


class HAControl(BaseModel):
    command: str
    params: Dict[str, Any] = {}


class HAConfig(BaseModel):
    ha_url: str
    ha_token: str


class STControl(BaseModel):
    command: str
    capability: str = "switch"
    args: List[Any] = []


class STConfig(BaseModel):
    st_pat: str


class IoTProvider(BaseModel):
    provider: str


class LinkDevice(BaseModel):
    device_id: int | None = None


class IOTDeviceControl(BaseModel):
    command: str
    params: Dict[str, Any] = {}


class PresetApply(BaseModel):
    preset: str
