# GitHub ↔ Acer ↔ Ubuntu CORE: команды на каждый день

Репозиторий: **https://github.com/musikfed/muzikfed**; ветка **main**.  
Веб-пульт на CORE: **http://192.168.0.100:9095** (по действующему LAN/VPN).
**Все файлы проекта на CORE — в `/1tbdisk/muzikfed` на 2 ТБ диске.** Включая `.venv`, `outputs` и кэш `uv`. Файл user-unit остаётся в стандартной папке systemd в домашнем каталоге.

## Сценарий A. Загрузить всё из GitHub на сервер .100

**Самый простой путь:** зайти с Acer по SSH в Ubuntu .100, выполнить:

```bash
# Первый раз на .100
sudo apt update
sudo apt install -y git curl fluidsynth fluid-soundfont-gm
findmnt -T /1tbdisk       # сначала убедись, что диск подключён
# Если каталог ещё отсутствует, дать обычному пользователю права только на папку проекта:
sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 755 /1tbdisk/muzikfed
git clone https://github.com/musikfed/muzikfed.git /1tbdisk/muzikfed
cd /1tbdisk/muzikfed
bash scripts/install-core.sh

# Проверить сервис и открыть на Acer http://192.168.0.100:9095
curl -fsS http://192.168.0.100:9095/api/health
```

При существующей папке `/1tbdisk/muzikfed` команда `git clone` допускает только **пустую** директорию; если в ней уже есть `.git` от этого репозитория, используй `git -C /1tbdisk/muzikfed pull --ff-only origin main`. Не удаляй и не перезаписывай чужие файлы. Скрипт `deploy-to-core.sh` выполняет эти проверки автоматически.

**В дальнейшем** на Ubuntu .100:

```bash
cd /1tbdisk/muzikfed
bash scripts/update-core.sh
```

**То же самое одной командой с Acer**, если установлен WSL или Git Bash и SSH работает по VPN:

```bash
git clone https://github.com/musikfed/muzikfed.git
cd muzikfed
bash scripts/deploy-to-core.sh user@192.168.0.100
```

Скрипт развернёт последнюю версию **строго в `/1tbdisk/muzikfed` на CORE** из GitHub, а не незакоммиченные файлы с Acer. Поэтому сначала `git push`, потом `deploy-to-core.sh`.

## Сценарий B. Изменил файлы на Acer → отправить в GitHub

Работай в клонированном каталоге `muzikfed` (в WSL/Git Bash/PowerShell с Git):

```bash
cd muzikfed
git switch main
git status
git pull --ff-only origin main

# Изменить код/документацию в редакторе.
git add pocket_orchestra/app.py README.md docs/DEPLOYMENT.md
git diff --cached --check
git diff --cached
git commit -m "feat: update Pocket Orchestra"
git push origin main
```

`git add` перечисляет **только те файлы, которые ты реально изменил**. Перед коммитом всегда смотри `git diff --cached`. Если нет изменений, `git commit` сообщит об этом — ничего дополнительно делать не нужно.

После успешного push разверни код на CORE:

```bash
bash scripts/deploy-to-core.sh user@192.168.0.100
```

## Сценарий C. Изменил файлы прямо на сервере .100 → отправить в GitHub

```bash
ssh user@192.168.0.100
cd /1tbdisk/muzikfed
git status
# Если есть незакоммиченные правки, сначала сохрани их в коммите.
git add pocket_orchestra/app.py
git diff --cached --check
git diff --cached
git commit -m "fix: change server application"
git pull --rebase origin main
git push origin main
bash scripts/install-core.sh
```

Команда `git pull --rebase` в этом сценарии запускается **после коммита**, чтобы не перезаписать локальные изменения. При конфликте остановись и реши его перед продолжением; **не используй `git push --force`**.

## Сценарий D. Изменения сделаны через ChatGPT + GitHub

Когда изменения уже закоммичены в репозитории через подключённый GitHub, **не надо делать `git push`**: код уже в GitHub. На сервере обнови рабочую версию:

```bash
cd /1tbdisk/muzikfed
bash scripts/update-core.sh
```

## Настройка Git для коммитов (один раз на каждом компьютере)

```bash
git config --global user.name "Ваше имя или GitHub-ник"
git config --global user.email "Ваш подтверждённый e-mail GitHub"
```

`git clone` публичного репозитория не требует авторизации. **Для push нужна авторизация GitHub.** Один из способов — SSH:

```bash
ssh-keygen -t ed25519 -C "pocket-orchestra"
cat ~/.ssh/id_ed25519.pub
```

Добавь **только публичный ключ** (с расширением `.pub`) в GitHub → Settings → SSH and GPG keys → New SSH key. Затем:

```bash
ssh -T git@github.com
git remote set-url origin git@github.com:musikfed/muzikfed.git
git push origin main
```

Альтернатива — HTTPS и Git Credential Manager / `gh auth login` (если `gh` установлен). Обычный пароль GitHub для `git push` через HTTPS не подходит. Токены и приватные ключи никогда не включай в исходники, историю команд или документацию.

## Как проверить результат

```bash
git remote -v             # GitHub URL
git branch --show-current # main
git status                # желательно: working tree clean
git log -1 --oneline      # последний локальный коммит
```

На сервере после установки:

```bash
systemctl --user status pocket-orchestra --no-pager
curl -fsS http://192.168.0.100:9095/api/health
```

Проверь в GitHub, что новый коммит появился на https://github.com/musikfed/muzikfed/commits/main.

## Что нельзя добавлять в коммиты

- `~/crt-cert/privkey.pem`, `~/crt-cert/fullchain.pem`, WireGuard/SSH-ключи, токены, `.env`;
- `outputs/`, `.venv/`, `__pycache__/`, большие звуковые библиотеки и веса моделей;
- реальные пароли, URL с токенами, файлы резервных копий с учётными данными.

Не используй `sudo git`, `git push --force`, `git reset --hard` без отдельного обоснования. Для обновления с GitHub держи рабочий каталог CORE чистым. Если хочешь сохранить локальные правки — сначала сделай коммит или перенос на отдельную ветку.
