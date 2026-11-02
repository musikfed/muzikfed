# Включение и выключение Pocket Orchestra — без токенов

**CORE Ubuntu 24.04:** `/1tbdisk/muzikfed`  
**Веб-пульт по твоему VPN:** http://192.168.0.100:9095  
**Служба:** `pocket-orchestra.service` (обычный пользователь `user`).

Никаких паролей, кодов и дополнительных токенов для управления Pocket Orchestra **не требуется**. Остаются только кнопка «Выключить» с простым подтверждением в браузере и скрипты запуска/остановки через SSH.

## Выключить с Acer в браузере

1. Открой `http://192.168.0.100:9095` по LAN/VPN.
2. В разделе **«Питание Pocket Orchestra»** нажми **«■ Выключить Pocket Orchestra»**.
3. Подтверди выключение.

Приложение запланирует остановку через 3 секунды, чтобы страница получила ответ. Будет выполнена команда `systemctl --user disable --now pocket-orchestra.service` — **останавливается Pocket Orchestra и отключается его автозапуск**. Сама Ubuntu, SSH, VPN, Ollama и другие службы продолжат работать. Исходники и музыка в `outputs/` останутся на месте.

**Важно:** выключенный веб-сервер не может принимать команду включения. Чтобы снова запустить Pocket Orchestra, используй SSH на CORE (ниже). Не создаём вторую отдельную службу ради ещё одной кнопки.

## Включить и выключить через SSH

```bash
ssh user@192.168.0.100
cd /1tbdisk/muzikfed

bash scripts/start-core.sh     # ВКЛ + автозапуск
bash scripts/stop-core.sh      # ВЫКЛ + убрать автозапуск
bash scripts/restart-core.sh   # перезапуск
bash scripts/status-core.sh    # состояние
```

С Acer можно одной командой:

```powershell
ssh user@192.168.0.100 "bash /1tbdisk/muzikfed/scripts/start-core.sh"
ssh user@192.168.0.100 "bash /1tbdisk/muzikfed/scripts/stop-core.sh"
```

Прямые команды systemd без обёрток:

```bash
systemctl --user enable --now pocket-orchestra.service
systemctl --user disable --now pocket-orchestra.service
systemctl --user status pocket-orchestra.service --no-pager
```

Не выполняй `sudo bash scripts/start-core.sh`: проект запущен как служба обычного пользователя.

## Обновить с GitHub

```bash
cd /1tbdisk/muzikfed
bash scripts/update-core.sh
```

**Внимание:** `update-core.sh` скачивает код, запускает тесты, затем включает/перезапускает службу. Если хочешь оставить её выключенной после обновления, выполни `bash scripts/stop-core.sh`.

Если нужен автозапуск без пользовательской SSH-сессии после перезагрузки:

```bash
sudo loginctl enable-linger "$USER"
```

## Сеть и безопасность

Ты используешь доверенную LAN/WireGuard VPN. Кнопка не требует отдельного кода, а сервер принимает её запрос только с собственного веб-интерфейса (проверка Origin). **Любой человек, имеющий доступ к этой локальной веб-странице, сможет нажать «Выключить».** Это сознательное упрощение для твоей сети.

Не пробрасывай порт `9095` на публичный интернет. Не меняем сертификаты `~/crt-cert/`, настройки WireGuard, SSH или прочие проекты. Не запускаем чужие команды из веб-формы — выключается строго один пользовательский systemd unit.

## Три режима сочинения

В интерфейсе доступны «Только инструменты», «Только вокальный SATB» и «Инструменты + SATB». Вокальный SATB в v0.1 — только нотные партии на `Ahh/Ooh/Mmm`, **не исполнение русских слов**. См. [TEST_MODES.md](TEST_MODES.md).

## Если установлен отдельный ACE-Step 1.5

Он управляется **отдельно** и не выключается кнопкой остановки основной веб-службы:

```bash
bash /1tbdisk/muzikfed/scripts/start-ace-step.sh
bash /1tbdisk/muzikfed/scripts/stop-ace-step.sh
```

ACE-Step устанавливается **только по желанию**, подробности: [ACE_STEP_SETUP.md](ACE_STEP_SETUP.md).

## Если что-то не включается

```bash
cd /1tbdisk/muzikfed
bash scripts/status-core.sh
journalctl --user -u pocket-orchestra.service -n 100 --no-pager
```
