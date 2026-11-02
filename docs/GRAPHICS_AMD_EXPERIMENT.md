# GRAPHICS .103: Radeon RX 7600 XT 16GB — экспериментальная ACE-Step

Цель — оценить, можно ли перенести второй аудиодвижок с CORE .100 (RTX 3060 12GB CUDA) на Windows 11 Pro .103 (AMD Ryzen 5 5600, Radeon RX 7600 XT 16GB, RAM 32GB, SSD 1TB) для **параллельной** работы: Qwen на .100 / ACE-Step на .103. Пока **не переносим** действующую установку на .100.

## Реальная совместимость, а не только объём VRAM

Официальная таблица AMD **Windows ROCm 7.2.1** перечисляет `gfx1100`/`gfx1101` и соответствующие Radeon, но **не включает RX 7600 XT (gfx1102)**. Это означает **отсутствие официально подтверждённой совместимости** с выбранной моделью. 16GB VRAM само по себе не решает проблему.

Официальная ACE-Step 1.5 предоставляет вариант установки **Windows ROCm 7.2 / Python 3.12**, специальный `requirements-rocm.txt` и `start_api_server_rocm.bat`, а для RX 7600-family предлагает `HSA_OVERRIDE_GFX_VERSION=11.0.2`. Это экспериментальный путь, который может не сработать или потребовать особых драйверов. Не рекомендуется ставить CUDA PyTorch через `uv sync` поверх ROCm-окружения.

Источники:
- [AMD: Windows ROCm support matrix](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html)
- [ACE-Step: install / AMD ROCm Windows](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INSTALL.md)
- [ACE-Step: Windows ROCm batch launcher](https://github.com/ace-step/ACE-Step-1.5/blob/main/start_api_server_rocm.bat)
- [ACE-Step: GPU troubleshooting RX 7600](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/GPU_TROUBLESHOOTING.md)

## Шаг 1. Только безопасная диагностика на .103

Открой PowerShell на Windows .103 (или по RDP) и выполни из клона проекта:

```powershell
cd C:\путь\к\muzikfed
powershell -ExecutionPolicy Bypass -File .\scripts\check-graphics-rocm.ps1
```

Скрипт **не загружает модели, не устанавливает ROCm/драйверы, не включает порты и не изменяет службу**. Покажет видеоадаптер, драйвер, список Python, наличие PyTorch HIP и доступность GPU. Для ROCm Windows нужна **Python 3.12**, а не Python 3.14.

Если PyTorch недоступен, это ещё не доказательство неисправности видеокарты: ROCm пока может отсутствовать. Если драйвер/torch установлены, но RX 7600 XT не определяется, **остановись** — не запускай модификации драйвера или неподдерживаемые ядра вслепую.

## Шаг 2. Только после подтверждения PyTorch ROCm GPU

Можно по инструкции ACE-Step создать **отдельное ROCm-окружение**, использовать их `start_api_server_rocm.bat`, установить `HSA_OVERRIDE_GFX_VERSION=11.0.2` для gfx1102, проверить генерацию **60-секундной** песни. Учти: это не гарантированно поддерживаемый AMD режим. Никаких таких изменений скрипт диагностики не делает.

Пример (только после правильной ручной установки и работающего CUDA-like PyTorch API):

```powershell
py -3.12 -c "import torch; print(torch.version.hip); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

Если это пройдёт и API создаёт реальные MP3 на .103, можно обсудить сетевой аудио-воркер с CORE: .100 будет посылать задачи по **LAN/VPN**, не открывая порт .103 наружу. Понадобится защита внутреннего API и разрешённое подключение только от .100. В **текущем коде Pocket Orchestra** ACE-Step привязана к `127.0.0.1:8001` на CORE, маршрутизация на .103 **ещё не реализована**.

## Пока гарантированный рабочий путь

На .100 CUDA и ACE-Step уже реально создают русские песни. Сохраняем этот путь, генерируем MP3 1–10 минут; .103 используем для MuseScore Studio, MuseSounds и DAW. Только при подтверждённом рабочем AMD ROCm и аудио-тесте переносим часть генерации.
