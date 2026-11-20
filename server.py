from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from data_processor import (
    FLOOR_TYPE_MAP,
    MATERIAL_MAP,
    REPAIR_MAP,
    ZONE_MAP,
    DataProcessor,
)
from house_info_service import HouseInfoService
from model import ValuationModel

app = FastAPI(title="Оценка недвижимости — Нижний Новгород")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATA_PATH = "data/apartments.xlsx"
dp = DataProcessor(DATA_PATH)
model = ValuationModel(dp)
house_service = HouseInfoService(
    {
        "dataset_path": DATA_PATH,
        "yandex_api_key": None,
        "use_cache": True,
        "cache_path": "data/house_info_cache.db",
        "cache_ttl_hours": 24,
    },
    df=dp.df,
)


class AddressRequest(BaseModel):
    address: str = Field(min_length=3)


class ValuationRequest(BaseModel):
    address: Optional[str] = None
    area: float
    rooms: int
    floor: int
    total_floors: Optional[int] = None
    floor_type: str
    repair: str
    material: Optional[str] = None
    balcony: int
    split_bathroom: int
    dist_center: Optional[float] = None
    dist_stop: Optional[float] = None
    dist_metro: Optional[float] = None
    year: Optional[int] = None
    zone: Optional[str] = None


def _features_from_request(req: ValuationRequest) -> dict:
    total_floors = req.total_floors or 9
    floor = req.floor
    if floor > total_floors:
        total_floors = floor
    return {
        "area": req.area,
        "rooms": req.rooms,
        "floor": floor,
        "total_floors": total_floors,
        "floor_type": FLOOR_TYPE_MAP.get(req.floor_type, 2),
        "repair": REPAIR_MAP.get(req.repair, 3),
        "material": MATERIAL_MAP.get(req.material, 3) if req.material else 3,
        "balcony": req.balcony,
        "split_bathroom": req.split_bathroom,
        "dist_center": req.dist_center if req.dist_center is not None else 7000,
        "dist_stop": req.dist_stop if req.dist_stop is not None else 300,
        "dist_metro": req.dist_metro if req.dist_metro is not None else 1500,
        "year": req.year or 1990,
        "zone": ZONE_MAP.get(req.zone, 3) if req.zone else 3,
    }


def _apply_house_info(features: dict, info) -> None:
    if info is None or info.confidence == "low":
        return
    if info.year_built:
        features["year"] = int(info.year_built)
    if info.floors:
        features["total_floors"] = int(info.floors)
        if features["floor"] > features["total_floors"]:
            features["floor"] = features["total_floors"]
    if info.material:
        features["material"] = MATERIAL_MAP.get(info.material, features["material"])
    if info.dist_to_center:
        features["dist_center"] = float(info.dist_to_center)
    if info.nearest_metro:
        features["dist_metro"] = float(info.nearest_metro)
    if info.nearest_bus_stop:
        features["dist_stop"] = float(info.nearest_bus_stop)
    if info.zone:
        features["zone"] = ZONE_MAP.get(info.zone, features["zone"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": dp.get_stats(),
            "repair_options": list(REPAIR_MAP.keys()),
            "floor_options": list(FLOOR_TYPE_MAP.keys()),
            "material_options": list(MATERIAL_MAP.keys()),
            "zone_options": list(ZONE_MAP.keys()),
        },
    )


@app.post("/api/house-info")
async def get_house_info(req: AddressRequest):
    info = house_service.get_house_info(req.address.strip(), use_poi=False)
    found = info.confidence != "low" and info.source != "not_found"
    return {
        "success": found,
        "data": info.to_dict(),
        "message": "Данные получены из локальной базы" if found else "Адрес не найден в базе",
    }


@app.get("/api/address-suggest")
async def suggest_addresses(q: str = ""):
    return {"suggestions": house_service.suggest_addresses(q, limit=7)}


@app.post("/api/estimate")
async def estimate(req: ValuationRequest):
    if req.area <= 0 or req.floor <= 0:
        raise HTTPException(status_code=400, detail="Площадь и этаж должны быть больше нуля")

    features = _features_from_request(req)
    house_info = None
    if req.address and req.address.strip():
        try:
            house_info = house_service.get_house_info(req.address.strip(), use_poi=False)
            _apply_house_info(features, house_info)
        except Exception as exc:
            print(f"[Estimate] Ошибка получения данных о доме: {exc}")

    result = model.estimate(features)
    if house_info and house_info.confidence != "low":
        result["house_info"] = house_info.to_dict()
    return result
