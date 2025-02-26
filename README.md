# Siriust Parser
Этот проект предназначен для парсинга данных с сайта [Siriust](https://siriust.ru/) и сохранения их в базе данных PostgreSQL.

## Функциональность
- Парсинг профиля пользователя и Wishlist.
- Сохранение данных в базе данных PostgreSQL.
- Создание таблиц для хранения данных о пользователях, товарах и отзывах.

## Требования
- Python 3.x
- Библиотеки: `requests`, `lxml`, `psycopg2`
- PostgreSQL

## Установка
1. Клонировать репозиторий.
2. Установить необходимые библиотеки: `pip install -r requirements.txt`
3. Создать базу данных PostgreSQL и заменить `DB_NAME`, `NAME_USER`, `PASSWORD` в коде на свои данные.
```commandline
conn = psycopg2.connect(
    dbname="DB_NAME",
    user="NAME_USER",  
    password="PASSWORD",  
    host="localhost",
    port="5432"
)

```

## Использование
1. Запустить скрипт: `python main.py`
2. Ввести email и пароль для авторизации на сайте Siriust.

