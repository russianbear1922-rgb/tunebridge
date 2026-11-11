import { getLang } from "./i18n.js";

// The backend speaks Russian. This module translates the user-facing parts of
// its messages for the English UI; unknown strings fall through unchanged.
const EXACT = {
  "Готово": "Done",
  "Задача остановлена": "Job stopped",
  "Останавливаем…": "Stopping…",
  "Запрошена остановка": "Stop requested",
  "Яндекс Музыка": "Yandex Music",
  "Яндекс Музыке": "Yandex Music",
  "Яндекс Музыку": "Yandex Music",
  "Яндекс Музыки": "Yandex Music",
  "Яндекс Музыкой": "Yandex Music",
  "Демо-плеер": "Demo player",
  "Демо": "Demo",
  "Файл": "File",
  "Внутренняя ошибка": "Internal error",
  "Плейлист создан, добавляем треки": "Playlist created, adding tracks",
  "Нет треков для переноса": "No tracks to transfer",
  "Вернитесь к сопоставлению и выберите хотя бы один найденный трек.":
    "Go back to matching and select at least one found track.",
  "Не удалось найти совпадения": "Couldn't find matches",
  "Проверьте подключение сервиса и повторите.":
    "Check the service connection and try again.",
  "Не удалось сопоставить треки": "Couldn't match tracks",
  "Попробуйте ещё раз или проверьте подключение сервиса.":
    "Try again or check the service connection.",
  "Сервис не вернул идентификатор плейлиста":
    "The service didn't return a playlist id",
  "Попробуйте ещё раз.": "Try again.",
  "ошибка сервиса": "service error",
  "Задача не найдена": "Job not found",
  "Возможно, она устарела. Запустите перенос заново.":
    "It may be stale. Start the transfer again.",
  "Нет модуля qrcode": "The qrcode module is missing",
  "Запустите start.bat — он доустановит зависимости.":
    "Run start.bat — it will install the dependencies.",
  "Для файла используйте импорт": "Use import for files",
  "Загрузите M3U, CSV или JSON.": "Upload M3U, CSV or JSON.",
  "Слишком большой блок заголовков": "Header block too large",
  "Скопируйте заголовки одного запроса browse.":
    "Copy the headers of a single browse request.",
  "Слишком большой плейлист": "Playlist too large",
  "Отправьте архив из «Скачать плейлист».":
    "Send the archive from “Download playlist”.",
  "Неизвестный сервис": "Unknown service",
  "Сейчас выполняется другая задача": "Another job is running",
  "Дождитесь её завершения или остановите.": "Wait for it to finish or stop it.",
  "Некорректные данные запроса": "Invalid request data",
  "Обновите страницу и попробуйте снова.": "Reload the page and try again.",
  "Доступ к Spotify отменён": "Spotify access cancelled",
  "Адрес для телефона недоступен": "Phone address unavailable",
  "Запустите TuneBridge через start-lan.bat (Windows) или start-lan.sh — приложение откроется для устройств в этой Wi-Fi сети.":
    "Launch TuneBridge via start-lan.bat (Windows) or start-lan.sh — the app will open to devices on this Wi-Fi network.",
  "Подключите аккаунт и повторите.": "Connect an account and try again.",
  "Нужно название плейлиста": "Playlist title required",
  "Введите название перед переносом.": "Enter a title before transferring.",

  "Нет связи с Яндекс Музыкой": "No connection to Yandex Music",
  "Проверьте интернет-соединение и попробуйте снова.":
    "Check your internet connection and try again.",
  "Проверьте интернет и попробуйте снова.": "Check your internet and try again.",
  "Плейлист не найден": "Playlist not found",
  "Проверьте ссылку. Возможно, плейлист удалён или скрыт владельцем.":
    "Check the link. The playlist may be deleted or hidden by its owner.",
  "Яндекс Музыка вернула ошибку": "Yandex Music returned an error",
  "Попробуйте ещё раз. Если ошибка повторяется — обновите подключение аккаунта.":
    "Try again. If the error persists, reconnect your account.",
  "Не удалось разобрать ссылку на плейлист":
    "Couldn't parse the playlist link",
  "Нужна ссылка вида music.yandex.ru/playlists/… или /users/…/playlists/…":
    "A link like music.yandex.ru/playlists/… or /users/…/playlists/… is required",
  "Откройте плейлист в Яндекс Музыке и скопируйте ссылку из адресной строки.":
    "Open the playlist in Yandex Music and copy the link from the address bar.",
  "Пустой токен": "Empty token",
  "Вставьте OAuth-токен Яндекс Музыки.": "Paste a Yandex Music OAuth token.",
  "Не удалось проверить токен": "Couldn't verify the token",
  "Попробуйте получить новый токен.": "Try getting a new token.",
  "Нет связи с Яндексом": "No connection to Yandex",
  "Не удалось начать вход в Яндекс Музыку":
    "Couldn't start Yandex Music sign-in",
  "Попробуйте позже или вставьте токен вручную.":
    "Try later or paste a token manually.",
  "Вход не начат": "Sign-in not started",
  "Нажмите «Получить код» ещё раз.": "Press “Get code” again.",
  "Код устарел": "The code has expired",
  "Получите новый код и подтвердите вход.":
    "Get a new code and confirm sign-in.",
  "Вход отменён": "Sign-in cancelled",
  "Попробуйте снова и подтвердите доступ.":
    "Try again and confirm access.",
  "Не удалось завершить вход": "Couldn't complete sign-in",
  "Попробуйте ещё раз или вставьте токен вручную.":
    "Try again or paste a token manually.",

  "Нет связи со Spotify": "No connection to Spotify",
  "Плейлист Spotify недоступен без входа":
    "Spotify playlist unavailable without sign-in",
  "Возможно, он приватный. Подключите аккаунт Spotify, чтобы открыть его.":
    "It may be private. Connect a Spotify account to open it.",
  "Spotify вернул ошибку": "Spotify returned an error",
  "Попробуйте ещё раз. Если ошибка повторяется — подключите аккаунт Spotify.":
    "Try again. If it persists, connect a Spotify account.",
  "Spotify вернул неожиданный ответ": "Spotify returned an unexpected response",
  "Попробуйте ещё раз или подключите аккаунт Spotify.":
    "Try again or connect a Spotify account.",
  "Spotify ограничил доступ": "Spotify restricted access",
  "Проверьте, что аккаунт добавлен в приложение Spotify (Users and Access) и имеет нужные права.":
    "Make sure the account is added to the Spotify app (Users and Access) with the required permissions.",
  "Плейлист Spotify не найден": "Spotify playlist not found",
  "Проверьте ссылку или доступ к плейлисту.":
    "Check the link or playlist access.",
  "Повторите попытку через минуту.": "Try again in a minute.",
  "Не удалось обратиться к Spotify": "Couldn't reach Spotify",
  "Не удалось разобрать ссылку на плейлист Spotify":
    "Couldn't parse the Spotify playlist link",
  "Нужна ссылка вида open.spotify.com/playlist/…":
    "A link like open.spotify.com/playlist/… is required",
  "Проверьте ссылку.": "Check the link.",
  "Spotify не вернул созданный плейлист":
    "Spotify didn't return the created playlist",
  "Неверный Client ID": "Invalid Client ID",
  "Скопируйте Client ID приложения из Spotify Developer Dashboard.":
    "Copy the app Client ID from the Spotify Developer Dashboard.",
  "Сессия подключения Spotify истекла": "The Spotify connection session expired",
  "Начните подключение заново.": "Start the connection again.",

  "Нет связи с YouTube Music": "No connection to YouTube Music",
  "Данные авторизации YouTube Music повреждены. Подключите аккаунт заново.":
    "YouTube Music authorization data is damaged. Reconnect your account.",
  "YouTube Music отклонил запрос": "YouTube Music rejected the request",
  "Проверьте подключение аккаунта и попробуйте снова.":
    "Check the account connection and try again.",
  "YouTube Music вернул ошибку": "YouTube Music returned an error",
  "Попробуйте ещё раз или обновите подключение аккаунта.":
    "Try again or reconnect your account.",
  "Не удалось обратиться к YouTube Music": "Couldn't reach YouTube Music",
  "Не удалось разобрать ссылку YouTube Music":
    "Couldn't parse the YouTube Music link",
  "Нужна ссылка вида music.youtube.com/playlist?list=…":
    "A link like music.youtube.com/playlist?list=… is required",
  "Плейлист YouTube Music недоступен без входа":
    "YouTube Music playlist unavailable without sign-in",
  "Возможно, он приватный. Подключите YouTube Music, чтобы открыть его.":
    "It may be private. Connect YouTube Music to open it.",
  "Плейлист YouTube Music не найден": "YouTube Music playlist not found",
  "YouTube Music не вернул созданный плейлист":
    "YouTube Music didn't return the created playlist",
  "Попробуйте ещё раз или проверьте подключение аккаунта.":
    "Try again or check the account connection.",
  "YouTube Music не принял часть треков":
    "YouTube Music didn't accept some tracks",
  "Проверьте, что плейлист не был изменён, и повторите.":
    "Make sure the playlist wasn't changed and retry.",
  "В cookie нет нужного ключа": "The cookie is missing a required key",
  "Скопируйте значение заголовка cookie целиком — в нём должен быть __Secure-3PAPISID.":
    "Copy the whole cookie header value — it must contain __Secure-3PAPISID.",
  "Не удалось разобрать cookie": "Couldn't parse the cookie",
  "Скопируйте значение заголовка cookie ещё раз, не разбивая его на части.":
    "Copy the cookie header value again without splitting it.",
  "Cookie пустые": "The cookies are empty",
  "Похоже, вы не вошли в аккаунт. Войдите на music.youtube.com и скопируйте cookie заново.":
    "Looks like you're not signed in. Sign in at music.youtube.com and copy the cookie again.",
  "Пустое поле": "Empty field",
  "Вставьте значение заголовка cookie со страницы music.youtube.com.":
    "Paste the cookie header value from music.youtube.com.",
  "Не удалось прочитать JSON": "Couldn't read the JSON",
  "Вставьте cookie или заголовки заново.": "Paste the cookie or headers again.",
  "Нужен объект с заголовками запроса.":
    "An object with request headers is required.",
  "В JSON нет cookie": "No cookie in the JSON",
  "Подойдёт объект с ключами cookie и authorization.":
    "An object with cookie and authorization keys will work.",
  "Не удалось разобрать вход": "Couldn't parse the sign-in",
  "Вставьте значение заголовка cookie из DevTools. cURL или блок заголовков тоже подойдут.":
    "Paste the cookie header value from DevTools. cURL or a block of headers also works.",

  "Нет связи с SoundCloud": "No connection to SoundCloud",
  "SoundCloud временно недоступен": "SoundCloud is temporarily unavailable",
  "Не удалось получить ключ доступа. Попробуйте ещё раз через минуту.":
    "Couldn't get the access key. Try again in a minute.",
  "Плейлист SoundCloud не найден": "SoundCloud playlist not found",
  "SoundCloud вернул ошибку": "SoundCloud returned an error",
  "SoundCloud вернул неожиданный ответ":
    "SoundCloud returned an unexpected response",
  "SoundCloud не требует входа": "SoundCloud doesn't require sign-in",
  "Откройте публичный плейлист по ссылке — аккаунт не нужен.":
    "Open a public playlist by link — no account needed.",
  "Не удалось разобрать ссылку SoundCloud":
    "Couldn't parse the SoundCloud link",
  "Нужна ссылка вида soundcloud.com/…/sets/…":
    "A link like soundcloud.com/…/sets/… is required",
  "Не удалось открыть короткую ссылку SoundCloud":
    "Couldn't open the SoundCloud short link",
  "Проверьте интернет и попробуйте полную ссылку из адресной строки.":
    "Check your internet and try the full link from the address bar.",
  "Это ссылка на трек, а не на плейлист":
    "This is a track link, not a playlist",
  "Откройте плейлист в SoundCloud и скопируйте ссылку на него.":
    "Open the playlist in SoundCloud and copy its link.",
  "Это не плейлист SoundCloud": "This isn't a SoundCloud playlist",

  "Нет связи с Apple Music": "No connection to Apple Music",
  "Плейлист Apple Music не найден": "Apple Music playlist not found",
  "Проверьте ссылку — возможно, он удалён или скрыт.":
    "Check the link — it may be deleted or hidden.",
  "Apple Music вернул ошибку": "Apple Music returned an error",
  "Попробуйте ещё раз через минуту.": "Try again in a minute.",
  "Apple Music вернул неожиданный ответ":
    "Apple Music returned an unexpected response",
  "Убедитесь, что плейлист публичный, и попробуйте снова.":
    "Make sure the playlist is public and try again.",
  "Apple Music не требует входа": "Apple Music doesn't require sign-in",
  "Не удалось разобрать ссылку Apple Music":
    "Couldn't parse the Apple Music link",
  "Нужна ссылка вида music.apple.com/…/playlist/…":
    "A link like music.apple.com/…/playlist/… is required",
  "В плейлисте Apple Music нет доступных треков":
    "No available tracks in the Apple Music playlist",
  "Возможно, он пуст или недоступен в вашем регионе.":
    "It may be empty or unavailable in your region.",

  "Файл слишком большой": "File is too large",
  "Максимальный размер — 5 МБ.": "The maximum size is 5 MB.",
  "Не удалось прочитать файл": "Couldn't read the file",
  "Поддерживаются M3U, M3U8, CSV, JSON и обычный текст со строками «Артист - Название».":
    "Supported: M3U, M3U8, CSV, JSON and plain text with “Artist - Title” lines.",
  "Проверьте, что файл не повреждён и содержит плейлист.":
    "Make sure the file isn't corrupted and contains a playlist.",
  "В файле не нашлось треков": "No tracks found in the file",
  "Для M3U нужны строки #EXTINF, для CSV — заголовки title/artist, для JSON — массив треков.":
    "M3U needs #EXTINF lines, CSV needs title/artist headers, JSON needs a track array.",

  "Неизвестный источник": "Unknown source",
  "Неизвестный сервис переноса": "Unknown transfer service",

  "Telegram: бот не подключён": "Telegram: bot not connected",
  "Добавьте токен бота — кнопка «Подключить Telegram».":
    "Add a bot token — the “Connect Telegram” button.",
  "Telegram не принял токен": "Telegram rejected the token",
  "Токен отозван или скопирован с ошибкой. Создайте нового бота через @BotFather.":
    "The token was revoked or copied incorrectly. Create a new bot via @BotFather.",
  "Telegram не нашёл этот чат": "Telegram couldn't find this chat",
  "Откройте бота в Telegram и отправьте ему /start, либо укажите @канал, где бот администратор.":
    "Open the bot in Telegram and send /start, or specify a @channel where the bot is an admin.",
  "Боту не хватает прав в канале": "The bot lacks permissions in the channel",
  "Добавьте бота администратором канала с правом публикации сообщений.":
    "Add the bot as a channel admin with permission to post messages.",
  "Telegram вернул ошибку": "Telegram returned an error",
  "Нет связи с Telegram": "No connection to Telegram",
  "Проверьте интернет. Если Telegram недоступен напрямую, включите VPN и повторите.":
    "Check your internet. If Telegram is blocked, enable a VPN and retry.",
  "Telegram отклонил запрос": "Telegram rejected the request",
  "Проверьте токен и повторите.": "Check the token and retry.",
  "Это не похоже на токен бота": "This doesn't look like a bot token",
  "Токен выглядит так: 123456789:AAH… — скопируйте его из сообщения @BotFather целиком.":
    "A token looks like 123456789:AAH… — copy it from @BotFather entirely.",
  "Непонятный адрес чата": "Unclear chat address",
  "Укажите @username канала или числовой ID из списка найденных чатов.":
    "Specify the channel @username or a numeric ID from the found chats.",
  "Укажите, куда отправить": "Choose where to send",
  "Введите @username канала или числовой ID чата.":
    "Enter the channel @username or a numeric chat ID.",
  "Бот уже подключён": "The bot is already connected",
  "В этом режиме используется общий бот TuneBridge — подключение своего бота недоступно.":
    "This mode uses the shared TuneBridge bot, so connecting your own bot isn't available.",
  "Пока не видно, куда отправлять": "Nothing to send to yet",
  "Откройте бота в Telegram, нажмите Start и отправьте /start. Затем вернитесь и повторите отправку.":
    "Open the bot in Telegram, press Start and send /start. Then come back and retry sending.",
  "В плейлисте нет треков": "The playlist has no tracks",
  "Загрузите плейлист заново.": "Reload the playlist.",

  "Локальный пользователь": "Local user",
  "Гость": "Guest",
  "Старт": "Start",
  "Про": "Pro",
  "Максимум": "Max",
  "Приветственные переносы": "Welcome tracks",
  "Приветственные треки": "Welcome tracks",
  "Начисление администратором": "Credited by admin",

  "Не пришло подтверждение Telegram": "No confirmation from Telegram",
  "Откройте TuneBridge как Mini App внутри Telegram и повторите вход.":
    "Open TuneBridge as a Mini App inside Telegram and try signing in again.",
  "Слишком большой запрос авторизации": "Authorization request is too large",
  "Вход через Telegram не настроен": "Telegram sign-in isn't configured",
  "Администратору нужно указать TUNEBRIDGE_BOT_TOKEN на сервере.":
    "The admin needs to set TUNEBRIDGE_BOT_TOKEN on the server.",
  "Не удалось прочитать подпись Telegram": "Couldn't read the Telegram signature",
  "Подпись Telegram повреждена": "The Telegram signature is corrupted",
  "В подписи Telegram нет hash": "The Telegram signature has no hash",
  "Telegram не подтвердил вход": "Telegram didn't confirm the sign-in",
  "Проверьте, что приложение открыто из нужного бота, и попробуйте снова.":
    "Make sure the app was opened from the correct bot and try again.",
  "В подписи нет времени входа": "The signature has no sign-in time",
  "Вход в Telegram устарел": "The Telegram sign-in has expired",
  "Закройте и снова откройте Mini App.": "Close and reopen the Mini App.",
  "Часы устройства расходятся с сервером": "The device clock differs from the server",
  "Проверьте время на телефоне и повторите вход.":
    "Check the time on your phone and sign in again.",
  "Не удалось прочитать профиль Telegram": "Couldn't read the Telegram profile",
  "Telegram не передал профиль": "Telegram didn't provide a profile",
  "Откройте Mini App из бота и повторите вход.":
    "Open the Mini App from the bot and try again.",
  "Некорректный профиль Telegram": "Invalid Telegram profile",
  "Нужен вход через Telegram": "Telegram sign-in required",
  "Откройте TuneBridge как Mini App в Telegram и вернитесь в кабинет.":
    "Open TuneBridge as a Mini App in Telegram and return to your account.",
  "Недостаточно прав": "Not enough permissions",
  "Действие доступно только администратору сервиса.":
    "This action is available only to the service admin.",

  "Такого пакета нет": "No such package",
  "Пополнение отключено": "Top-ups are disabled",
  "Сервис работает бесплатно: переносы не списывают токены.":
    "The service is free: transfers don't spend tokens.",
  "Промокоды отключены": "Promo codes are disabled",
  "Сервис бесплатный, поэтому промокоды больше не нужны.":
    "The service is free, so promo codes are no longer needed.",
  "Обновите страницу и выберите пакет заново.":
    "Reload the page and choose the package again.",
  "Оплата пока недоступна": "Payment isn't available yet",
  "На сервере не настроен бот Telegram. Попробуйте позже.":
    "The Telegram bot isn't configured on the server. Try again later.",
  "Заказ не найден": "Order not found",
  "Проверьте номер заказа.": "Check the order number.",
  "Вернуть можно только оплаченный заказ": "Only a paid order can be refunded",
  "Этот заказ ещё не оплачен или уже возвращён.":
    "This order isn't paid yet or was already refunded.",
  "Нет идентификатора платежа": "No payment ID",
  "Telegram не передал charge id — возврат невозможен.":
    "Telegram didn't provide a charge id — refund isn't possible.",
  "Пользователь не найден": "User not found",
  "Проверьте Telegram ID или ID в базе.": "Check the Telegram ID or the database ID.",
  "Возврат звёзд доступен только Telegram-аккаунтам.":
    "Star refunds are available only to Telegram accounts.",
  "Токены уже потрачены": "The tokens have already been spent",
  "Недостаточно треков на балансе": "Not enough tracks in your balance",
  "Пополните баланс или уменьшите плейлист: списывается по одному треку за добавленный.":
    "Top up or shorten the playlist: one track is charged per added track.",
  "Возврат за неперенесённые треки": "Refund for unadded tracks",
  "Верните звёзды без списания баланса или сначала пополните счёт вручную.":
    "Refund the Stars without deducting the balance, or top up the wallet manually first.",
  "Заказ уже изменился": "The order has already changed",
  "Обновите кабинет и повторите.": "Refresh your account and retry.",
  "Слишком много попыток": "Too many attempts",
  "Подождите несколько минут и попробуйте снова.":
    "Wait a few minutes and try again.",
  "Промокод не похож на настоящий": "That doesn't look like a valid promo code",
  "Проверьте раскладку и введите код ещё раз.":
    "Check your keyboard layout and enter the code again.",
  "Промокод не найден": "Promo code not found",
  "Проверьте код: возможно, в нём опечатка или он отключён.":
    "Check the code: it may have a typo or be disabled.",
  "Промокод истёк": "The promo code has expired",
  "Попросите новый код у администратора.": "Ask the admin for a new code.",
  "Промокод уже использован максимальное число раз":
    "The promo code has reached its usage limit",
  "Промокоды можно активировать один раз.": "Promo codes can be redeemed once.",
  "Вы уже активировали этот промокод": "You've already redeemed this promo code",
  "Каждый промокод срабатывает для аккаунта один раз.":
    "Each promo code works once per account.",
  "За один раз можно создать от 1 до 50 кодов":
    "You can create 1 to 50 codes at a time",
  "Начисление по промокоду должно быть от 1 до 100 000":
    "The promo credit must be between 1 and 100,000",
  "Лимит активаций должен быть от 0 до 100 000":
    "The activation limit must be between 0 and 100,000",
  "Срок действия должен быть от 0 до 365 дней":
    "The validity period must be between 0 and 365 days",
  "Обновите список кодов.": "Refresh the code list.",

  "Оплата не настроена": "Payment isn't configured",
  "Вебхук Telegram не настроен": "The Telegram webhook isn't configured",
  "Задайте секрет вебхука.": "Set the webhook secret.",
  "Неверный секрет вебхука": "Invalid webhook secret",
  "Некорректный запрос Telegram": "Invalid Telegram request",
  "Некорректная сумма": "Invalid amount",
  "Укажите от 1 до 1 000 000 токенов.": "Enter between 1 and 1,000,000 tokens.",
  "Не получилось изменить баланс": "Couldn't change the balance",
  "На счету недостаточно токенов для списания.":
    "There aren't enough tokens in the wallet to deduct.",
};

const RULES = [
  [/^Сопоставлено (\d+) из (\d+)$/, (m) => `Matched ${m[1]} of ${m[2]}`],
  [/^Добавлено (\d+) из (\d+)$/, (m) => `Added ${m[1]} of ${m[2]}`],
  [/^Начинаем поиск в (.+)$/, (m) => `Starting search in ${localize(m[1])}`],
  [/^Ищем совпадения в (.+)$/, (m) => `Finding matches in ${localize(m[1])}`],
  [/^Создаём плейлист в (.+)$/, (m) => `Creating a playlist in ${localize(m[1])}`],
  [/^Создаём плейлист «(.+)»$/, (m) => `Creating playlist “${m[1]}”`],
  [/^Добавляем треки в (.+)$/, (m) => `Adding tracks to ${localize(m[1])}`],
  [/^Поиск в (.+)$/, (m) => `Search in ${localize(m[1])}`],
  [/^Перенос в (.+)$/, (m) => `Transfer to ${localize(m[1])}`],
  [/^Перенесено из (.+)$/, (m) => `Transferred from ${localize(m[1])}`],
  [/^Готово: (\d+) из (\d+) совпадений$/, (m) => `Done: ${m[1]} of ${m[2]} matches`],
  [
    /^Не удалось проверить (\d+) из (\d+) треков\. Они отмечены как «не найдены» — их можно найти вручную\.$/,
    (m) =>
      `Couldn't check ${m[1]} of ${m[2]} tracks. They are marked as “missing” — you can find them manually.`,
  ],
  [/^Остановлено\. Добавлено (\d+) из (\d+)$/, (m) => `Stopped. Added ${m[1]} of ${m[2]}`],
  [/^Готово с ошибками: добавлено (\d+) из (\d+)$/, (m) => `Done with errors: added ${m[1]} of ${m[2]}`],
  [/^Все (\d+) треков добавлены$/, (m) => `All ${m[1]} tracks added`],
  [/^Не удалось добавить (.+?): (.+)$/, (m) => `Couldn't add ${label(m[1])}: ${localize(m[2])}`],
  [/^«(.+)»: (.+)$/, (m) => `“${m[1]}”: ${localize(m[2])}`],
  [/^(.+): аккаунт не подключён$/, (m) => `${localize(m[1])}: account not connected`],
  [/^Это ссылка на (.+), а не на плейлист$/, (m) => `This is a link to ${localize(m[1])}, not a playlist`],
  [/^Сервис «(.+)» пока не поддерживается\.$/, (m) => `The “${m[1]}” service isn't supported yet.`],
  [/^Spotify вернул ошибку: (.+)$/, (m) => `Spotify returned an error: ${m[1]}`],
  [/^Код ответа (\d+)\. Попробуйте ещё раз\.$/, (m) => `Response code ${m[1]}. Try again.`],
  [/^Тестовое пополнение «(.+)»$/, (m) => `Test top-up “${localize(m[1])}”`],
  [
    /^Пополнение через Telegram Stars \((\d+) шт\.\)$/,
    (m) => `Telegram Stars top-up (${m[1]} pcs.)`,
  ],
  [/^Промокод ([A-Z0-9]+)$/, (m) => `Promo code ${m[1]}`],
  [/^Возврат звёзд за заказ (.+)$/, (m) => `Star refund for order ${m[1]}`],
];

function label(value) {
  const match = /^(\d+) треков$/.exec(value);
  return match ? `${match[1]} tracks` : value;
}

export function localize(value) {
  if (value == null) return value;
  const text = String(value);
  if (!text || getLang() !== "en") return text;
  const exact = EXACT[text];
  if (exact) return exact;
  for (const [pattern, build] of RULES) {
    const match = pattern.exec(text);
    if (match) return build(match);
  }
  return text;
}
