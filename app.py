from pathlib import Path

import pandas as pd
import streamlit as st

from data_processor import (
    FLOOR_TYPE_MAP,
    MATERIAL_MAP,
    REPAIR_MAP,
    ZONE_MAP,
    DataProcessor,
)
from house_info_service import HouseInfoService
from model import ValuationModel

st.set_page_config(
    page_title="Оценка недвижимости — Нижний Новгород",
    page_icon="🏠",
    layout="wide",
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "apartments.xlsx"
ROOM_LABELS = {0: "Студия", 1: "1", 2: "2", 3: "3", 4: "4 и более"}


@st.cache_resource
def load_services():
    processor = DataProcessor(str(DATA_PATH))
    valuation = ValuationModel(processor)
    houses = HouseInfoService(
        {
            "dataset_path": str(DATA_PATH),
            "yandex_api_key": None,
            "use_cache": False,
        },
        df=processor.df,
    )
    return processor, valuation, houses


dp, model, house_service = load_services()
stats = dp.get_stats()

DEFAULTS = {
    "address": "",
    "area": 55.0,
    "rooms": 2,
    "floor": 5,
    "total_floors": 9,
    "floor_type": "Средний",
    "repair": "Типовой ремонт",
    "material": "Кирпичный",
    "year": 1985,
    "dist_center": 7000,
    "dist_metro": 1500,
    "dist_stop": 300,
    "zone": "Многоквартирная жилая застройка",
    "balcony": "Есть",
    "bathroom": "Раздельный",
    "house": None,
    "house_message": "",
    "result": None,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)


def format_price(price: float) -> str:
    return f"{int(round(price)):,}".replace(",", " ") + " ₽"


def format_signed_price(price: float) -> str:
    sign = "+" if price >= 0 else "−"
    return sign + " " + f"{int(round(abs(price))):,}".replace(",", " ") + " ₽"


def load_house() -> None:
    typed = (st.session_state.get("address") or "").strip()
    query = typed
    if len(query) < 3:
        st.session_state.house = None
        st.session_state.house_message = "Введите адрес дома."
        return

    info = house_service.get_house_info(query, use_poi=False)
    if info.confidence == "low" or info.source == "not_found":
        st.session_state.house = None
        st.session_state.house_message = "Адрес не найден в базе."
        return

    st.session_state.house = info.to_dict()
    st.session_state.house_message = ""
    st.session_state.address = info.address
    if info.year_built:
        st.session_state.year = int(info.year_built)
    if info.floors:
        st.session_state.total_floors = int(info.floors)
        if int(st.session_state.floor) > int(info.floors):
            st.session_state.floor = int(info.floors)
        floor = int(st.session_state.floor)
        if floor <= 1:
            st.session_state.floor_type = "Первый"
        elif floor >= int(info.floors):
            st.session_state.floor_type = "Последний"
    if info.material in MATERIAL_MAP:
        st.session_state.material = info.material
    if info.zone in ZONE_MAP:
        st.session_state.zone = info.zone
    if info.dist_to_center:
        st.session_state.dist_center = int(info.dist_to_center)
    if info.nearest_metro:
        st.session_state.dist_metro = int(info.nearest_metro)
    if info.nearest_bus_stop:
        st.session_state.dist_stop = int(info.nearest_bus_stop)


def use_suggestion() -> None:
    st.session_state.address = st.session_state.address_pick
    load_house()


def estimate_from_form() -> None:
    floor = int(st.session_state.floor)
    total_floors = int(st.session_state.total_floors)
    if floor > total_floors:
        total_floors = floor
        st.session_state.total_floors = total_floors
    features = {
        "area": float(st.session_state.area),
        "rooms": int(st.session_state.rooms),
        "floor": floor,
        "total_floors": total_floors,
        "floor_type": FLOOR_TYPE_MAP.get(st.session_state.floor_type, 2),
        "repair": REPAIR_MAP.get(st.session_state.repair, 3),
        "material": MATERIAL_MAP.get(st.session_state.material, 3),
        "balcony": 1 if st.session_state.balcony == "Есть" else 0,
        "split_bathroom": 1 if st.session_state.bathroom == "Раздельный" else 0,
        "dist_center": float(st.session_state.dist_center),
        "dist_stop": float(st.session_state.dist_stop),
        "dist_metro": float(st.session_state.dist_metro),
        "year": int(st.session_state.year),
        "zone": ZONE_MAP.get(st.session_state.zone, 3),
    }
    st.session_state.result = model.estimate(features)


st.title("Оценка рыночной стоимости квартиры")
st.caption(
    f"Нижний Новгород · база из {stats['n_objects']} объектов · "
    f"цены от {format_price(stats['price_min'])} до {format_price(stats['price_max'])}"
)
st.write(
    "Похожие квартиры влияют на цену сильнее, чем объекты с другими характеристиками."
)

st.subheader("Шаг 1. Адрес дома")
with st.form("house_lookup"):
    st.text_input(
        "Адрес",
        key="address",
        placeholder="Например: Грузинская улица, 46",
    )
    st.form_submit_button("Загрузить характеристики", on_click=load_house)

suggestions = []
query = (st.session_state.address or "").strip()
if len(query) >= 3:
    suggestions = house_service.suggest_addresses(query, limit=7)
if suggestions:
    if st.session_state.get("address_pick") not in suggestions:
        st.session_state.address_pick = suggestions[0]
    st.selectbox(
        "Или выберите адрес из базы",
        suggestions,
        key="address_pick",
        on_change=use_suggestion,
    )

if st.session_state.house_message:
    st.warning(st.session_state.house_message)

house = st.session_state.house
if house:
    st.markdown(f"**{house['address']}**")
    cards = st.columns(4)
    cards[0].metric("Год постройки", house.get("year_built") or "—")
    cards[1].metric("Материал", house.get("material") or "—")
    cards[2].metric("Этажность", f"{house['floors']} эт." if house.get("floors") else "—")
    cards[3].metric("Парковка", house.get("parking_type") or "—")
    cards = st.columns(4)
    cards[0].metric("Зона", house.get("zone") or "—")
    cards[1].metric("До центра", f"{house['dist_to_center']} м" if house.get("dist_to_center") else "—")
    cards[2].metric("До метро", f"{house['nearest_metro']} м" if house.get("nearest_metro") else "—")
    cards[3].metric("До остановки", f"{house['nearest_bus_stop']} м" if house.get("nearest_bus_stop") else "—")

st.subheader("Шаг 2. Характеристики квартиры")
with st.form("valuation"):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.number_input("Площадь, м²", min_value=10.0, max_value=300.0, step=0.1, key="area")
        st.selectbox(
            "Количество комнат",
            list(ROOM_LABELS),
            format_func=lambda value: ROOM_LABELS[value],
            key="rooms",
        )
        st.number_input("Этаж квартиры", min_value=1, max_value=50, step=1, key="floor")
        st.number_input("Этажность дома", min_value=1, max_value=50, step=1, key="total_floors")
        st.selectbox("Тип этажа", list(FLOOR_TYPE_MAP), key="floor_type")
    with col2:
        st.selectbox("Состояние ремонта", list(REPAIR_MAP), key="repair")
        st.selectbox("Материал стен", list(MATERIAL_MAP), key="material")
        st.number_input("Год постройки", min_value=1900, max_value=2026, step=1, key="year")
        st.number_input("Расстояние до центра, м", min_value=0, max_value=30000, step=1, key="dist_center")
        st.number_input("Ближайшее метро, м", min_value=0, max_value=30000, step=1, key="dist_metro")
    with col3:
        st.number_input("Ближайшая остановка, м", min_value=0, max_value=5000, step=1, key="dist_stop")
        st.selectbox("Зона", list(ZONE_MAP), key="zone")
        st.selectbox("Балкон или лоджия", ["Есть", "Нет"], key="balcony")
        st.selectbox("Санузел", ["Раздельный", "Совмещённый"], key="bathroom")
    submitted = st.form_submit_button("Рассчитать рыночную стоимость", type="primary")

if submitted:
    estimate_from_form()

result = st.session_state.result
if result:
    st.subheader("Результат оценки")
    left, right = st.columns([2, 1])
    left.metric("Рыночная стоимость", format_price(result["price"]))
    left.caption(f"Диапазон: {format_price(result['ci_low'])} — {format_price(result['ci_high'])}")
    right.metric("Учтено аналогов", result["n_analogues_used"])

    st.markdown("**Поправки к рыночной стоимости**")
    st.caption(
        f"Базовая стоимость при средних характеристиках: {format_price(result['base_price'])}. "
        "Каждая строка показывает влияние параметра отдельно. Итог — разница между оценкой и базой."
    )
    adjustment_rows = []
    for index, item in enumerate(result["adjustments"], start=1):
        adjustment_rows.append(
            {
                "№": index,
                "Параметр": item["label"],
                "У объекта": item["object_value"],
                "Поправка, ₽": format_signed_price(item["money_adj"]),
                "Поправка, %": f"{item['pct_adj']:+.1f}%",
                "Влияние": "Повышает" if item["money_adj"] >= 0 else "Снижает",
            }
        )
    st.dataframe(pd.DataFrame(adjustment_rows), use_container_width=True, hide_index=True)

    chart = pd.DataFrame(
        {
            "Параметр": [item["label"] for item in result["adjustments"][:8]],
            "Поправка, тыс. ₽": [item["money_adj"] / 1000 for item in result["adjustments"][:8]],
        }
    ).set_index("Параметр")
    st.bar_chart(chart)

    st.markdown("**Ближайшие аналоги из базы**")
    analogue_rows = [
        {
            "Адрес": item["address"],
            "Площадь, м²": item["area"],
            "Комнаты": item["rooms"],
            "Этаж": item["floor"],
            "Материал": item["material"],
            "Год": item["year"],
            "Ремонт": item["repair"],
            "Цена": format_price(item["price"]),
            "Сходство": f"{item['similarity']}%",
        }
        for item in result["analogues"]
    ]
    st.dataframe(pd.DataFrame(analogue_rows), use_container_width=True, hide_index=True)

    with st.expander("Как считается оценка"):
        st.markdown(
            """
Система сравнивает квартиру с объектами базы по площади, этажу, ремонту, материалу, году и расположению.
Похожим квартирам даётся больший вес, сильно отличающиеся почти не влияют на цену.
Диапазон — коридор, в котором обычно лежит оценка для квартир с таким набором параметров.
Оценка нужна для ориентира. Итоговое суждение остаётся за специалистом.
"""
        )
