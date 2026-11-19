import numpy as np
from scipy.spatial.distance import cdist
from sklearn.linear_model import LinearRegression


class _FittedModel:
    """Коэффициенты признаков отдельно от свободного члена."""

    def __init__(self, coef: np.ndarray, intercept: float):
        self.coef_ = coef
        self.intercept_ = intercept


class LocalWeightedRegressor:
    """
    Локальная взвешенная мультипликативная регрессия.
    Для каждого объекта оценки:
      1. Считаем расстояния до всех объектов базы
      2. Применяем гауссово ядро → получаем веса
      3. Решаем взвешенную регрессию
      4. Получаем прогноз
    """

    def __init__(self, bandwidth: float = 1.5):
        self.bandwidth = bandwidth

    def _gaussian_weights(self, distances: np.ndarray) -> np.ndarray:
        return np.exp(-(distances ** 2) / (2 * self.bandwidth ** 2))

    def predict(self, X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray):
        """
        Возвращает прогноз в log-шкале, индексы аналогов, их веса и модель.
        Свободный член тоже взвешивается: sqrt(w) умножается на всю матрицу
        [X | 1], иначе перехват смещает оценку.
        """
        x_row = np.asarray(X_test, dtype=float).reshape(1, -1)
        distances = cdist(x_row, X_train, metric="euclidean")[0]
        weights = self._gaussian_weights(distances)

        mask = weights > 1e-6
        if mask.sum() < 5:
            top_idx = np.argsort(weights)[-50:]
            mask = np.zeros_like(weights, dtype=bool)
            mask[top_idx] = True

        X_local = X_train[mask]
        y_local = y_train[mask]
        w_local = weights[mask]
        indices_local = np.where(mask)[0]

        sw = np.sqrt(w_local)
        design = np.column_stack([X_local, np.ones(len(X_local))])
        model = LinearRegression(fit_intercept=False)
        model.fit(design * sw[:, None], y_local * sw)

        x_aug = np.append(x_row.ravel(), 1.0)
        y_pred_log = float(model.predict(x_aug.reshape(1, -1))[0])
        fitted = _FittedModel(coef=model.coef_[:-1], intercept=float(model.coef_[-1]))

        return y_pred_log, indices_local, w_local, fitted


class ValuationModel:
    def __init__(self, data_processor, bandwidth: float = 1.5):
        self.dp = data_processor
        self.regressor = LocalWeightedRegressor(bandwidth=bandwidth)

    def estimate(self, features_dict: dict) -> dict:
        """
        Принимает словарь с характеристиками объекта.
        Возвращает оценку, доверительный интервал, аналоги и вклад факторов.
        """
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
        x_log[0, 0] = np.log1p(max(x_log[0, 0], 0))
        x_log[0, 9] = np.log1p(max(x_log[0, 9], 0))
        x_log[0, 10] = np.log1p(max(x_log[0, 10], 0))
        x_log[0, 11] = np.log1p(max(x_log[0, 11], 0))
        x_log[0, 12] = np.log1p(max(x_log[0, 12], 0))

        x_scaled = self.dp.scaler.transform(x_log)

        y_pred_log, indices, weights, model = self.regressor.predict(
            self.dp.X_scaled, self.dp.y_log, x_scaled[0]
        )
        y_pred = float(np.exp(y_pred_log))

        analog_prices = self.dp.y[indices]
        weighted_mean = np.average(analog_prices, weights=weights)
        weighted_var = np.average((analog_prices - weighted_mean) ** 2, weights=weights)
        weighted_std = float(np.sqrt(weighted_var))
        ci_low = max(0.0, weighted_mean - 1.96 * weighted_std)
        ci_high = weighted_mean + 1.96 * weighted_std

        factor_names = self.dp.feature_cols
        factor_contributions = []
        for i, (name, coef) in enumerate(zip(factor_names, model.coef_)):
            factor_contributions.append(
                {
                    "feature": name,
                    "coef": float(coef),
                    "impact": float(coef * x_scaled[0, i]),
                }
            )
        factor_contributions.sort(key=lambda item: -abs(item["impact"]))

        analogues = self.dp.get_analogues(indices, weights, top_n=5)

        return {
            "price": int(round(y_pred)),
            "ci_low": int(round(ci_low)),
            "ci_high": int(round(ci_high)),
            "analogues": analogues,
            "factors": factor_contributions,
            "n_analogues_used": int(len(indices)),
            "log_intercept": float(model.intercept_),
        }
