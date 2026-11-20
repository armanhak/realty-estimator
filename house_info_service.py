"""
Характеристики дома по адресу.
Основной источник — локальная база квартир. Геокодер и точки интереса
подключаются, если задан ключ и координаты.
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class HouseInfo:
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    year_built: Optional[int] = None
    material: Optional[str] = None
    floors: Optional[int] = None
    total_area: Optional[float] = None
    parking_type: Optional[str] = None
    elevator: Optional[bool] = None
    emergency_status: Optional[bool] = None
    zone: Optional[str] = None
    functional_zone: Optional[str] = None
    dist_to_center: Optional[int] = None
    nearest_metro: Optional[int] = None
    nearest_bus_stop: Optional[int] = None
    nearest_school: Optional[int] = None
    nearest_kindergarten: Optional[int] = None
    source: str = "combined"
    fetched_at: Optional[str] = None
    confidence: str = "high"

    def to_dict(self) -> dict:
        payload = asdict(self)
        for key, value in list(payload.items()):
            if hasattr(value, "item"):
                payload[key] = value.item()
        return payload


class LocalHouseDatabase:
    """Индекс домов, собранный по уже очищенному датасету."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True)
        self.address_index: Dict[str, List[int]] = {}
        for idx, row in self.df.iterrows():
            address = str(row.get("Адрес", "")).strip()
            if address and address != "—":
                key = self._normalize_address(address)
                self.address_index.setdefault(key, []).append(int(idx))

    @staticmethod
    def _normalize_address(addr: str) -> str:
        addr = addr.lower().strip()
        addr = re.sub(r"[,.;:]", " ", addr)
        addr = re.sub(r"\s+", " ", addr)
        replacements = {
            "нижегородская область": "",
            "нижний новгород": "",
            "россия": "",
            "г.": "",
            "д.": "",
            "ул.": "улица",
            "пр-т": "проспект",
            "пр.": "проспект",
        }
        for src, dst in replacements.items():
            addr = addr.replace(src, dst)
        return re.sub(r"\s+", " ", addr).strip(" ,")

    _GENERIC = {
        "улица", "проспект", "переулок", "бульвар", "шоссе", "площадь",
        "город", "россия", "нижний", "новгород", "дом", "корпус",
        "городского", "округа", "жилой", "район",
    }

    def ranked_addresses(self, query: str, limit: int = 7) -> List[str]:
        """Адреса домов, которые совпадают с запросом, в том же порядке, что и загрузка дома."""
        scored = self._score_addresses(query)
        return [address for _score, address, _key in scored[:limit]]

    def is_unique_match(self, query: str) -> bool:
        scored = self._score_addresses(query)
        if len(scored) == 1:
            return True
        return len(scored) > 1 and scored[0][0] > scored[1][0]

    def _score_addresses(self, query: str) -> List[Tuple[int, str, str]]:
        query_norm = self._normalize_address(query)
        if len(query_norm) < 3:
            return []
        scored = []
        for addr_key, indices in self.address_index.items():
            score = self._match_score(query_norm, addr_key)
            if score <= 0:
                continue
            address = str(self.df.iloc[indices[0]]["Адрес"])
            scored.append((score, address, addr_key))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored

    def _match_score(self, query_norm: str, addr_key: str) -> int:
        query_tokens = [token for token in query_norm.split() if token not in self._GENERIC]
        if not query_tokens:
            return 0
        addr_tokens = addr_key.split()
        addr_set = set(addr_tokens)
        score = 0
        for token in query_tokens:
            if any(char.isdigit() for char in token):
                if token not in addr_set:
                    return 0
                score += 50
                continue
            if token in addr_set:
                score += 20
                continue
            if len(token) >= 3 and any(item.startswith(token) for item in addr_tokens):
                score += 8
                continue
            return 0
        if query_norm == addr_key:
            score += 100
        return score

    def search_by_address(self, query: str) -> List[pd.Series]:
        scored = self._score_addresses(query)
        if not scored:
            return []
        _score, _address, addr_key = scored[0]
        return [self.df.iloc[idx] for idx in self.address_index[addr_key]]

    def get_house_info(self, query: str) -> Optional[HouseInfo]:
        results = self.search_by_address(query)
        if not results:
            return None

        matches = pd.DataFrame(results)
        lat = self._mean(matches, "Широта")
        lon = self._mean(matches, "Долгота")
        year = self._mode_int(matches, "Год постройки")
        material = self._mode_text(matches, "Материал (текст)")
        floors = self._max_int(matches, "Этажность")
        parking = self._mode_text(matches, "Парковка")
        zone = self._mode_text(matches, "Зона (текст)")
        dist_center = self._positive_median(matches, "Расстояние до центра, м.")
        dist_metro = self._positive_median(matches, "Ближайшее метро, м.")
        dist_bus = self._positive_median(matches, "Ближайшая остановка, м.")
        address = str(matches["Адрес"].iloc[0]) if "Адрес" in matches else query

        return HouseInfo(
            address=address,
            latitude=lat,
            longitude=lon,
            year_built=year,
            material=material,
            floors=floors,
            parking_type=None if parking in (None, "—", "nan") else parking,
            zone=zone,
            functional_zone=zone,
            dist_to_center=dist_center,
            nearest_metro=dist_metro,
            nearest_bus_stop=dist_bus,
            source="local_dataset",
            fetched_at=datetime.now().isoformat(timespec="seconds"),
            confidence="high" if len(results) >= 3 else "medium",
        )

    @staticmethod
    def _mean(frame: pd.DataFrame, column: str) -> Optional[float]:
        if column not in frame:
            return None
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            return None
        return float(series.mean())

    @staticmethod
    def _mode_text(frame: pd.DataFrame, column: str) -> Optional[str]:
        if column not in frame:
            return None
        series = frame[column].dropna().astype(str)
        series = series[~series.isin(["", "—", "nan", "None"])]
        if series.empty:
            return None
        mode = series.mode()
        return str(mode.iloc[0] if not mode.empty else series.iloc[0])

    @staticmethod
    def _mode_int(frame: pd.DataFrame, column: str) -> Optional[int]:
        if column not in frame:
            return None
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            return None
        mode = series.mode()
        return int(mode.iloc[0] if not mode.empty else series.median())

    @staticmethod
    def _max_int(frame: pd.DataFrame, column: str) -> Optional[int]:
        if column not in frame:
            return None
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            return None
        return int(series.max())

    @staticmethod
    def _positive_median(frame: pd.DataFrame, column: str) -> Optional[int]:
        if column not in frame:
            return None
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        series = series[series > 0]
        if series.empty:
            return None
        return int(series.median())


class GeocodingService:
    """Сначала Яндекс, если задан ключ, затем открытые карты."""

    # Чуть шире границ базы, чтобы взять дом рядом с Нижним Новгородом.
    _SOUTH, _WEST, _NORTH, _EAST = 56.12, 43.50, 56.42, 44.15

    def __init__(self, yandex_api_key: Optional[str] = None):
        self.yandex_api_key = yandex_api_key
        self._suggest_cache: dict = {}
        self._last_nominatim = 0.0

    def geocode(self, address: str) -> Optional[Tuple[float, float, str]]:
        query = address.strip()
        if "новгород" not in query.lower():
            query = f"{query}, Нижний Новгород"
        wanted = self._house_number(query)
        finders = []
        if self.yandex_api_key:
            finders.append(self._yandex)
        finders.extend([self._nominatim, self._photon])
        for finder in finders:
            found = finder(query, wanted)
            if found and self._inside(found[0], found[1]):
                return found
        return None

    @staticmethod
    def _house_number(query: str) -> Optional[str]:
        """Последнее слово вроде 8, 8В или 27/8. «8 марта» номером дома не считается."""
        tail = query.split(",")[-1].strip().lower()
        last = re.split(r"\s+", tail)[-1].strip(".,")
        if re.fullmatch(r"\d+(?:/\d+)?[а-яa-z]?", last):
            return last
        return None

    def _inside(self, lat: float, lon: float) -> bool:
        return self._SOUTH <= lat <= self._NORTH and self._WEST <= lon <= self._EAST

    def _yandex(self, address: str, wanted: Optional[str] = None) -> Optional[Tuple[float, float, str]]:
        try:
            import requests

            response = requests.get(
                "https://geocode-maps.yandex.ru/1.x/",
                params={"apikey": self.yandex_api_key, "geocode": address, "format": "json", "lang": "ru_RU"},
                timeout=6,
            )
            response.raise_for_status()
            member = response.json()["response"]["GeoObjectCollection"]["featureMember"][0]
            geo = member["GeoObject"]
            lon, lat = map(float, geo["Point"]["pos"].split())
            return lat, lon, geo.get("name") or address
        except Exception as exc:
            print(f"[Geocoding] Ошибка Яндекс API: {exc}")
            return None

    def _nominatim(self, address: str, wanted: Optional[str] = None) -> Optional[Tuple[float, float, str]]:
        try:
            import requests

            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "jsonv2",
                    "limit": 5,
                    "countrycodes": "ru",
                    "addressdetails": 1,
                },
                headers={"User-Agent": "realty-estimator/1.0 (nizhny apartment valuation)", "Accept-Language": "ru"},
                timeout=8,
            )
            response.raise_for_status()
            fallback = None
            for row in response.json():
                lat, lon = float(row["lat"]), float(row["lon"])
                if not self._inside(lat, lon):
                    continue
                parts = row.get("address") or {}
                street = parts.get("road") or parts.get("pedestrian") or parts.get("street")
                house = parts.get("house_number")
                city = parts.get("city") or parts.get("town") or "Нижний Новгород"
                label = ", ".join(part for part in [city, street, house] if part) or row.get("display_name") or address
                found = (lat, lon, label)
                number = self._house_number(str(house or ""))
                if wanted and number == wanted:
                    return found
                if fallback is None and not wanted:
                    fallback = found
            return fallback
        except Exception as exc:
            print(f"[Geocoding] Ошибка Nominatim: {exc}")
            return None

    def suggest(self, address: str, limit: int = 5) -> List[str]:
        """Подсказки с карты, если дома нет в локальной базе."""
        import time

        query = address.strip()
        if len(query) < 5:
            return []
        if "новгород" not in query.lower():
            query = f"{query}, Нижний Новгород"
        cached = self._suggest_cache.get(query)
        now = time.monotonic()
        if cached and now - cached[0] < 120:
            return cached[1][:limit]
        # У Nominatim лимит около одного запроса в секунду. Частые подсказки идут в Photon.
        if now - self._last_nominatim >= 1.1:
            self._last_nominatim = now
            labels = self._suggest_nominatim(query, limit)
        else:
            labels = []
        if not labels:
            labels = self._suggest_photon(query, limit)
        labels = labels[:limit]
        self._suggest_cache[query] = (now, labels)
        return labels

    def _suggest_nominatim(self, address: str, limit: int) -> List[str]:
        try:
            import requests

            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "jsonv2",
                    "limit": limit,
                    "countrycodes": "ru",
                    "addressdetails": 1,
                },
                headers={"User-Agent": "realty-estimator/1.0 (nizhny apartment valuation)", "Accept-Language": "ru"},
                timeout=8,
            )
            response.raise_for_status()
            labels = []
            for row in response.json():
                lat, lon = float(row["lat"]), float(row["lon"])
                if not self._inside(lat, lon):
                    continue
                found = self._nominatim_label(row)
                if found and found not in labels:
                    labels.append(found)
            return labels
        except Exception as exc:
            print(f"[Geocoding] Ошибка подсказок Nominatim: {exc}")
            return []

    @staticmethod
    def _nominatim_label(row: dict) -> Optional[str]:
        parts = row.get("address") or {}
        street = parts.get("road") or parts.get("pedestrian") or parts.get("residential")
        house = parts.get("house_number")
        if not street:
            return None
        city = parts.get("city") or parts.get("town") or "Нижний Новгород"
        return ", ".join(part for part in [city, street, house] if part)

    def _suggest_photon(self, address: str, limit: int) -> List[str]:
        try:
            import requests

            response = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": address, "limit": limit, "lat": 56.326, "lon": 44.006},
                headers={"User-Agent": "realty-estimator/1.0 (nizhny apartment valuation)"},
                timeout=8,
            )
            response.raise_for_status()
            labels = []
            for feature in response.json().get("features") or []:
                lon, lat = feature["geometry"]["coordinates"][:2]
                if not self._inside(float(lat), float(lon)):
                    continue
                found = self._photon_label(feature.get("properties") or {})
                if found and found not in labels:
                    labels.append(found)
            return labels
        except Exception as exc:
            print(f"[Geocoding] Ошибка подсказок Photon: {exc}")
            return []

    @staticmethod
    def _photon_label(props: dict) -> Optional[str]:
        if props.get("osm_key") == "place" and props.get("osm_value") in {"city", "town", "state", "county"}:
            return None
        street = props.get("street") or props.get("name")
        house = props.get("housenumber")
        if not street:
            return None
        city = props.get("city") or props.get("town") or "Нижний Новгород"
        return ", ".join(part for part in [city, street, house] if part)

    def _photon(self, address: str, wanted: Optional[str] = None) -> Optional[Tuple[float, float, str]]:
        try:
            import requests

            response = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": address, "limit": 5, "lat": 56.326, "lon": 44.006},
                headers={"User-Agent": "realty-estimator/1.0 (nizhny apartment valuation)"},
                timeout=8,
            )
            response.raise_for_status()
            fallback = None
            for feature in response.json().get("features") or []:
                lon, lat = feature["geometry"]["coordinates"][:2]
                if not self._inside(float(lat), float(lon)):
                    continue
                props = feature.get("properties") or {}
                label = self._photon_label(props) or address
                found = (float(lat), float(lon), label)
                number = self._house_number(str(props.get("housenumber") or ""))
                if wanted and number == wanted:
                    return found
                if fallback is None and not wanted:
                    fallback = found
            return fallback
        except Exception as exc:
            print(f"[Geocoding] Ошибка Photon: {exc}")
            return None


class POIService:
    def __init__(self):
        self.api_url = "https://overpass-api.de/api/interpreter"

    def find_nearby(self, lat: float, lon: float, radius: int = 1000) -> Dict[str, Optional[int]]:
        query = f"""
        [out:json][timeout:15];
        (
          node["railway"="station"]["station"="subway"](around:{radius},{lat},{lon});
          node["highway"="bus_stop"](around:{radius},{lat},{lon});
          node["amenity"="school"](around:{radius},{lat},{lon});
          node["amenity"="kindergarten"](around:{radius},{lat},{lon});
        );
        out body;
        """
        try:
            import requests

            response = requests.post(self.api_url, data={"data": query}, timeout=20)
            response.raise_for_status()
            buckets = {"metro": [], "bus_stop": [], "school": [], "kindergarten": []}
            for element in response.json().get("elements", []):
                tags = element.get("tags", {})
                dist = self._haversine(lat, lon, element.get("lat"), element.get("lon"))
                if tags.get("station") == "subway":
                    buckets["metro"].append(dist)
                elif tags.get("highway") == "bus_stop":
                    buckets["bus_stop"].append(dist)
                elif tags.get("amenity") == "school":
                    buckets["school"].append(dist)
                elif tags.get("amenity") == "kindergarten":
                    buckets["kindergarten"].append(dist)
            return {key: int(min(values)) if values else None for key, values in buckets.items()}
        except Exception as exc:
            print(f"[POI] Ошибка запроса: {exc}")
            return {}

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        radius = 6_371_000
        phi1, phi2 = radians(lat1), radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lon2 - lon1)
        a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
        return radius * 2 * atan2(sqrt(a), sqrt(1 - a))


class HouseInfoService:
    def __init__(self, config: Dict, df: Optional[pd.DataFrame] = None):
        self.config = config
        if df is None:
            from data_processor import DataProcessor

            df = DataProcessor(config["dataset_path"]).df
        self.local_db = LocalHouseDatabase(df)
        self.geocoder = GeocodingService(config.get("yandex_api_key"))
        self.poi_service = POIService()
        self.cache_db = self._init_cache() if config.get("use_cache", True) else None

    def _init_cache(self) -> sqlite3.Connection:
        cache_path = self.config.get("cache_path", "house_info_cache.db")
        conn = sqlite3.connect(cache_path, check_same_thread=False)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS house_cache (
                address_hash TEXT PRIMARY KEY,
                address TEXT,
                data_json TEXT,
                fetched_at TIMESTAMP
            )
            """
        )
        conn.commit()
        return conn

    @staticmethod
    def _get_address_hash(address: str) -> str:
        return hashlib.md5(address.lower().strip().encode()).hexdigest()

    def get_house_info(self, address: str, use_poi: bool = False) -> HouseInfo:
        cached = self._get_from_cache(address)
        if cached and cached.source != "not_found":
            requested = GeocodingService._house_number(address)
            same_house = requested == GeocodingService._house_number(cached.address)
            if cached.source != "geocoder" or same_house or not requested:
                return cached

        house_info = self.local_db.get_house_info(address) or HouseInfo(
            address=address,
            confidence="low",
            source="not_found",
            fetched_at=datetime.now().isoformat(timespec="seconds"),
        )

        if house_info.latitude is None or house_info.longitude is None:
            coords = self.geocoder.geocode(address)
            if coords:
                house_info.latitude, house_info.longitude = coords[0], coords[1]
                if house_info.source == "not_found":
                    house_info.source = "geocoder"
                    house_info.confidence = "medium"
                    house_info.address = coords[2] or address

        if use_poi and house_info.latitude and house_info.longitude:
            poi_data = self.poi_service.find_nearby(house_info.latitude, house_info.longitude, radius=1500)
            if poi_data.get("metro"):
                house_info.nearest_metro = poi_data["metro"]
            if poi_data.get("bus_stop"):
                house_info.nearest_bus_stop = poi_data["bus_stop"]
            if poi_data.get("school"):
                house_info.nearest_school = poi_data["school"]
            if poi_data.get("kindergarten"):
                house_info.nearest_kindergarten = poi_data["kindergarten"]
            if house_info.source == "local_dataset":
                house_info.source = "local_dataset + poi"

        house_info.fetched_at = datetime.now().isoformat(timespec="seconds")
        self._save_to_cache(address, house_info)
        return house_info

    def suggest_addresses(self, query: str, limit: int = 7) -> List[str]:
        local = []
        if self.local_db.df is not None:
            local = self.local_db.ranked_addresses(query, limit=limit)
        if local or len((query or "").strip()) < 5:
            return local
        return self.geocoder.suggest(query, limit=limit)

    def _get_from_cache(self, address: str) -> Optional[HouseInfo]:
        if not self.cache_db:
            return None
        try:
            row = self.cache_db.execute(
                "SELECT data_json, fetched_at FROM house_cache WHERE address_hash = ?",
                (self._get_address_hash(address),),
            ).fetchone()
            if not row:
                return None
            data_json, fetched_at = row
            fetched_time = datetime.fromisoformat(fetched_at)
            ttl = timedelta(hours=self.config.get("cache_ttl_hours", 24))
            if datetime.now() - fetched_time >= ttl:
                return None
            return HouseInfo(**json.loads(data_json))
        except Exception as exc:
            print(f"[Cache] Ошибка чтения: {exc}")
            return None

    def _save_to_cache(self, address: str, info: HouseInfo):
        if not self.cache_db:
            return
        try:
            self.cache_db.execute(
                """
                INSERT OR REPLACE INTO house_cache
                (address_hash, address, data_json, fetched_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self._get_address_hash(address),
                    address,
                    json.dumps(info.to_dict(), ensure_ascii=False),
                    info.fetched_at,
                ),
            )
            self.cache_db.commit()
        except Exception as exc:
            print(f"[Cache] Ошибка записи: {exc}")


if __name__ == "__main__":
    service = HouseInfoService(
        {
            "dataset_path": "data/apartments.xlsx",
            "yandex_api_key": None,
            "use_cache": False,
        }
    )
    for sample in [
        "Нижний Новгород, Грузинская улица, 46",
        "Большая Покровская",
    ]:
        info = service.get_house_info(sample, use_poi=False)
        print(sample, "->", info.address, info.year_built, info.material, info.zone, info.confidence)
    print("Подсказки:", service.suggest_addresses("Грузинская", limit=5))
