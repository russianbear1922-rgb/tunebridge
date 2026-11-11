"""Публичные юридические страницы: политика конфиденциальности и условия использования.

Текст описывает то, что приложение действительно делает: вход через Telegram,
зашифрованные подключения сервисов, история переносов, реклама и отсутствие
скачивания аудио. Меняете поведение приложения — обновите и этот текст.
"""

from __future__ import annotations

from html import escape

from . import config

UPDATED = "2026-11-11"

Section = dict[str, object]


def _contact() -> tuple[str, str]:
    """Пара (подпись, ссылка) для связи с оператором."""
    if config.CONTACT_EMAIL:
        return config.CONTACT_EMAIL, f"mailto:{config.CONTACT_EMAIL}"
    handle = config.CONTACT_TELEGRAM or (config.BOT_USERNAME if config.HOSTED else "")
    if handle:
        return f"@{handle}", f"https://t.me/{handle}"
    return "", ""


def _content(kind: str, lang: str) -> list[Section]:
    if kind == "privacy":
        return _PRIVACY_RU if lang == "ru" else _PRIVACY_EN
    return _TERMS_RU if lang == "ru" else _TERMS_EN


_TITLES = {
    "privacy": {"ru": "Политика конфиденциальности", "en": "Privacy Policy"},
    "terms": {"ru": "Условия использования", "en": "Terms of Service"},
}

_LEADS = {
    "privacy": {
        "ru": "Что TuneBridge хранит, зачем и как это удалить.",
        "en": "What TuneBridge stores, why, and how to delete it.",
    },
    "terms": {
        "ru": "Правила пользования сервисом переноса плейлистов.",
        "en": "Rules for using the playlist transfer service.",
    },
}

_SUMMARY = {
    "privacy": {
        "ru": [
            "Мы не скачиваем и не храним музыку — только названия треков для переноса.",
            "Токены музыкальных сервисов хранятся зашифрованными и видны только вам.",
            "Реклама считается обезличенно: показы и клики без идентификаторов.",
        ],
        "en": [
            "We never download or store music — only track names needed for the transfer.",
            "Music service tokens are stored encrypted and are visible only to you.",
            "Ad counters are anonymous: impressions and clicks without identifiers.",
        ],
    },
    "terms": {
        "ru": [
            "Сервис бесплатный и показывается реклама; перенос идёт через официальные API сервисов.",
            "Вы отвечаете за права на контент своих плейлистов и за свой аккаунт.",
            "Сервис предоставляется «как есть», без гарантии стопроцентного совпадения треков.",
        ],
        "en": [
            "The service is free and ad-supported; transfers use the official APIs of each service.",
            "You are responsible for the rights to your playlist content and for your account.",
            "The service is provided “as is”, without a guarantee of perfect track matching.",
        ],
    },
}

_PRIVACY_RU: list[Section] = [
    {
        "title": "1. Кто обрабатывает данные",
        "body": [
            "Оператор сервиса TuneBridge (далее — «сервис», «мы»). Сервис переносит плейлисты между "
            "музыкальными платформами: Яндекс Музыка, Spotify, YouTube Music, SoundCloud, Apple Music.",
            "По вопросам о данных пишите на контакт, указанный внизу страницы.",
        ],
    },
    {
        "title": "2. Какие данные мы обрабатываем",
        "body": [
            {"list": [
                "<b>Данные Telegram.</b> При входе через Mini App мы получаем ваш идентификатор Telegram, "
                "имя, username и язык интерфейса. Пароль Telegram мы не получаем и не храним.",
                "<b>Сессия.</b> Одна cookie <span class=\"mono\">tb_session</span> со случайным идентификатором "
                "и срок действия до 30 дней, а также CSRF-токен для защиты действий. Строка User-Agent браузера.",
                "<b>Подключения музыкальных сервисов.</b> Токены Spotify, заголовки и cookie YouTube Music, "
                "токен Яндекс Музыки, токен вашего Telegram-бота для отправки плейлистов. В облачном режиме они "
                "хранятся в зашифрованном виде (AES/Fernet) отдельно для каждого пользователя; в локальном режиме — "
                "в папке <span class=\"mono\">data/</span> на вашем компьютере.",
                "<b>Переносы.</b> Название и ссылка плейлиста-источника, сервис-цель, количество добавленных треков "
                "и дата. Список треков живёт в памяти сервера только на время задачи (до 6 часов) и не сохраняется в базу.",
                "<b>Платежи (только в платном режиме).</b> Заказы, суммы в Telegram Stars и идентификаторы платежей "
                "Telegram. Данные банковских карт мы не получаем и не храним.",
                "<b>Технические журналы.</b> Время запроса, путь, код ответа и IP-адрес для защиты от злоупотреблений. "
                "Токены, cookie и содержимое плейлистов в журналы не пишутся.",
                "<b>Реклама.</b> Обезличенные счётчики показов и кликов по рекламному блоку: дата, тип события, количество. "
                "Без идентификаторов пользователя, без рекламных cookie и без профилирования.",
                "<b>В браузере.</b> Выбранный язык и история переносов хранятся локально (localStorage) и не отправляются "
                "на сервер, кроме самих записей о переносах в вашем аккаунте.",
            ]},
        ],
    },
    {
        "title": "3. Зачем мы это делаем",
        "body": [
            {"list": [
                "вход в аккаунт и защита от подделки запросов;",
                "перенос плейлистов по вашему действию и показ прогресса;",
                "история переносов и поддержка, если что-то пошло не так;",
                "учёт оплат и возвратов в платном режиме;",
                "ограничение нагрузки и защита от автоматизированных злоупотреблений;",
                "понимание, сколько людей видит рекламный блок, — в обезличенном виде.",
            ]},
            "Правовое основание — ваше согласие (вход и подключение сервисов) и исполнение договора об использовании сервиса.",
        ],
    },
    {
        "title": "4. Кому передаются данные",
        "body": [
            {"list": [
                "<b>Музыкальные сервисы</b> — только те запросы, которые нужны для переноса: поиск трека, создание "
                "плейлиста, добавление треков. Запросы идут от вашего имени через ваш аккаунт.",
                "<b>Telegram</b> — вход Mini App, отправка списка треков и архива в выбранный вами чат, платежи Stars "
                "в платном режиме.",
                "<b>Хостинг-провайдер</b> — сервер, на котором работает сервис, обрабатывает запросы как инфраструктура.",
                "<b>Рекламодатель</b> — получает только факт перехода по ссылке. Ваши данные, плейлисты и идентификаторы "
                "ему не передаются.",
            ]},
            "Мы не продаём персональные данные и не передаём их для сторонней рекламы или аналитики.",
        ],
    },
    {
        "title": "5. Сколько хранятся данные",
        "body": [
            {"list": [
                "подключения сервисов — пока вы их не отключите в кабинете: отключение удаляет сохранённые токены;",
                "история переносов и аккаунт — пока вы не попросите удалить аккаунт;",
                "сессия — до 30 дней или до выхода из аккаунта;",
                "списки треков текущей задачи — в памяти до 6 часов;",
                "архивы экспорта — формируются в памяти и сразу отдаются вам или в Telegram, на диске не остаются;",
                "резервные копии базы — до 14 дней, затем удаляются;",
                "обезличенные счётчики рекламы — агрегированные значения по дням.",
            ]},
        ],
    },
    {
        "title": "6. Как мы защищаем данные",
        "body": [
            "HTTPS, шифрование подключений сервисов отдельным ключом, изоляция данных по пользователям, "
            "CSRF-защита, ограничение частоты запросов, отсутствие токенов в журналах. Доступ к серверу есть "
            "только у оператора. Полностью исключить риск при передаче данных через интернет невозможно — "
            "подключайте только те сервисы, которыми готовы поделиться с сервисом переноса.",
        ],
    },
    {
        "title": "7. Ваши права",
        "body": [
            {"list": [
                "посмотреть свои данные — кабинет и история переносов;",
                "удалить подключения — кнопка отключения сервиса в кабинете;",
                "удалить аккаунт и все связанные данные — запрос на контакт внизу страницы;",
                "отозвать согласие — выйти из аккаунта и отключить сервисы; после этого переносы недоступны.",
            ]},
            "Запросы на удаление мы выполняем в течение 30 дней. Резервные копии перезаписываются в течение 14 дней.",
        ],
    },
    {
        "title": "8. Дети",
        "body": [
            "Сервис не предназначен для детей младше 13 лет. Если вы считаете, что ребёнок младше 13 лет "
            "передал нам данные, напишите нам — мы их удалим.",
        ],
    },
    {
        "title": "9. Cookie и аналитика",
        "body": [
            "Мы используем одну техническую cookie для входа. Рекламных и аналитических cookie нет, "
            "сторонние счётчики и пиксели не подключены. Рекламный блок — наш собственный, он ведёт на сайт "
            "рекламодателя только по вашему клику.",
        ],
    },
    {
        "title": "10. Изменения политики",
        "body": [
            "Мы можем обновлять эту политику. Актуальная версия всегда доступна по адресу "
            "<span class=\"mono\">/privacy</span>, дата обновления указана внизу страницы. "
            "Существенные изменения мы дополнительно показываем в интерфейсе.",
        ],
    },
]

_PRIVACY_EN: list[Section] = [
    {
        "title": "1. Who processes your data",
        "body": [
            "The operator of TuneBridge (the “service”, “we”). The service transfers playlists between music "
            "platforms: Yandex Music, Spotify, YouTube Music, SoundCloud and Apple Music.",
            "For data questions, use the contact at the bottom of this page.",
        ],
    },
    {
        "title": "2. What we process",
        "body": [
            {"list": [
                "<b>Telegram data.</b> When you sign in through the Mini App we receive your Telegram id, name, "
                "username and interface language. We never receive or store your Telegram password.",
                "<b>Session.</b> A single <span class=\"mono\">tb_session</span> cookie with a random identifier, "
                "valid up to 30 days, plus a CSRF token that protects your actions. Your browser User-Agent string.",
                "<b>Music service connections.</b> Spotify tokens, YouTube Music headers and cookies, a Yandex Music "
                "token, and the token of your own Telegram bot used to deliver playlists. In hosted mode they are "
                "stored encrypted (AES/Fernet) per user; in local mode they stay in the <span class=\"mono\">data/</span> "
                "folder on your computer.",
                "<b>Transfers.</b> Source playlist title and URL, target service, number of added tracks and the date. "
                "The track list itself lives in server memory only while the job runs (up to 6 hours) and is not "
                "written to the database.",
                "<b>Payments (paid mode only).</b> Orders, Telegram Stars amounts and Telegram payment identifiers. "
                "We never receive or store bank card details.",
                "<b>Technical logs.</b> Request time, path, response code and IP address, used to prevent abuse. "
                "Tokens, cookies and playlist contents are never logged.",
                "<b>Ads.</b> Anonymous counters of ad impressions and clicks: date, event type, count. No user "
                "identifiers, no advertising cookies, no profiling.",
                "<b>In your browser.</b> Your language choice and transfer history are kept locally (localStorage) "
                "and are not sent to the server, apart from the transfer records in your account.",
            ]},
        ],
    },
    {
        "title": "3. Why we process it",
        "body": [
            {"list": [
                "to sign you in and protect requests from forgery;",
                "to transfer playlists when you ask and show progress;",
                "to keep transfer history and help you when something fails;",
                "to account for payments and refunds in paid mode;",
                "to limit load and prevent automated abuse;",
                "to understand how many people see the ad block — in anonymous form.",
            ]},
            "The legal basis is your consent (signing in and connecting services) and performance of the terms of use.",
        ],
    },
    {
        "title": "4. Who receives data",
        "body": [
            {"list": [
                "<b>Music services</b> — only the requests needed for the transfer: searching a track, creating a "
                "playlist, adding tracks. They are made on your behalf through your account.",
                "<b>Telegram</b> — Mini App sign-in, delivery of the track list and archive to the chat you choose, "
                "and Stars payments in paid mode.",
                "<b>Hosting provider</b> — the server running the service processes requests as infrastructure.",
                "<b>Advertiser</b> — receives only the fact that you clicked the link. Your data, playlists and "
                "identifiers are not shared with them.",
            ]},
            "We do not sell personal data and do not share it for third-party advertising or analytics.",
        ],
    },
    {
        "title": "5. How long we keep it",
        "body": [
            {"list": [
                "service connections — until you disconnect them in the cabinet; disconnecting deletes stored tokens;",
                "transfer history and account — until you ask us to delete the account;",
                "session — up to 30 days or until you sign out;",
                "track lists of the current job — in memory for up to 6 hours;",
                "export archives — built in memory and handed to you or to Telegram immediately, never left on disk;",
                "database backups — up to 14 days, then deleted;",
                "anonymous ad counters — daily aggregates.",
            ]},
        ],
    },
    {
        "title": "6. How we protect it",
        "body": [
            "HTTPS, encryption of service connections with a dedicated key, per-user isolation, CSRF protection, "
            "request rate limits and no tokens in logs. Only the operator has server access. No internet transmission "
            "can be made risk-free — connect only the services you are comfortable sharing with a transfer tool.",
        ],
    },
    {
        "title": "7. Your rights",
        "body": [
            {"list": [
                "see your data — the cabinet and transfer history;",
                "delete connections — the disconnect button in the cabinet;",
                "delete your account and all related data — request via the contact below;",
                "withdraw consent — sign out and disconnect services; transfers then become unavailable.",
            ]},
            "We complete deletion requests within 30 days. Backups are overwritten within 14 days.",
        ],
    },
    {
        "title": "8. Children",
        "body": [
            "The service is not intended for children under 13. If you believe a child under 13 has given us data, "
            "contact us and we will delete it.",
        ],
    },
    {
        "title": "9. Cookies and analytics",
        "body": [
            "We use one technical cookie for sign-in. There are no advertising or analytics cookies and no third-party "
            "counters or pixels. The ad block is our own and leads to the advertiser's site only when you click it.",
        ],
    },
    {
        "title": "10. Changes to this policy",
        "body": [
            "We may update this policy. The current version is always available at <span class=\"mono\">/privacy</span>; "
            "the update date is at the bottom of the page. Material changes are also announced in the interface.",
        ],
    },
]

_TERMS_RU: list[Section] = [
    {
        "title": "1. Что такое TuneBridge",
        "body": [
            "TuneBridge — инструмент переноса плейлистов между музыкальными сервисами. Он сопоставляет треки по "
            "названию, исполнителю и длительности и создаёт плейлист в выбранном сервисе через его официальный API. "
            "Сервис не скачивает, не хранит и не распространяет аудиофайлы.",
            "Используя сервис, вы соглашаетесь с этими условиями и с политикой конфиденциальности "
            "(<a href=\"/privacy\">/privacy</a>).",
        ],
    },
    {
        "title": "2. Аккаунт и вход",
        "body": [
            "В облачном режиме вход выполняется через Telegram Mini App. Вы отвечаете за сохранность своего аккаунта "
            "Telegram и за действия, совершённые через него. Подключая музыкальный сервис, вы подтверждаете, что "
            "имеете право использовать этот аккаунт и разрешаете сервису выполнять перенос от вашего имени.",
        ],
    },
    {
        "title": "3. Правила использования",
        "body": [
            {"list": [
                "не нарушайте права третьих лиц: переносите только те плейлисты, на которые у вас есть права;",
                "не используйте сервис для спама, массовой автоматической нагрузки или обхода ограничений платформ;",
                "не пытайтесь обходить DRM, скачивать аудио или извлекать контент в обход правил музыкальных сервисов;",
                "не вмешивайтесь в работу сервера, не подбирайте чужие сессии и не эксплуатируйте уязвимости;",
                "соблюдайте условия использования Spotify, YouTube Music, Яндекс Музыки, SoundCloud и Apple Music.",
            ]},
            "Нарушение правил может привести к ограничению или прекращению доступа без компенсации.",
        ],
    },
    {
        "title": "4. Ограничения сервиса",
        "body": [
            {"list": [
                "до 2000 треков за один перенос;",
                "лимиты частоты запросов для защиты сервера и сторонних API;",
                "точность сопоставления зависит от каталогов сервисов: часть треков может не найтись или отличаться "
                "версией (ремикс, live, clean);",
                "доступность зависит от сторонних платформ — их сбои, лимиты и изменения API вне нашего контроля.",
            ]},
            "Перед переносом вы видите список совпадений и можете подтвердить, заменить или исключить треки.",
        ],
    },
    {
        "title": "5. Бесплатный режим и реклама",
        "body": [
            "Сервис предоставляется бесплатно. Чтобы покрывать расходы на сервер, в интерфейсе показывается рекламный "
            "блок. Реклама помечена словом «Реклама» и ведёт на сторонний сайт только по вашему клику. Мы не отвечаем "
            "за содержание сайтов рекламодателей, их товары и условия. Переходя по рекламной ссылке, вы покидаете сервис.",
        ],
    },
    {
        "title": "6. Платный режим",
        "body": [
            "Если оператор включает платный режим, переносы оплачиваются внутренней валютой — токенами (один трек = "
            "один токен). Пополнение возможно через Telegram Stars. За неудачные совпадения и отменённый перенос "
            "токены возвращаются автоматически. Возврат средств Telegram Stars регулируется правилами Telegram; "
            "спорные случаи решает оператор вручную.",
        ],
    },
    {
        "title": "7. Отказ от гарантий",
        "body": [
            "Сервис предоставляется «как есть» и «как доступен». Мы не гарантируем бесперебойную работу, полное "
            "совпадение каталогов, сохранность плейлистов в сторонних сервисах или отсутствие ошибок. Рекомендуем "
            "экспортировать плейлист в файл перед переносом — такая возможность встроена в сервис.",
        ],
    },
    {
        "title": "8. Ответственность",
        "body": [
            "Мы не несём ответственности за косвенные убытки, упущенную выгоду, потерю данных в сторонних сервисах, "
            "блокировки аккаунтов музыкальных платформ или действия рекламодателей. Наша ответственность ограничена "
            "суммой, фактически уплаченной вами за сервис за последние 3 месяца (в бесплатном режиме — нулю), "
            "в пределах, допустимых применимым законодательством.",
        ],
    },
    {
        "title": "9. Интеллектуальная собственность",
        "body": [
            "Права на музыкальные произведения, обложки и товарные знаки принадлежат их правообладателям. Сервис "
            "работает только с метаданными плейлистов (названия, исполнители, длительность, ссылки) и не создаёт "
            "копий аудио. Название и оформление TuneBridge принадлежат оператору.",
        ],
    },
    {
        "title": "10. Прекращение доступа",
        "body": [
            "Вы можете в любой момент выйти из аккаунта, отключить сервисы и запросить удаление аккаунта. Мы можем "
            "приостановить или прекратить доступ при нарушении этих условий, злоупотреблении нагрузкой или требовании "
            "закона. Мы можем изменить или закрыть сервис, предупредив об этом в интерфейсе.",
        ],
    },
    {
        "title": "11. Применимое право и споры",
        "body": [
            "К отношениям сторон применяется законодательство Российской Федерации, если иное не установлено "
            "императивными нормами страны вашего проживания. Споры решаются путём переговоров, при недостижении "
            "согласия — в компетентном суде по месту нахождения оператора.",
        ],
    },
    {
        "title": "12. Изменения условий",
        "body": [
            "Мы можем обновлять эти условия. Актуальная версия доступна по адресу <span class=\"mono\">/terms</span>, "
            "дата обновления указана внизу. Продолжая пользоваться сервисом после изменений, вы принимаете новую редакцию.",
        ],
    },
]

_TERMS_EN: list[Section] = [
    {
        "title": "1. What TuneBridge is",
        "body": [
            "TuneBridge is a tool that transfers playlists between music services. It matches tracks by title, artist "
            "and duration and creates a playlist in the chosen service through its official API. The service does not "
            "download, store or distribute audio files.",
            "By using the service you agree to these terms and to the privacy policy "
            "(<a href=\"/privacy\">/privacy</a>).",
        ],
    },
    {
        "title": "2. Account and sign-in",
        "body": [
            "In hosted mode you sign in through the Telegram Mini App. You are responsible for keeping your Telegram "
            "account secure and for actions performed through it. By connecting a music service you confirm that you "
            "are entitled to use that account and allow the service to perform transfers on your behalf.",
        ],
    },
    {
        "title": "3. Acceptable use",
        "body": [
            {"list": [
                "do not infringe third-party rights: transfer only playlists you are entitled to;",
                "do not use the service for spam, mass automated load or to bypass platform limits;",
                "do not attempt to circumvent DRM, download audio or extract content against music services' rules;",
                "do not interfere with the server, guess other users' sessions or exploit vulnerabilities;",
                "respect the terms of Spotify, YouTube Music, Yandex Music, SoundCloud and Apple Music.",
            ]},
            "Breaking these rules may lead to restricted or terminated access without compensation.",
        ],
    },
    {
        "title": "4. Service limits",
        "body": [
            {"list": [
                "up to 2000 tracks per transfer;",
                "request rate limits that protect the server and third-party APIs;",
                "matching accuracy depends on each catalogue: some tracks may be missing or differ in version "
                "(remix, live, clean);",
                "availability depends on third-party platforms — their outages, quotas and API changes are outside "
                "our control.",
            ]},
            "Before transferring you see the match list and can confirm, replace or exclude tracks.",
        ],
    },
    {
        "title": "5. Free mode and advertising",
        "body": [
            "The service is free. To cover server costs an ad block is shown in the interface. Ads are labelled “Ad” "
            "and lead to a third-party site only when you click. We are not responsible for advertisers' sites, "
            "products or terms. Clicking an ad link takes you outside the service.",
        ],
    },
    {
        "title": "6. Paid mode",
        "body": [
            "If the operator enables paid mode, transfers are paid with internal tokens (one track = one token). "
            "Top-ups are made with Telegram Stars. Tokens for failed matches and cancelled transfers are refunded "
            "automatically. Telegram Stars refunds follow Telegram's rules; disputed cases are handled manually by "
            "the operator.",
        ],
    },
    {
        "title": "7. No warranty",
        "body": [
            "The service is provided “as is” and “as available”. We do not guarantee uninterrupted operation, complete "
            "catalogue overlap, preservation of playlists in third-party services, or absence of errors. We recommend "
            "exporting your playlist to a file before transferring — the service has this built in.",
        ],
    },
    {
        "title": "8. Liability",
        "body": [
            "We are not liable for indirect damages, lost profits, data loss in third-party services, bans of music "
            "platform accounts or advertisers' actions. Our liability is limited to the amount you actually paid for "
            "the service in the last 3 months (zero in free mode), to the extent permitted by applicable law.",
        ],
    },
    {
        "title": "9. Intellectual property",
        "body": [
            "Rights to music, artwork and trademarks belong to their owners. The service works only with playlist "
            "metadata (titles, artists, durations, links) and creates no copies of audio. The TuneBridge name and "
            "design belong to the operator.",
        ],
    },
    {
        "title": "10. Termination",
        "body": [
            "You may sign out, disconnect services and request account deletion at any time. We may suspend or "
            "terminate access for breaches of these terms, abusive load or legal requirements. We may change or close "
            "the service with notice in the interface.",
        ],
    },
    {
        "title": "11. Governing law and disputes",
        "body": [
            "These terms are governed by the laws of the Russian Federation, unless mandatory rules of your country "
            "of residence provide otherwise. Disputes are resolved by negotiation and, failing that, by the competent "
            "court at the operator's location.",
        ],
    },
    {
        "title": "12. Changes to the terms",
        "body": [
            "We may update these terms. The current version is available at <span class=\"mono\">/terms</span> with "
            "the update date below. Continuing to use the service after changes means you accept the new version.",
        ],
    },
]


def _body_html(body: list[object]) -> str:
    parts: list[str] = []
    for item in body:
        if isinstance(item, dict) and "list" in item:
            entries = "".join(f"<li>{entry}</li>" for entry in item["list"])  # type: ignore[union-attr]
            parts.append(f"<ul>{entries}</ul>")
        else:
            parts.append(f"<p>{item}</p>")
    return "".join(parts)


def render(kind: str, lang: str = "ru") -> str:
    """Готовая HTML-страница. Тексты внутри — наши собственные, экранируется только ввод пользователя."""
    lang = "en" if lang == "en" else "ru"
    if kind not in _TITLES:
        raise ValueError(kind)
    title = _TITLES[kind][lang]
    lead = _LEADS[kind][lang]
    sections = _content(kind, lang)
    contact_label, contact_href = _contact()
    other = "en" if lang == "ru" else "ru"
    other_label = "English version" if lang == "ru" else "Русская версия"
    back = "Вернуться в TuneBridge" if lang == "ru" else "Back to TuneBridge"
    updated = "Обновлено" if lang == "ru" else "Updated"
    operator = "Оператор" if lang == "ru" else "Operator"
    contact_title = "Связаться" if lang == "ru" else "Contact"
    privacy_on = ' class="is-on"' if kind == "privacy" else ""
    terms_on = ' class="is-on"' if kind == "terms" else ""
    summary = "".join(f"<li>{item}</li>" for item in _SUMMARY[kind][lang])
    articles = "".join(
        f"<section><h2>{escape(str(section['title']))}</h2>{_body_html(section['body'])}</section>"  # type: ignore[arg-type]
        for section in sections
    )
    contact_html = (
        f'<a class="legal-contact" href="{escape(contact_href, quote=True)}">{escape(contact_label)}</a>'
        if contact_href
        else f'<span class="legal-contact dim">{escape(config.APP_NAME)}</span>'
    )
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#08090f">
<meta name="robots" content="index, follow">
<title>{escape(title)} — {escape(config.APP_NAME)}</title>
<meta name="description" content="{escape(lead)}">
<link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
<link rel="canonical" href="{escape(config.BASE_URL.rstrip('/') + '/' + kind, quote=True)}">
<link rel="stylesheet" href="/static/css/legal.css">
</head>
<body>
<main class="legal">
  <header class="legal-head">
    <a class="legal-brand" href="/"><img src="/static/img/logo.svg" alt=""><span>{escape(config.APP_NAME)}</span></a>
    <nav class="legal-nav">
      <a href="/privacy"{privacy_on}>{escape(_TITLES["privacy"][lang])}</a>
      <a href="/terms"{terms_on}>{escape(_TITLES["terms"][lang])}</a>
      <a href="/{kind}?lang={other}">{escape(other_label)}</a>
    </nav>
  </header>
  <h1>{escape(title)}</h1>
  <p class="legal-lead">{escape(lead)}</p>
  <ul class="legal-summary">{summary}</ul>
  {articles}
  <footer class="legal-foot">
    <div class="legal-foot-row">
      <span class="dim">{operator}: {escape(config.OPERATOR_NAME)}</span>
      <span class="dim">{contact_title}: {contact_html}</span>
    </div>
    <div class="legal-foot-row">
      <span class="dim">{updated}: {UPDATED}</span>
      <a href="/">{escape(back)}</a>
    </div>
  </footer>
</main>
</body>
</html>
"""