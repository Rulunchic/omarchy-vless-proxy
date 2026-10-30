# ⚡ Omarchy VLESS Proxy & DNS Switcher

Удобный локальный клиент VLESS Reality / Xray и виджет для панели **Omarchy** (Arch Linux / Hyprland). Автоматически парсит подписки **BeregVPN**, позволяет на лету переключать серверы и умные DNS-профили (Comss, GeoHide, Cloudflare, AdGuard) в один клик.

---

## 🤖 Инструкция для ИИ-агента (AI Agent Prompt)

Если вы передаёте настройку своему ИИ-агенту (Antigravity, Cursor, Claude Code, OpenCodeInterpreter и др.), скопируйте и отправьте ему этот промпт:

```text
Привет! Помоги мне развернуть и настроить локальный VLESS прокси и виджет для панели Omarchy.

Репозиторий проекта: https://github.com/Rulunchic/omarchy-vless-proxy.git
Моя ссылка на подписку BeregVPN: [ВСТАВЬТЕ_СЮДА_ВАШУ_ССЫЛКУ_BEREGVPN]

Выполни следующие шаги:
1. Склонируй репозиторий в ~/Projects/omarchy-vless-proxy:
   git clone https://github.com/Rulunchic/omarchy-vless-proxy.git ~/Projects/omarchy-vless-proxy
2. Запусти скрипт установки с моей ссылкой подписки:
   cd ~/Projects/omarchy-vless-proxy && ./install.sh "[ВСТАВЬТЕ_СЮДА_ВАШУ_ССЫЛКУ_BEREGVPN]"
3. Скрипт автоматически:
   - Распарсит все VLESS Reality серверы из подписки и создаст для них конфигурации;
   - Скачает актуальный бинарник Xray в bin/xray (если не установлен в системе);
   - Установит CLI-команды zapret-toggle, zapret-settings, zapret-status в ~/.local/bin/;
   - Установит плагин виджета в ~/.config/omarchy/plugins/bobol.zapret/ и зарегистрирует его в ~/.config/omarchy/shell.json;
   - Настроит безопасный хук в ~/.bashrc, чтобы при выключении прокси интернет в терминале не ломался.
4. Проверь работоспособность с помощью:
   ~/Projects/omarchy-vless-proxy/core/proxy.sh test
5. Перезапусти панель Omarchy (или Quickshell), чтобы виджет отобразился на панели:
   omarchy-reload 2>/dev/null || quickshell-reload 2>/dev/null || true
```

---

## 🚀 Быстрая установка вручную (для пользователя)

```bash
# 1. Клонируем репозиторий
git clone https://github.com/Rulunchic/omarchy-vless-proxy.git ~/Projects/omarchy-vless-proxy
cd ~/Projects/omarchy-vless-proxy

# 2. Запускаем установку, указав ссылку на подписку BeregVPN
./install.sh "https://bereg.cc/ВАША_ССЫЛКА"
```

Скрипт автоматически всё распакует, настроит и запустит начальный тест.

---

## 🎮 Управление через панель Omarchy

После установки на верхней панели появится значок молнии (**⚡**):

- **ЛКМ (Левый клик)**:
  - **Включение / Выключение прокси**.
  - Значок подсвечивается **зеленым**, когда прокси активен, и серым, когда выключен.
  - При выключении система и браузеры мгновенно переходят на прямое соединение (интернет не зависает).
- **ПКМ (Правый клик)**:
  - Открывает графическое меню настроек (**Zenity / Tkinter**).
  - Позволяет выбрать сервер выхода и DNS-профиль.
- **Наведение мыши (Hover)**:
  - Отображает подсказку с текущим сервером, DNS-провайдером и статусом.

---

## 🌐 Поддерживаемые DNS-профили

В меню настроек (ПКМ) доступны 5 профилей DNS:

1. **Системный / Серверный (по умолчанию)**:
   - Резолв осуществляется напрямую через исходящий VLESS-сервер. Максимальная скорость и отсутствие задержек.
2. **Comss.one Smart DNS**:
   - DoH-профиль (`https://dns.comss.one/dns-query`) с bootstrap IP `185.146.157.78`. Отлично подходит для доступа к ChatGPT, Claude, Discord, Spotify.
3. **GeoHide Smart DNS**:
   - `193.233.112.88` со специализированной прямой маршрутизацией.
4. **Cloudflare DoH**:
   - Зашифрованный DNS over HTTPS (`https://1.1.1.1/dns-query`).
5. **AdGuard DoH**:
   - Зашифрованный DNS over HTTPS (`https://dns.adguard-dns.com/dns-query`) с блокировкой рекламы и трекеров.

---

## 💻 Полезные консольные команды

Все вспомогательные скрипты установлены в `~/.local/bin/` и доступны из любого места:

```bash
# Переключить состояние прокси (вкл / выкл)
zapret-toggle

# Открыть графическое окно выбора сервера и DNS
zapret-settings

# Вывести статус в формате JSON (используется виджетом)
zapret-status

# Протестировать скорость и проверить внешний IP через SOCKS5 и HTTP
~/Projects/omarchy-vless-proxy/core/proxy.sh test

# Посмотреть список всех доступных серверов
~/Projects/omarchy-vless-proxy/core/proxy.sh list

# Запустить конкретный сервер вручную через CLI
~/Projects/omarchy-vless-proxy/core/proxy.sh start finland
```

---

## 🔧 Архитектура и сетевая изоляция

- **Локальные порты**:
  - `127.0.0.1:10808` — SOCKS5 (с поддержкой UDP).
  - `127.0.0.1:10809` — HTTP/HTTPS Proxy.
- **Динамический системный прокси**:
  - При включении на лету активируются параметры GSettings GNOME/GTK и переменные пользовательской сессии `systemd`.
  - При выключении переменные полностью обнуляются, возвращая систему на прямое интернет-соединение.
- **Поддержка AI CLI (Antigravity `agy`, Cursor, Claude)**:
  - Для работы зарубежных AI-инструментов из РФ рекомендуется сервер **Финляндия** (Google Cloud Code / Gemini API полностью разблокированы).
