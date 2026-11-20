import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

# В выгрузке колонка «Зона» почти пустая. Рабочая локация — «Функциональная зона»:
# её значения совпадают со шкалой из модели.
REPAIR_MAP = {
    "Требует ремонта": 1,
    "Под чистовую": 2,
    "Типовой ремонт": 3,
    "Комфортный ремонт": 4,
    "Неизвестно": 3,
}

FLOOR_TYPE_MAP = {
    "Первый": 1,
    "Средний": 2,
    "Последний": 3,
    "Неизвестно": 2,
}

MATERIAL_MAP = {
    "Кирпичный": 4,
    "Монолитный": 5,
    "Панельный": 2,
    "Блочный": 3,
    "Смешанный": 3,
    "Деревянный": 1,
    "Неизвестно": 3,
}

ZONE_MAP = {
    "Исторический центр города": 5,
    "Центр деловой активности": 4,
    "Многоквартирная жилая застройка": 3,
    "Зона автомагистралей": 2,
    "Окраина": 1,
    "Промзона": 1,
    "ИЖС": 2,
    "Зеленая зона": 3,
    "Неизвестно": 3,
}

NUMERIC_FEATURES = [
    "Общая площадь, кв.м",
    "Количество комнат",
    "Этаж",
    "Этажность",
    "Расстояние до центра, м.",
    "Ближайшая остановка, м.",
    "Ближайшее метро, м.",
    "Год постройки",
]


def load_and_clean_data(path: str) -> pd.DataFrame:
    """Загружает и очищает датасет квартир Нижнего Новгорода."""
    df = pd.read_excel(path)
    if "Цена" not in df.columns:
        raise ValueError("В файле нет колонки «Цена». Ожидается выгрузка квартир с заголовками.")

    df = df.dropna(subset=["Цена"])
    df["Цена"] = pd.to_numeric(df["Цена"], errors="coerce")
    df = df.dropna(subset=["Цена"])
    df = df[df["Цена"] > 0]

    q_low, q_high = df["Цена"].quantile([0.01, 0.99])
    df = df[(df["Цена"] >= q_low) & (df["Цена"] <= q_high)]

    df["Количество комнат"] = df["Количество комнат"].replace("4 и более", 4)
    df["Количество комнат"] = df["Количество комнат"].replace("Студия", 0)
    df["Количество комнат"] = pd.to_numeric(df["Количество комнат"], errors="coerce").fillna(1)

    for col in NUMERIC_FEATURES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["Расстояние до центра, м.", "Ближайшая остановка, м.", "Ближайшее метро, м."]:
        if col in df.columns:
            positive = df.loc[df[col] > 0, col]
            median_val = float(positive.median()) if len(positive) else 0.0
            df[col] = df[col].where(df[col] > 0, median_val)

    area = df["Общая площадь, кв.м"]
    positive_area = area[area > 0]
    median_area = float(positive_area.median()) if len(positive_area) else 1.0
    df["Общая площадь, кв.м"] = area.where(area > 0, median_area)
    df["Этаж"] = df["Этаж"].fillna(df["Этаж"].median())
    df["Этажность"] = df["Этажность"].fillna(df["Этажность"].median())
    df["Год постройки"] = df["Год постройки"].fillna(df["Год постройки"].median())

    for col in ["Широта", "Долгота"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Ремонт (текст)"] = df["Состояние отделки"].fillna("Типовой ремонт").astype(str)
    df["Материал (текст)"] = df["Материал стен"].fillna("Неизвестно").astype(str)
    zone_source = df["Функциональная зона"] if "Функциональная зона" in df.columns else df["Зона"]
    df["Зона (текст)"] = zone_source.fillna("Неизвестно").astype(str)
    df["Парковка"] = df["Парковка"].fillna("—").astype(str) if "Парковка" in df.columns else "—"
    df["Адрес"] = df["Адрес"].fillna("—").astype(str)

    df["Тип этажа"] = df["Тип этажа"].fillna("Средний").map(FLOOR_TYPE_MAP).fillna(2)
    df["Состояние отделки"] = df["Ремонт (текст)"].map(REPAIR_MAP).fillna(3)
    df["Материал стен"] = df["Материал (текст)"].map(MATERIAL_MAP).fillna(3)
    df["Зона"] = df["Зона (текст)"].map(ZONE_MAP).fillna(3)

    df["Есть балкон"] = (df["Балкон/лоджия"].astype(str).str.strip() == "Есть").astype(int)
    bathroom = df["Санузел"].astype(str).str.strip()
    df["Раздельный санузел"] = bathroom.isin(["Раздельный"]).astype(int)

    return df.reset_index(drop=True)


def prepare_features(df: pd.DataFrame):
    """Подготавливает матрицу признаков. Часть признаков логарифмируется."""
    feature_cols = [
        "Общая площадь, кв.м",
        "Количество комнат",
        "Этаж",
        "Этажность",
        "Тип этажа",
        "Состояние отделки",
        "Материал стен",
        "Есть балкон",
        "Раздельный санузел",
        "Расстояние до центра, м.",
        "Ближайшая остановка, м.",
        "Ближайшее метро, м.",
        "Год постройки",
        "Зона",
    ]

    X = df[feature_cols].copy()
    y = df["Цена"].to_numpy(dtype=float)
    area = df["Общая площадь, кв.м"].to_numpy(dtype=float)
    # Модель объясняет цену квадратного метра. Полная цена — это удельная, умноженная на площадь.
    y_log = np.log(y / area)

    log_cols = [
        "Общая площадь, кв.м",
        "Расстояние до центра, м.",
        "Ближайшая остановка, м.",
        "Ближайшее метро, м.",
        "Год постройки",
    ]
    for col in log_cols:
        X[col] = np.log1p(X[col].clip(lower=0))

    return X, y, y_log, feature_cols


class DataProcessor:
    def __init__(self, data_path: str):
        self.df = load_and_clean_data(data_path)
        self.X, self.y, self.y_log, self.feature_cols = prepare_features(self.df)
        self.scaler = StandardScaler()
        self.X_scaled = self.scaler.fit_transform(self.X.to_numpy(dtype=float))
        self.coordinates = self.df[["Широта", "Долгота"]].to_numpy(dtype=float)

    def get_stats(self):
        return {
            "n_objects": int(len(self.df)),
            "price_min": int(self.y.min()),
            "price_max": int(self.y.max()),
            "price_median": int(np.median(self.y)),
            "area_median": float(self.df["Общая площадь, кв.м"].median()),
        }

    def get_analogues(self, indices, weights, top_n: int = 5, distances_m=None):
        """Топ-N аналогов с наибольшим весом."""
        distance_by_index = {}
        if distances_m is not None:
            distance_by_index = {
                int(idx): float(meters)
                for idx, meters in zip(indices, distances_m)
                if meters is not None and np.isfinite(meters)
            }
        pairs = sorted(zip(indices, weights), key=lambda item: -float(item[1]))[:top_n]
        max_weight = max((float(w) for _, w in pairs), default=0.001)
        analogues = []
        for idx, weight in pairs:
            row = self.df.iloc[int(idx)]
            raw_id = row.get("id", int(idx))
            try:
                raw_id = int(raw_id)
            except (TypeError, ValueError):
                raw_id = str(raw_id)
            analogues.append(
                {
                    "id": raw_id,
                    "address": row.get("Адрес", "—") or "—",
                    "area": round(float(row["Общая площадь, кв.м"]), 1),
                    "rooms": int(row["Количество комнат"]),
                    "floor": f"{int(row['Этаж'])}/{int(row['Этажность'])}",
                    "material": row.get("Материал (текст)", "—"),
                    "year": int(row["Год постройки"]),
                    "repair": row.get("Ремонт (текст)", "—"),
                    "price": int(row["Цена"]),
                    "weight": float(weight),
                    "similarity": min(100, int(float(weight) * 100 / max(0.001, max_weight))),
                    "distance_m": (
                        int(round(distance_by_index[int(idx)]))
                        if int(idx) in distance_by_index
                        else None
                    ),
                }
            )
        return analogues
