# Оценка квартир в Нижнем Новгороде

Два способа запуска одной и той же модели.

База: `data/apartments.xlsx`.

## Публикация на Streamlit

На share.streamlit.io укажите репозиторий `armanhak/realty-estimator`, ветку `streamlit-v2`, файл `app.py`.

Локально:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Откроется http://localhost:8501

## Сайт из документа

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

Откроется http://127.0.0.1:8000

Ветка `main` — более ранняя версия без поиска дома. Её тоже можно опубликовать отдельным приложением Streamlit: ветка `main`, файл `app.py`.
