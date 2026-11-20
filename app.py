import html
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
    initial_sidebar_state="collapsed",
)

# Те же цвета и карточки, что у локального сайта. Файл config.toml фиксирует тему
# и на компьютере, и на Streamlit Cloud, иначе облако подставляет свою.
st.markdown(
    """
    <style>
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stToolbar"] {
        background: linear-gradient(160deg, #1f3b73 0%, #3d6b8a 45%, #d7e4ea 100%) !important;
        color: #243044;
    }
    [data-testid="stHeader"],
    [data-testid="stToolbar"] { background: transparent !important; }
    .block-container {
        max-width: 1100px;
        background: #ffffff !important;
        border-radius: 16px;
        padding: 2rem 2.2rem 2.4rem;
        box-shadow: 0 10px 30px rgba(20, 35, 60, 0.12);
    }
    iframe { border: none !important; background: transparent !important; }
    .subtitle { color: #5c6b7a; font-size: 16px; margin: 0 0 6px; text-align: center; }
    .method { color: #7b8794; font-size: 14px; text-align: center; margin-bottom: 8px; }
    .page-title { text-align: center; font-size: 28px; margin: 0 0 8px; }
    .stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {
        border: 2px solid #e0e6ed !important;
        border-radius: 8px !important;
        background: #ffffff !important;
    }
    .stFormSubmitButton button,
    .stButton > button {
        background: #1f4e79 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    .stFormSubmitButton button { width: 100%; padding: 0.7rem 1rem !important; }
    .stFormSubmitButton button:hover,
    .stButton > button:hover { background: #173e61 !important; color: #ffffff !important; }
    div[data-testid="stMetric"] {
        background: #f6f8fb;
        border-radius: 12px;
        padding: 14px 12px;
        border-left: 4px solid #1f4e79;
    }
    .price-card {
        background: #1f6b4a;
        color: #ffffff;
        border-radius: 12px;
        padding: 28px;
        text-align: center;
    }
    .price-card .price-label { color: rgba(255,255,255,0.9); font-size: 14px; }
    .price-card .price-value { color: #ffffff; font-size: 36px; font-weight: 700; margin: 8px 0; }
    .price-card .price-range { color: #ffffff; font-size: 15px; }
    .house-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 12px;
        margin-top: 12px;
    }
    .house-card {
        background: #f6f8fb;
        border-radius: 10px;
        padding: 12px;
        text-align: center;
        border-left: 4px solid #1f4e79;
    }
    .house-card .info-label {
        color: #7b8794;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .house-card .info-value { font-size: 16px; font-weight: 700; margin-top: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "apartments.xlsx"
ADDRESS_BOX = components.declare_component(
    "address_box",
    path=str(Path(__file__).resolve().parent / "components" / "address_box"),
)
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


def apply_house(address: str) -> None:
    info = house_service.get_house_info(address, use_poi=False)
    if info.confidence == "low" or info.source == "not_found":
        st.session_state.house = None
        st.session_state.house_message = "Адрес не найден в базе."
        return

    st.session_state.address = info.address
    st.session_state.house = info.to_dict()
    st.session_state.house_message = ""
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


def load_house() -> None:
    typed = (st.session_state.get("address") or "").strip()
    if len(typed) < 3:
        st.session_state.house = None
        st.session_state.house_message = "Введите адрес дома."
        return

    matches = house_service.suggest_addresses(typed, limit=7)
    if not matches:
        st.session_state.house = None
        st.session_state.house_message = "Адрес не найден в базе."
        return
    if not house_service.local_db.is_unique_match(typed):
        st.session_state.house = None
        st.session_state.house_message = "Найдено несколько домов. Выберите адрес из подсказки."
        return
    apply_house(matches[0])


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


st.markdown(
    f"""
    <h1 class="page-title">Оценка рыночной стоимости квартиры</h1>
    <p class="subtitle">Нижний Новгород · база из {stats['n_objects']} объектов · цены от {format_price(stats['price_min'])} до {format_price(stats['price_max'])}</p>
    <p class="method">Похожие квартиры влияют на цену сильнее, чем объекты с другими характеристиками.</p>
    """,
    unsafe_allow_html=True,
)

st.subheader("Шаг 1. Адрес дома")
st.caption("Начните вводить адрес — ниже появятся дома из базы.")
query = (st.session_state.get("address_query") or "").strip()
suggestions = house_service.suggest_addresses(query, limit=7) if len(query) >= 3 else []
loaded_address = (st.session_state.house or {}).get("address")
visible_suggestions = [] if loaded_address and query == loaded_address else suggestions
address_event = ADDRESS_BOX(
    value=st.session_state.get("address_query", ""),
    suggestions=visible_suggestions,
    key="address_box",
    default=None,
)
if isinstance(address_event, dict) and address_event.get("seq") != st.session_state.get("address_event_seq"):
    st.session_state.address_event_seq = address_event.get("seq")
    typed = (address_event.get("value") or "").strip()
    kind = address_event.get("type")
    if kind == "input":
        st.session_state.address_query = typed
        st.rerun()
    elif kind == "pick" and typed:
        st.session_state.address_query = typed
        st.session_state.address = typed
        apply_house(typed)
    elif kind == "load":
        st.session_state.address_query = typed
        st.session_state.address = typed
        load_house()

if st.session_state.house_message:
    st.warning(st.session_state.house_message)

def _card(label: str, value) -> str:
    text = "—" if value in (None, "") else str(value)
    return (
        f'<div class="house-card"><div class="info-label">{html.escape(label)}</div>'
        f'<div class="info-value">{html.escape(text)}</div></div>'
    )


house = st.session_state.house
if house:
    st.markdown(
        "<div class='house-grid'>"
        + _card("Адрес", house.get("address"))
        + _card("Год постройки", house.get("year_built"))
        + _card("Материал", house.get("material"))
        + _card("Этажность", f"{house['floors']} эт." if house.get("floors") else "—")
        + _card("Парковка", house.get("parking_type"))
        + _card("Зона", house.get("zone"))
        + _card("До центра", f"{house['dist_to_center']} м" if house.get("dist_to_center") else "—")
        + _card("До метро", f"{house['nearest_metro']} м" if house.get("nearest_metro") else "—")
        + _card("До остановки", f"{house['nearest_bus_stop']} м" if house.get("nearest_bus_stop") else "—")
        + "</div>",
        unsafe_allow_html=True,
    )

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
    price_col, count_col = st.columns([2, 1])
    price_col.markdown(
        f"""
        <div class="price-card">
            <div class="price-label">Рыночная стоимость</div>
            <div class="price-value">{format_price(result['price'])}</div>
            <div class="price-range">Диапазон: {format_price(result['ci_low'])} — {format_price(result['ci_high'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    count_col.metric("Учтено аналогов", result["n_analogues_used"])

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
