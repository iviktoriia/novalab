# 🎓 NovaLab

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white)
![Jinja2](https://img.shields.io/badge/Jinja2-B41717?style=flat-square&logo=jinja&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

Веб-платформа для обучения: единое пространство для администратора, преподавателей и студентов — дисциплины, материалы, задания, сдача работ и оценка.

## ✨ Возможности

- 👩‍🏫 **Роли** — админ, преподаватель и студент с отдельными кабинетами
- 📚 **Дисциплины и материалы** — загрузка файлов, привязка к группам
- 📝 **Задания** — дедлайны, файлы-приложения, проверка сдач
- 📤 **Сдача работ** — файлы и/или ссылка на GitHub, пересдача до оценки
- 👥 **Группы** — саморегистрация по коду или автосоздание студентов
- 📊 **Аттестация** — оценки, обратная связь, прогноз по дисциплине
- ☁️ **Хранилище** — локальные файлы или S3 (Timeweb и совместимые)
- 🗑️ **Удаление** — soft-delete в БД + очистка файлов из хранилища

## 🛠️ Технологии

- **Backend:** Python, FastAPI, SQLAlchemy, Pydantic, Jinja2
- **Auth:** сессии (cookie), bcrypt
- **БД:** SQLite (по умолчанию) / PostgreSQL
- **Файлы:** локальные каталоги или Amazon S3–совместимое API (boto3)
- **Опционально:** сервис анализа кода Codect

## 🗺️ Roadmap

- Уведомления о дедлайнах
- Импорт студентов из Excel/CSV
- Расширенная аналитика по группам и дисциплинам

## 📄 Лицензия
MIT License
Copyright (c) 2026 Viktoriia Ivanova (iviktoriia)

---

**Важное примечание**: Данный проект создан исключительно в образовательных/личных целях. 
