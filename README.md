## Description

Клиент/сервер для синхронного прослушивания музыки. Бекэнд - питон, фронтэнд - мелкая фиговина в трее (никакого UI). Синхронизация через веб апи сервер (к сожалению), приглосы через discord rich presence

Client/server app for synchronous music listening. Python for backend, small tray icon as frontend. Syncs through web api server, invites through discord rich presence (or web link).

## Progress

- [ ] Discover music and track progress
    - [x] Discovering Yandex Music through API
    - [x] Discovering through win sdk
    - [ ] Search on youtube
    - [ ] Search on yandex music
    - [ ] Search locally (in given locations)
- [x] Playback
- [ ] Stream downloads
    - [ ] from youtube
    - [x] from yandex music
    - [ ] p2p
        - [ ] STUN
        - [ ] TURN
        - [ ] local network discovery
    - [x] and stream playback
- [x] Send / update track progress as well as music source
    - [x] flask web server
        - [ ] in docker
- [ ] Tray icon with some buttons
    - [ ] Cute icon
- [ ] Discord rich presence
    - [ ] Register app through win registry for opening links
- [ ] Installer


## Как работает

стейтмашина:

сервер не работает - ничего делать не надо  \
сервер работает, музыка не играет - ничего делать не надо \
сервер работает, музыка играет, винсдк показывает - определить источник музыки и передать клиенту (если нужен апдейт) \
сервер работает, музыка играет, винсдк не показывает - проверить ямузыку, если текущий трек новый - передать клиенту

источник музыки / как передавать клиенту: \
локальная папка (указать) - п2п / youtube / ямузыка (в таком порядке) \
ютуб - youtube / ямузыка \
ямузыка - youtube / ямузыка

## Настройки

- Поддерживаемые источники (для поиска трека):
    - Яндекс музыка (когда ставишь галку - проверить работоспособность)
    - Ютуб
    - папка для обнаружения музыки (покрасить в серый, если п2п запрещён)
- Поддерживаемые источники (для загрузки): 
    - Яндекс музыка (то же самое)
    - Ютуб
    - п2п (указать папку для загрузок)
- Запрет отдавать через п2п
- Захостить (копирует ссылку в буфер обмена)
- Подсоединиться (открывает диалоговое окно для вставки ссылки)
- Discord rich presence
- Зарегистрировать для открытия ссылок
- Разрешить проигрывать потоковые загрузки (по умолчанию выключено и не реализовано)
- Указать альтернативный адрес STUN/API сервера (открывает диалоговое окно для вставки ссылки/ip)
- Открыть папку с логами

посортирую потом