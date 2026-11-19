from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_processor import (
    FLOOR_TYPE_MAP,
    MATERIAL_MAP,
    REPAIR_MAP,
    ZONE_MAP,
    DataProcessor,
)
from model import ValuationModel

st.set_page_config(
    page_title="Оценка недвижимости — Нижний Новгород",
    page_icon="🏠",
    layout="wide",
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "apartments.xlsx"


@st.cache_resource
def load_processor():
    return DataProcessor(str(DATA_PATH))


@st.cache_resource
def load_model(_dp):
    return ValuationModel(_dp)


dp = load_processor()
model = load_model(dp)
stats = dp.get_stats()


def format_price(price: float) -> str:
    return f"{int(price):,}".replace(",", " ") + " ₽"


def feature_label(name: str) -> str:
    labels = {
        "Общая площадь, кв.м": "📐 Площадь",
        "Количество комнат": "🚪 Комнаты",
        "Этаж": "🏢 Этаж",
        "Этажность": "🏗 Этажность",
        "Тип этажа": "📍 Тип этажа",
        "Состояние отделки": "🔨 Ремонт",
        "Материал стен": "🧱 Материал",
        "Есть балкон": "🪴 Балкон",
        "Раздельный санузел": "🚿 Санузел",
        "Расстояние до центра, м.": "🏙 До центра",
        "Ближайшая остановка, м.": "🚌 Остановка",
        "Ближайшее метро, м.": "🚇 Метро",
        "Год постройки": "📅 Год",
        "Зона": "🗺 Район",
    }
    return labels.get(name, name)


st.markdown(
    """
# 🏠 Оценка рыночной стоимости квартиры
### Нижний Новгород — автоматизированная система оценки на основе 1000+ объектов

*Метод: мультипликативная регрессия с локальным взвешиванием по сходству объектов*
"""
)

st.markdown("---")
st.markdown("### 📋 Характеристики оцениваемой квартиры")

col1, col2, col3 = st.columns(3)

with col1:
    area = st.number_input(
        "Общая площадь, м²", min_value=10.0, max_value=300.0, value=55.0, step=1.0
    )
    rooms = st.selectbox(
        "Количество комнат",
        [0, 1, 2, 3, 4],
        format_func=lambda x: "Студия" if x == 0 else ("4 и более" if x == 4 else str(x)),
        index=2,
    )
    floor = st.number_input("Этаж квартиры", min_value=1, max_value=50, value=5)
    total_floors = st.number_input("Этажность дома", min_value=1, max_value=50, value=9)

with col2:
    floor_type_name = st.selectbox("Тип этажа", list(FLOOR_TYPE_MAP.keys()), index=1)
    repair_name = st.selectbox(
        "Состояние ремонта",
        ["Требует ремонта", "Типовой ремонт", "Комфортный ремонт"],
        index=1,
    )
    material_name = st.selectbox(
        "Материал стен",
        ["Кирпичный", "Панельный", "Монолитный", "Блочный"],
        index=0,
    )
    year = st.number_input("Год постройки", min_value=1900, max_value=2026, value=1985)

with col3:
    balcony = st.selectbox("Балкон/лоджия", [0, 1], format_func=lambda x: "Есть" if x else "Нет")
    split_bath = st.selectbox(
        "Санузел", [0, 1], format_func=lambda x: "Раздельный" if x else "Совмещённый"
    )
    dist_center = st.number_input(
        "Расстояние до центра, м", min_value=0, max_value=30000, value=7000, step=100
    )
    zone_name = st.selectbox("Зона / район", list(ZONE_MAP.keys()), index=2)

dist1, dist2 = st.columns(2)
with dist1:
    dist_stop = st.number_input(
        "Ближайшая остановка, м", min_value=0, max_value=10000, value=300, step=50
    )
with dist2:
    dist_metro = st.number_input(
        "Ближайшее метро, м", min_value=0, max_value=30000, value=1500, step=50
    )

st.markdown("---")
if st.button("🎯 Рассчитать рыночную стоимость", type="primary", use_container_width=True):
    with st.spinner("Анализируем базу объектов и подбираем аналоги..."):
        features = {
            "area": area,
            "rooms": rooms,
            "floor": floor,
            "total_floors": total_floors,
            "floor_type": FLOOR_TYPE_MAP[floor_type_name],
            "repair": REPAIR_MAP[repair_name],
            "material": MATERIAL_MAP[material_name],
            "balcony": balcony,
            "split_bathroom": split_bath,
            "dist_center": dist_center,
            "dist_stop": dist_stop,
            "dist_metro": dist_metro,
            "year": year,
            "zone": ZONE_MAP[zone_name],
        }
        result = model.estimate(features)

    st.session_state["result"] = result
    st.session_state["features"] = features


if "result" in st.session_state:
    result = st.session_state["result"]

    st.markdown("---")
    st.markdown("### 💰 Результат оценки")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.metric(
            label="Рыночная стоимость",
            value=format_price(result["price"]),
            delta=f"диапазон: {format_price(result['ci_low'])} — {format_price(result['ci_high'])}",
        )
    with col_b:
        st.metric(
            label="Учтено аналогов",
            value=result["n_analogues_used"],
            delta="из базы",
        )

    with st.expander("📊 Из чего сложилась цена (вклад факторов)", expanded=True):
        factors = result["factors"]
        base = float(np.exp(result["log_intercept"]))
        names = ["Средний объект"]
        measures = ["absolute"]
        values = [base]
        texts = [format_price(base)]
        running = base
        for factor in factors:
            nxt = running * float(np.exp(factor["impact"]))
            delta = nxt - running
            running = nxt
            names.append(feature_label(factor["feature"]))
            measures.append("relative")
            values.append(delta)
            texts.append(format_price(abs(delta)) + (" ▲" if delta > 0 else " ▼"))
        names.append("Оценка")
        measures.append("total")
        values.append(result["price"])
        texts.append(format_price(result["price"]))

        fig = go.Figure(
            go.Waterfall(
                name="Вклад фактора",
                orientation="v",
                measure=measures,
                x=names,
                y=values,
                text=texts,
                textposition="outside",
                connector={"line": {"color": "rgb(63, 63, 63)"}},
                increasing={"marker": {"color": "#2ecc71"}},
                decreasing={"marker": {"color": "#e74c3c"}},
                totals={"marker": {"color": "#3498db"}},
            )
        )
        fig.update_layout(
            height=460,
            margin=dict(l=20, r=20, t=40, b=80),
            xaxis_tickangle=-30,
            yaxis_title="₽",
            title="Влияние характеристик на итоговую цену",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Старт — цена «средней» квартиры в локальной выборке. "
            "Каждый столбец — насколько признак сдвигает её относительно среднего по базе. "
            "Последний столбец совпадает с оценкой."
        )

    with st.expander("🏘 Ближайшие аналоги из базы (на чём основана оценка)", expanded=True):
        analogues_df = pd.DataFrame(result["analogues"])
        analogues_df["Цена"] = analogues_df["price"].apply(format_price)
        analogues_df["Сходство"] = analogues_df["similarity"].apply(lambda x: f"{x}%")
        analogues_df = analogues_df[
            ["address", "area", "rooms", "floor", "material", "year", "repair", "Цена", "Сходство"]
        ]
        analogues_df.columns = [
            "Адрес",
            "Площадь",
            "Комнаты",
            "Этаж",
            "Материал",
            "Год",
            "Ремонт",
            "Цена",
            "Сходство",
        ]
        st.dataframe(analogues_df, use_container_width=True, hide_index=True)

    with st.expander("🧠 Как работает метод оценки?"):
        st.markdown(
            """
        **Локальная взвешенная регрессия** работает по принципу опытного оценщика:

        1. **Поиск аналогов.** Система сравнивает ваш объект со всеми квартирами в базе
           по 14 параметрам (площадь, этаж, район, материал, ремонт и т.д.).

        2. **Взвешивание.** Объекты, более похожие на ваш, получают больший вес
           (гауссово ядро). Сильно отличающиеся объекты почти не влияют на результат.

        3. **Локальная регрессия.** На взвешенной выборке строится регрессия
           логарифма цены: влияние площади и расстояний мультипликативное.

        4. **Результат.** Итоговая цена — прогноз этой модели, а диапазон —
           статистический разброс цен среди объектов с ненулевым весом.
        """
        )


st.markdown("---")
st.markdown(
    f"""
<small>

📊 База данных: **{stats['n_objects']}** объектов ·
Диапазон цен: **{format_price(stats['price_min'])}** — **{format_price(stats['price_max'])}** ·
Медиана: **{format_price(stats['price_median'])}**

© 2026 · Система автоматизированной оценки недвижимости

</small>
""",
    unsafe_allow_html=True,
)
