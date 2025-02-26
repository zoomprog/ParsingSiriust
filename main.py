import requests
from lxml import html
import re
import psycopg2
import logging
import os
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из .env
load_dotenv()

# Получение значений из .env
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")  # Значение по умолчанию: localhost
DB_PORT = os.getenv("DB_PORT", "5432")       # Значение по умолчанию: 5432


def parse_and_save_to_db(email, password):
    # URL для отправки POST-запроса
    login_url = "https://siriust.ru/"
    profile_url = "https://siriust.ru/profiles-update/"
    wishlist_url = "https://siriust.ru/wishlist/"

    # Данные для авторизации
    payload = {
        "user_login": email,  # Логин пользователя
        "password": password,  # Пароль пользователя
        "return_url": "index.php",
        "redirect_url": "index.php",
        "dispatch[auth.login]": "Войти"  # Имя кнопки "Войти"
    }

    # Заголовки для имитации реального пользователя
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://siriust.ru/",
    }

    # Создаем сессию для сохранения кук после авторизации
    session = requests.Session()

    try:
        # Отправляем POST-запрос с данными авторизации
        response = session.post(login_url, data=payload, headers=headers)

        # Проверяем результат авторизации
        if response.status_code == 200:
            # Проверяем наличие сообщения об ошибке в HTML-ответе
            if "Вы ввели неверный логин или пароль" in response.text:
                logger.error("Неверный логин или пароль. Пожалуйста, попробуйте еще раз.")
                return  # Прекращаем выполнение функции

            logger.info("Авторизация успешна!")
        else:
            logger.error(f"Ошибка авторизации. Код ошибки: {response.status_code}")
            return

        # Получаем данные профиля
        profile_response = session.get(profile_url, headers=headers)
        if profile_response.status_code == 200:
            tree = html.fromstring(profile_response.text)

            # Находим email, имя, фамилию и регион
            email_input = tree.xpath('//input[@name="user_data[email]"]/@value')
            firstname_input = tree.xpath('//input[@name="user_data[s_firstname]"]/@value')
            lastname_input = tree.xpath('//input[@name="user_data[s_lastname]"]/@value')
            selected_region_input = tree.xpath('//select[@name="user_data[s_state]"]/option[@selected]/text()')

            email = email_input[0] if email_input else "Email not found"
            firstname = firstname_input[0] if firstname_input else "Firstname not found"
            lastname = lastname_input[0] if lastname_input else "Lastname not found"
            selected_region = selected_region_input[0] if selected_region_input else "Region not found"

        else:
            logger.error(f"Не удалось получить доступ к странице профиля. Код ошибки: {profile_response.status_code}")
            return

        # Получаем данные wishlist'a
        wishlist_response = session.get(wishlist_url, headers=headers)
        if wishlist_response.status_code == 200:
            tree = html.fromstring(wishlist_response.text)
            product_links = tree.xpath('//a[@class="abt-single-image"]')
        else:
            logger.error(f"Не удалось получить доступ к странице Вишлиста. Код ошибки: {wishlist_response.status_code}")
            return

        # Подключение к базе данных PostgreSQL
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,  # Замените на имя пользователя PostgreSQL
            password=DB_PASSWORD,  # Замените на пароль PostgreSQL
            host=DB_HOST,
            port=DB_PORT
        )
        cur = conn.cursor()
        conn.set_client_encoding('UTF8')

        try:
            # Создание таблиц, если их нет
            cur.execute("""
                CREATE TABLE IF NOT EXISTS пользователи (
                    id SERIAL PRIMARY KEY,
                    почта VARCHAR(255) NOT NULL UNIQUE,  -- Поле должно быть уникальным
                    имя VARCHAR(255),
                    фамилия VARCHAR(255),
                    регион VARCHAR(255)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS товары (
                    id SERIAL PRIMARY KEY,
                    пользователь_id INTEGER REFERENCES пользователи(id),
                    название VARCHAR(255) NOT NULL,
                    розничная_цена DECIMAL(10, 2),
                    оптовая_цена DECIMAL(10, 2),
                    рейтинг NUMERIC(3, 1),
                    количество_отзывов INTEGER,
                    доступно_в_магазинах INTEGER
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS отзывы (
                    id SERIAL PRIMARY KEY,
                    товар_id INTEGER REFERENCES товары(id),
                    текст_отзыва TEXT NOT NULL UNIQUE  -- Поле должно быть уникальным
                );
            """)

            # Проверка существования пользователя
            cur.execute("SELECT id FROM пользователи WHERE почта = %s;", (email,))
            existing_user = cur.fetchone()

            if existing_user:
                user_id = existing_user[0]
                logger.info(f"Пользователь с email {email} уже существует.")
            else:
                # Вставка данных пользователя
                cur.execute("""
                    INSERT INTO пользователи (почта, имя, фамилия, регион)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                """, (email, firstname, lastname, selected_region))
                user_id = cur.fetchone()[0]
                logger.info(f"Добавлен новый пользователь с email {email}.")

            # Обработка каждого товара
            for link in product_links:
                href = link.attrib.get('href', '')
                img_element = link.xpath('.//img')[0] if link.xpath('.//img') else None

                if img_element is not None:
                    img_src = img_element.attrib.get('src', '')

                    # Получение данных о товаре
                    product_page_response = session.get(href, headers=headers)

                    if product_page_response.status_code == 200:
                        product_tree = html.fromstring(product_page_response.text)
                        # Название товара
                        h1_title = product_tree.xpath('//h1[@class="ty-product-block-title"]/bdi/text()')
                        # Розничная цена
                        retail_price = product_tree.xpath('//span[@class="ty-price-num"]/text()')
                        # Оптовая цена
                        wholesale_price_container = product_tree.xpath('//div[@class="ty-product-block__price-second"]//span[@class="ty-price-num"]/text()')
                        # Рейтинг
                        full_stars = product_tree.xpath('//div[@class="ty-discussion__rating-wrapper"]//i[@class="ty-stars__icon ty-icon-star"]')
                        half_star = product_tree.xpath('//div[@class="ty-discussion__rating-wrapper"]//i[@class="ty-stars__icon ty-icon-star-half"]')
                        # Количество отзывов
                        number_reviews = product_tree.xpath('//a[@class="ty-discussion__review-a cm-external-click"]')
                        # Доступно в магазинах
                        store_count = product_tree.xpath('//div[@class="ty-product-feature"]//div[@class="ty-product-feature__value"]')
                        # Отзывы
                        reviews = product_tree.xpath('//div[@class="ty-discussion-post__message"]/text()')

                        title = h1_title[0].strip() if h1_title else "Название не найдено"
                        retail_price = retail_price[0].replace('\xa0', '').strip() if retail_price else None
                        wholesale_price = wholesale_price_container[0].replace('\xa0', '').strip() if wholesale_price_container else None
                        rating = len(full_stars) + 0.5 if half_star else len(full_stars)
                        reviews_count = int(re.search(r'\d+', number_reviews[0].text.strip()).group()) if number_reviews else 0
                        available_stores_count = sum("мало" in store.text_content() or "достаточно" in store.text_content() or "много" in store.text_content() for store in store_count)

                        # Проверка существования товара
                        cur.execute("SELECT id FROM товары WHERE название = %s AND пользователь_id = %s;", (title, user_id))
                        existing_product = cur.fetchone()

                        if existing_product:
                            product_id = existing_product[0]
                            logger.info(f"Товар '{title}' уже существует для данного пользователя.")
                        else:
                            # Вставка данных о товаре
                            cur.execute("""
                                INSERT INTO товары (пользователь_id, название, розничная_цена, оптовая_цена, рейтинг, количество_отзывов, доступно_в_магазинах)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                RETURNING id;
                            """, (
                                user_id, title, retail_price, wholesale_price, rating, reviews_count, available_stores_count))
                            product_id = cur.fetchone()[0]
                            logger.info(f"Добавлен новый товар: '{title}'.")

                        # Вставка отзывов
                        for review in reviews:
                            cleaned_review = review.strip()

                            if cleaned_review:
                                # Проверка существования отзыва
                                cur.execute("SELECT id FROM отзывы WHERE текст_отзыва = %s AND товар_id = %s;", (cleaned_review, product_id))
                                existing_review = cur.fetchone()

                                if existing_review:
                                    logger.info(f"Отзыв '{cleaned_review[:20]}...' уже существует для товара '{title}'.")
                                else:
                                    cur.execute("""
                                        INSERT INTO отзывы (товар_id, текст_отзыва)
                                        VALUES (%s, %s);
                                    """, (product_id, cleaned_review))
                                    logger.info(f"Добавлен новый отзыв для товара '{title}'.")

            # Сохранение изменений
            conn.commit()
            logger.info("Данные успешно записаны в базу данных.")

        except Exception as e:
            logger.error(f"Ошибка при записи в базу данных: {e}")
            conn.rollback()

        finally:
            cur.close()
            conn.close()

    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")

# Пример использования функции
if __name__ == "__main__":
    email = input("Введите ваш email: ")
    password = input("Введите ваш пароль: ")
    parse_and_save_to_db(email, password)