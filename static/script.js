function formatDistance(meters) {
    if (meters === null || meters === undefined) return "—";
    if (meters < 1000) return `${Math.round(meters)} м`;
    return `${(meters / 1000).toFixed(1).replace(".", ",")} км`;
}

function formatPrice(price) {
    return Math.round(price).toLocaleString("ru-RU") + " ₽";
}

function formatSignedPrice(price) {
    const sign = price >= 0 ? "+" : "−";
    return sign + " " + Math.abs(Math.round(price)).toLocaleString("ru-RU") + " ₽";
}

function formatPct(pct) {
    const sign = pct >= 0 ? "+" : "−";
    return sign + Math.abs(pct).toFixed(1) + "%";
}

function showNotification(message, type) {
    const notification = document.createElement("div");
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 3200);
}

function setSelectValue(id, value) {
    if (!value) return;
    const select = document.getElementById(id);
    for (const option of select.options) {
        if (option.value === value) {
            select.value = value;
            return;
        }
    }
}

const addressInput = document.getElementById("address-input");
const suggestionsBox = document.getElementById("address-suggestions");
let debounceTimer;

addressInput.addEventListener("input", (event) => {
    clearTimeout(debounceTimer);
    const query = event.target.value.trim();
    if (query.length < 3) {
        suggestionsBox.classList.add("hidden");
        suggestionsBox.innerHTML = "";
        return;
    }
    debounceTimer = setTimeout(async () => {
        try {
            const response = await fetch(`/api/address-suggest?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            suggestionsBox.innerHTML = "";
            if (!data.suggestions || data.suggestions.length === 0) {
                suggestionsBox.classList.add("hidden");
                return;
            }
            data.suggestions.forEach((address) => {
                const item = document.createElement("div");
                item.className = "suggestion-item";
                item.textContent = address;
                item.addEventListener("click", () => {
                    addressInput.value = address;
                    suggestionsBox.classList.add("hidden");
                    fetchHouseInfo();
                });
                suggestionsBox.appendChild(item);
            });
            suggestionsBox.classList.remove("hidden");
        } catch (err) {
            console.error(err);
        }
    }, 250);
});

document.addEventListener("click", (event) => {
    if (!event.target.closest(".address-input-wrapper") && !event.target.closest(".suggestions-dropdown")) {
        suggestionsBox.classList.add("hidden");
    }
});

document.getElementById("btn-fetch").addEventListener("click", fetchHouseInfo);

async function fetchHouseInfo() {
    const address = addressInput.value.trim();
    if (!address) {
        showNotification("Введите адрес дома", "error");
        return;
    }
    const button = document.getElementById("btn-fetch");
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Ищем дом в базе...";
    try {
        const response = await fetch("/api/house-info", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ address }),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            document.getElementById("house-info-block").classList.add("hidden");
            showNotification(result.message || "Адрес не найден в базе", "error");
            return;
        }
        const data = result.data;
        document.getElementById("info-year").textContent = data.year_built || "—";
        document.getElementById("info-material").textContent = data.material || "—";
        document.getElementById("info-floors").textContent = data.floors ? `${data.floors} эт.` : "—";
        document.getElementById("info-parking").textContent = data.parking_type || "—";
        document.getElementById("info-zone").textContent = data.zone || "—";
        document.getElementById("info-dist-center").textContent = data.dist_to_center ? `${data.dist_to_center} м` : "—";
        document.getElementById("info-metro").textContent = data.nearest_metro ? `${data.nearest_metro} м` : "—";
        document.getElementById("info-bus").textContent = data.nearest_bus_stop ? `${data.nearest_bus_stop} м` : "—";
        document.getElementById("info-full-address").textContent = data.address;
        const coords = data.latitude && data.longitude
            ? `Координаты: ${Number(data.latitude).toFixed(5)}, ${Number(data.longitude).toFixed(5)}`
            : "Координаты не найдены";
        document.getElementById("info-coords").textContent = coords;
        document.getElementById("info-source").textContent = data.confidence === "high" ? "Найдено в базе" : "Похожий адрес";
        document.getElementById("house-info-block").classList.remove("hidden");

        if (data.year_built) document.getElementById("year").value = data.year_built;
        if (data.floors) {
            document.getElementById("total_floors").value = data.floors;
            const floorInput = document.getElementById("floor");
            if (parseInt(floorInput.value, 10) > data.floors) {
                floorInput.value = data.floors;
            }
            const floor = parseInt(floorInput.value, 10);
            if (floor <= 1) setSelectValue("floor_type", "Первый");
            else if (floor >= data.floors) setSelectValue("floor_type", "Последний");
        }
        if (data.dist_to_center) document.getElementById("dist_center").value = data.dist_to_center;
        if (data.nearest_metro) document.getElementById("dist_metro").value = data.nearest_metro;
        if (data.nearest_bus_stop) document.getElementById("dist_stop").value = data.nearest_bus_stop;
        setSelectValue("material", data.material);
        setSelectValue("zone", data.zone);
        showNotification("Характеристики дома подставлены в форму", "success");
    } catch (err) {
        showNotification("Не удалось загрузить данные дома", "error");
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}

document.getElementById("valuation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.getElementById("btn-estimate");
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Считаем стоимость...";

    const payload = {
        address: addressInput.value.trim() || null,
        area: parseFloat(document.getElementById("area").value),
        rooms: parseInt(document.getElementById("rooms").value, 10),
        floor: parseInt(document.getElementById("floor").value, 10),
        total_floors: parseInt(document.getElementById("total_floors").value, 10),
        floor_type: document.getElementById("floor_type").value,
        repair: document.getElementById("repair").value,
        material: document.getElementById("material").value,
        balcony: parseInt(document.getElementById("balcony").value, 10),
        split_bathroom: parseInt(document.getElementById("split_bathroom").value, 10),
        dist_center: parseFloat(document.getElementById("dist_center").value),
        dist_stop: parseFloat(document.getElementById("dist_stop").value),
        dist_metro: parseFloat(document.getElementById("dist_metro").value),
        year: parseInt(document.getElementById("year").value, 10),
        zone: document.getElementById("zone").value,
    };

    try {
        const response = await fetch("/api/estimate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || "Ошибка расчёта");
        }
        renderResult(result);
        const section = document.getElementById("result-section");
        section.classList.remove("hidden");
        section.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
        showNotification(err.message || "Ошибка при расчёте", "error");
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
});

function renderResult(result) {
    document.getElementById("price-value").textContent = formatPrice(result.price);
    document.getElementById("price-range").textContent =
        `Диапазон: ${formatPrice(result.ci_low)} — ${formatPrice(result.ci_high)}`;
    document.getElementById("analogues-count").textContent = result.n_analogues_used;
    renderAdjustmentsTable(result);
    renderWaterfallChart(result);
    renderAnaloguesTable(result);
}

function renderAdjustmentsTable(result) {
    const container = document.getElementById("adjustments-table");
    const adjustments = result.adjustments || [];
    const basePrice = result.base_price;
    const finalPrice = result.price;
    const totalAdj = finalPrice - basePrice;
    const totalDir = totalAdj >= 0 ? "positive" : "negative";

    let html = `
        <div class="adjustments-summary">
            <div class="summary-item">
                <div class="summary-label">Базовая стоимость</div>
                <div class="summary-value">${formatPrice(basePrice)}</div>
                <div class="summary-hint">при средних характеристиках</div>
            </div>
            <div class="summary-arrow">→</div>
            <div class="summary-item final">
                <div class="summary-label">Рыночная стоимость</div>
                <div class="summary-value">${formatPrice(finalPrice)}</div>
                <div class="summary-hint">с учётом характеристик объекта</div>
            </div>
        </div>
        <table class="adjustments-table">
            <thead>
                <tr>
                    <th>№</th>
                    <th>Параметр</th>
                    <th>У объекта</th>
                    <th>Поправка, ₽</th>
                    <th>Поправка, %</th>
                    <th>Влияние</th>
                </tr>
            </thead>
            <tbody>`;

    adjustments.forEach((item, index) => {
        const direction = item.money_adj >= 0 ? "positive" : "negative";
        const text = item.money_adj >= 0 ? "Повышает" : "Снижает";
        html += `
            <tr>
                <td>${index + 1}</td>
                <td>${item.label}</td>
                <td>${item.object_value}</td>
                <td class="money-cell ${direction}">${formatSignedPrice(item.money_adj)}</td>
                <td class="pct-cell ${direction}">${formatPct(item.pct_adj)}</td>
                <td><span class="direction-badge ${direction}">${text}</span></td>
            </tr>`;
    });

    html += `
            <tr class="total-row">
                <td colspan="3" class="total-label">Итог относительно базовой стоимости</td>
                <td class="money-cell ${totalDir}">${formatSignedPrice(totalAdj)}</td>
                <td class="pct-cell ${totalDir}">${formatPct((totalAdj / basePrice) * 100)}</td>
                <td></td>
            </tr>
        </tbody></table>
        <div class="table-footnote">
            Поправки показаны по отдельности относительно средней квартиры. Они не складываются
            в одну сумму: параметры влияют на цену совместно. Итоговая строка — разница между
            оценкой и базовой стоимостью.
        </div>`;
    container.innerHTML = html;
}

function renderWaterfallChart(result) {
    const chart = document.getElementById("factors-chart");
    const adjustments = (result.adjustments || []).slice(0, 8);
    const maxImpact = Math.max(...adjustments.map((item) => Math.abs(item.money_adj)), 1);
    chart.innerHTML = adjustments.map((item) => {
        const width = Math.max(8, (Math.abs(item.money_adj) / maxImpact) * 100);
        const direction = item.money_adj >= 0 ? "positive" : "negative";
        return `
            <div class="factor-row">
                <div class="factor-name">${item.label}</div>
                <div class="factor-bar-container">
                    <div class="factor-bar ${direction}" style="width: ${width}%">${formatSignedPrice(item.money_adj)}</div>
                </div>
            </div>`;
    }).join("");
}

function renderAnaloguesTable(result) {
    const rows = (result.analogues || []).map((item) => `
        <tr>
            <td>${item.address}</td>
            <td>${Number(item.area).toFixed(1)} м²</td>
            <td>${item.rooms}</td>
            <td>${item.floor}</td>
            <td>${item.material}</td>
            <td>${item.year}</td>
            <td>${item.repair}</td>
            <td>${formatDistance(item.distance_m)}</td>
            <td><strong>${formatPrice(item.price)}</strong></td>
            <td><span class="similarity-badge">${item.similarity}%</span></td>
        </tr>`).join("");
    document.getElementById("analogues-table").innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Адрес</th><th>Площадь</th><th>Комнаты</th><th>Этаж</th>
                    <th>Материал</th><th>Год</th><th>Ремонт</th><th>До объекта</th><th>Цена</th><th>Сходство</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;
}
