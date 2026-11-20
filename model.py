import numpy as np
from scipy.spatial.distance import cdist


FEATURE_LABELS = {
    "Общая площадь, кв.м": "Площадь",
    "Количество комнат": "Комнатность",
    "Этаж": "Этаж квартиры",
    "Этажность": "Этажность дома",
    "Тип этажа": "Тип этажа",
    "Состояние отделки": "Состояние ремонта",
    "Материал стен": "Материал стен",
    "Есть балкон": "Балкон или лоджия",
    "Раздельный санузел": "Раздельный санузел",
    "Расстояние до центра, м.": "Расстояние до центра",
    "Ближайшая остановка, м.": "Ближайшая остановка",
    "Ближайшее метро, м.": "Ближайшее метро",
    "Год постройки": "Год постройки",
    "Зона": "Район и зона",
}

# Площадь, расстояние до центра, остановка, метро, год.
LOG_FEATURE_INDICES = [0, 9, 10, 11, 12]


class _FittedModel:
    """Коэффициенты признаков отдельно от свободного члена."""

    def __init__(self, coef: np.ndarray, intercept: float):
        self.coef_ = np.asarray(coef, dtype=float)
        self.intercept_ = float(intercept)

    def predict(self, X: np.ndarray) -> np.ndarray:
        matrix = np.asarray(X, dtype=float)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        return matrix @ self.coef_ + self.intercept_


class LocalWeightedRegressor:
    """
    Локальная взвешенная мультипликативная регрессия.
    Ближние объекты получают больший вес через гауссово ядро.
    Свободный член тоже взвешивается, иначе перехват смещает оценку.
    """

    def __init__(self, bandwidth: float = 1.5):
        self.bandwidth = bandwidth

    def _gaussian_weights(self, distances: np.ndarray) -> np.ndarray:
        return np.exp(-(distances ** 2) / (2 * self.bandwidth ** 2))

    def predict(self, X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray):
        x_row = np.asarray(X_test, dtype=float).reshape(1, -1)
        distances = cdist(x_row, X_train, metric="euclidean")[0]
        weights = self._gaussian_weights(distances)

        # Вес ниже 5% почти не двигает цену, но раздувает число «учтённых» аналогов.
        mask = weights >= 0.05
        if int(mask.sum()) < 40:
            top_idx = np.argsort(weights)[-40:]
            mask = np.zeros_like(weights, dtype=bool)
            mask[top_idx] = True

        X_local = X_train[mask]
        y_local = y_train[mask]
        w_local = weights[mask]
        indices_local = np.where(mask)[0]

        # Штраф только на наклоны: свободный член — это базовая цена и его нельзя прижимать к нулю.
        sw = np.sqrt(w_local)
        weighted_x = X_local * sw[:, None]
        weighted_y = y_local * sw
        n_features = X_local.shape[1]
        system = np.zeros((n_features + 1, n_features + 1))
        system[:n_features, :n_features] = weighted_x.T @ weighted_x + np.eye(n_features)
        system[:n_features, n_features] = weighted_x.T @ sw
        system[n_features, :n_features] = sw @ weighted_x
        system[n_features, n_features] = float(np.dot(sw, sw))
        right_hand = np.append(weighted_x.T @ weighted_y, float(np.dot(sw, weighted_y)))
        solution = np.linalg.solve(system, right_hand)
        fitted = _FittedModel(coef=solution[:-1], intercept=float(solution[-1]))

        y_pred_log = float(fitted.predict(x_row)[0])
        return y_pred_log, indices_local, w_local, fitted, X_local


class ValuationModel:
    def __init__(self, data_processor, bandwidth: float = 1.5):
        self.dp = data_processor
        self.regressor = LocalWeightedRegressor(bandwidth=bandwidth)

    def _compute_adjustments(self, model: _FittedModel, x_scaled: np.ndarray, feature_cols):
        """
        Поправка фактора в рублях относительно цены при средних признаках:
        base * (exp(coef_i * x_i) - 1).
        """
        base_price = float(np.exp(model.intercept_))
        adjustments = []
        for i, name in enumerate(feature_cols):
            log_contribution = float(model.coef_[i] * x_scaled[0, i])
            money_adjustment = base_price * np.exp(log_contribution) - base_price
            pct_adjustment = (np.exp(log_contribution) - 1) * 100
            adjustments.append(
                {
                    "feature": name,
                    "label": FEATURE_LABELS.get(name, name),
                    "coef": float(model.coef_[i]),
                    "scaled_value": float(x_scaled[0, i]),
                    "money_adj": float(money_adjustment),
                    "pct_adj": float(pct_adjustment),
                }
            )
        adjustments.sort(key=lambda item: -abs(item["money_adj"]))
        predicted = float(np.exp(model.predict(x_scaled)[0]))
        return adjustments, base_price, predicted

    def _get_feature_values(self, features_dict: dict) -> dict:
        return {
            "Общая площадь, кв.м": f"{features_dict['area']} м²",
            "Количество комнат": "Студия" if int(features_dict["rooms"]) == 0 else str(features_dict["rooms"]),
            "Этаж": str(features_dict["floor"]),
            "Этажность": str(features_dict["total_floors"]),
            "Тип этажа": self._reverse_map(
                features_dict["floor_type"],
                {1: "Первый", 2: "Средний", 3: "Последний"},
            ),
            "Состояние отделки": self._reverse_map(
                features_dict["repair"],
                {1: "Требует ремонта", 2: "Под чистовую", 3: "Типовой ремонт", 4: "Комфортный ремонт"},
            ),
            "Материал стен": self._reverse_map(
                features_dict["material"],
                {1: "Деревянный", 2: "Панельный", 3: "Блочный", 4: "Кирпичный", 5: "Монолитный"},
            ),
            "Есть балкон": "Есть" if features_dict["balcony"] else "Нет",
            "Раздельный санузел": "Да" if features_dict["split_bathroom"] else "Нет",
            "Расстояние до центра, м.": f"{int(features_dict['dist_center'])} м",
            "Ближайшая остановка, м.": f"{int(features_dict['dist_stop'])} м",
            "Ближайшее метро, м.": f"{int(features_dict['dist_metro'])} м",
            "Год постройки": str(features_dict["year"]),
            "Зона": self._reverse_map(
                features_dict["zone"],
                {
                    1: "Окраина или промзона",
                    2: "Автомагистраль или ИЖС",
                    3: "Жилая застройка",
                    4: "Деловой центр",
                    5: "Исторический центр",
                },
            ),
        }

    @staticmethod
    def _reverse_map(value, mapping):
        return mapping.get(int(value), "—")

    def estimate(self, features_dict: dict) -> dict:
        x = np.array(
            [[
                features_dict["area"],
                features_dict["rooms"],
                features_dict["floor"],
                features_dict["total_floors"],
                features_dict["floor_type"],
                features_dict["repair"],
                features_dict["material"],
                features_dict["balcony"],
                features_dict["split_bathroom"],
                features_dict["dist_center"],
                features_dict["dist_stop"],
                features_dict["dist_metro"],
                features_dict["year"],
                features_dict["zone"],
            ]],
            dtype=float,
        )

        x_log = x.copy()
        for idx in LOG_FEATURE_INDICES:
            x_log[0, idx] = np.log1p(max(0.0, x_log[0, idx]))

        x_scaled = self.dp.scaler.transform(x_log)
        y_pred_log, indices, weights, fitted, _x_local = self.regressor.predict(
            self.dp.X_scaled, self.dp.y_log, x_scaled[0]
        )
        y_pred = float(np.exp(y_pred_log))

        local_pred = fitted.predict(self.dp.X_scaled[indices])
        residuals = self.dp.y_log[indices] - local_pred
        sigma = float(np.sqrt(np.average(residuals ** 2, weights=weights)))
        sigma = max(sigma, 0.04)
        ci_low = float(np.exp(y_pred_log - 1.96 * sigma))
        ci_high = float(np.exp(y_pred_log + 1.96 * sigma))

        adjustments, base_price, _predicted = self._compute_adjustments(
            fitted, x_scaled, self.dp.feature_cols
        )
        object_values = self._get_feature_values(features_dict)
        for item in adjustments:
            item["object_value"] = object_values.get(item["feature"], "—")

        analogues = self.dp.get_analogues(indices, weights, top_n=5)
        return {
            "price": int(round(y_pred)),
            "base_price": int(round(base_price)),
            "ci_low": int(round(ci_low)),
            "ci_high": int(round(ci_high)),
            "analogues": analogues,
            "adjustments": adjustments,
            "n_analogues_used": int(len(indices)),
        }
